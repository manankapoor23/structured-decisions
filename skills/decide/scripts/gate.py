#!/usr/bin/env python3
"""Apply a policy to a validated decision. No external dependencies.

The gate runs outside the model. It reads only these fields of the decision:
`decision`, `confidence`, `abstained`, `needs_review`, `evidence`. Everything
that controls permission — the threshold, the action, its consequence — comes
from the policy and the caller. A model cannot widen its own authority by
adding a field, and the validator rejects decisions carrying fields outside
the contract.

Stages, kept separate on purpose:

  raw confidence -> calibration -> risk/cost policy -> threshold -> verdict

Verdicts and exit codes:

  AUTOMATION_ALLOWED   0   the caller may act without a person
  HUMAN_REVIEW        10   a person must look at this first
  ABSTAIN             30   the model declined to decide; nothing to act on
  REJECT_RESULT       20   the output is malformed or off-policy
  usage/policy error   2

Only exit code 0 means automate. Every other code means do not.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate import validate  # noqa: E402
from thresholds import (  # noqa: E402
    CONSEQUENCE_ORDER,
    INSUFFICIENT_DATA_STRATEGIES,
    calibrated_confidence,
    resolve_threshold,
    select_group,
)

EXIT_CODES = {"AUTOMATION_ALLOWED": 0, "HUMAN_REVIEW": 10, "REJECT_RESULT": 20, "ABSTAIN": 30}

POLICY_REQUIRED = {"allowed_decisions", "require_evidence"}
POLICY_OPTIONAL = {
    "automation_threshold", "review_below", "max_consequence",
    "class_thresholds", "actions", "consequence_thresholds", "calibration",
}
CALIBRATION_KEYS = {"path", "min_samples", "target_accuracy", "insufficient_data", "shrinkage_weight"}


def _is_fraction(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 1


def validate_policy(policy):
    """Structural and internal-consistency checks. A contradictory policy is an
    error rather than something to resolve silently at gate time."""
    errors = []
    if not isinstance(policy, dict):
        return ["policy must be an object"]

    missing = POLICY_REQUIRED - policy.keys()
    if missing:
        errors.append(f"missing policy fields: {sorted(missing)}")
    extra = set(policy) - POLICY_REQUIRED - POLICY_OPTIONAL
    if extra:
        errors.append(f"unexpected policy fields: {sorted(extra)}")

    allowed = policy.get("allowed_decisions")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(x, str) and x for x in allowed):
        errors.append("allowed_decisions must be a non-empty array of non-empty strings")
        allowed = []
    if not isinstance(policy.get("require_evidence"), bool):
        errors.append("require_evidence must be boolean")

    for field in ("automation_threshold", "review_below"):
        if field in policy and not _is_fraction(policy[field]):
            errors.append(f"{field} must be a number between 0 and 1")
    if "review_below" in policy and "automation_threshold" not in policy:
        errors.append("review_below has no meaning without automation_threshold")
    if ("review_below" in policy and "automation_threshold" in policy
            and _is_fraction(policy["review_below"]) and _is_fraction(policy["automation_threshold"])
            and policy["review_below"] > policy["automation_threshold"]):
        errors.append("review_below must not exceed automation_threshold")

    if "max_consequence" in policy and policy["max_consequence"] not in CONSEQUENCE_ORDER:
        errors.append(f"max_consequence must be one of {sorted(CONSEQUENCE_ORDER)}")

    ladder = policy.get("consequence_thresholds")
    if ladder is not None:
        if not isinstance(ladder, dict):
            errors.append("consequence_thresholds must be an object")
            ladder = {}
        else:
            for level, value in ladder.items():
                if level not in CONSEQUENCE_ORDER:
                    errors.append(f"consequence_thresholds key '{level}' is not a consequence level")
                if not _is_fraction(value):
                    errors.append(f"consequence_thresholds['{level}'] must be a number between 0 and 1")
            ordered = [ladder[k] for k in ("low", "medium", "high") if k in ladder and _is_fraction(ladder[k])]
            if ordered != sorted(ordered):
                errors.append(
                    "consequence_thresholds must not decrease as consequence rises; a costlier "
                    "action cannot require less confidence"
                )
    ladder = ladder or {}

    class_thresholds = policy.get("class_thresholds")
    if class_thresholds is not None:
        if not isinstance(class_thresholds, dict):
            errors.append("class_thresholds must be an object")
        else:
            for label, value in class_thresholds.items():
                if not _is_fraction(value):
                    errors.append(f"class_thresholds['{label}'] must be a number between 0 and 1")
                if allowed and label not in allowed:
                    errors.append(f"class_thresholds names '{label}', which is not an allowed decision")

    actions = policy.get("actions")
    if actions is not None:
        if not isinstance(actions, dict) or not actions:
            errors.append("actions must be a non-empty object")
        else:
            for name, entry in actions.items():
                if not isinstance(entry, dict):
                    errors.append(f"actions['{name}'] must be an object")
                    continue
                unknown = set(entry) - {"threshold", "consequence", "description"}
                if unknown:
                    errors.append(f"actions['{name}'] has unexpected fields: {sorted(unknown)}")
                if "threshold" in entry and not _is_fraction(entry["threshold"]):
                    errors.append(f"actions['{name}'].threshold must be a number between 0 and 1")
                level = entry.get("consequence")
                if level is not None and level not in CONSEQUENCE_ORDER:
                    errors.append(f"actions['{name}'].consequence must be one of {sorted(CONSEQUENCE_ORDER)}")
                if (level in ladder and "threshold" in entry and _is_fraction(entry["threshold"])
                        and entry["threshold"] < ladder[level]):
                    errors.append(
                        f"actions['{name}'] sets threshold {entry['threshold']} but its "
                        f"consequence '{level}' requires at least {ladder[level]}"
                    )
                if not entry.get("threshold") and level is None:
                    errors.append(f"actions['{name}'] must set a threshold, a consequence, or both")
                if "threshold" not in entry and level is not None and level not in ladder:
                    errors.append(
                        f"actions['{name}'] is '{level}' consequence but consequence_thresholds "
                        f"has no '{level}' entry, so the action has no threshold of its own"
                    )

    calibration = policy.get("calibration")
    if calibration is not None:
        if not isinstance(calibration, dict):
            errors.append("calibration must be an object")
        else:
            unknown = set(calibration) - CALIBRATION_KEYS
            if unknown:
                errors.append(f"calibration has unexpected fields: {sorted(unknown)}")
            if "target_accuracy" in calibration and not _is_fraction(calibration["target_accuracy"]):
                errors.append("calibration.target_accuracy must be a number between 0 and 1")
            minimum = calibration.get("min_samples")
            if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1):
                errors.append("calibration.min_samples must be an integer of at least 1")
            weight = calibration.get("shrinkage_weight")
            if weight is not None and (isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0):
                errors.append("calibration.shrinkage_weight must be a positive number")
            strategy = calibration.get("insufficient_data")
            if strategy is not None and strategy not in INSUFFICIENT_DATA_STRATEGIES:
                errors.append(
                    f"calibration.insufficient_data must be one of {sorted(INSUFFICIENT_DATA_STRATEGIES)}"
                )
            if "path" in calibration and not isinstance(calibration["path"], str):
                errors.append("calibration.path must be a string")
    return errors


def validate_calibration(artifact):
    errors = []
    if not isinstance(artifact, dict):
        return ["calibration artifact must be an object"]
    groups = artifact.get("groups")
    if not isinstance(groups, dict) or not groups:
        return ["calibration artifact must hold a non-empty 'groups' object"]
    for key, group in groups.items():
        if not isinstance(group, dict):
            errors.append(f"groups['{key}'] must be an object")
            continue
        if not isinstance(group.get("count"), int) or group["count"] < 0:
            errors.append(f"groups['{key}'].count must be a non-negative integer")
        bins = group.get("bins")
        if not isinstance(bins, list):
            errors.append(f"groups['{key}'].bins must be an array")
            continue
        for i, b in enumerate(bins):
            if not isinstance(b, dict):
                errors.append(f"groups['{key}'].bins[{i}] must be an object")
                continue
            for numeric in ("lower", "upper", "empirical_accuracy"):
                if not _is_fraction(b.get(numeric)):
                    errors.append(f"groups['{key}'].bins[{i}].{numeric} must be between 0 and 1")
            if not isinstance(b.get("count"), int) or b["count"] < 0:
                errors.append(f"groups['{key}'].bins[{i}].count must be a non-negative integer")
    return errors


def _resolve_consequence(policy, action, stated):
    """Consequence comes from the caller or the policy, never the decision.

    Returns (level_or_None, error_reason_or_None).
    """
    actions = policy.get("actions") or {}
    declared = (actions.get(action) or {}).get("consequence") if action is not None else None
    if stated is not None and declared is not None and stated != declared:
        return None, (
            f"the caller states this action is '{stated}' consequence but the policy "
            f"declares action '{action}' as '{declared}'"
        )
    return (stated if stated is not None else declared), None


def gate(decision, policy, consequence=None, action=None, calibration=None):
    """Return (verdict, reasons). The order below is the documented order."""
    verdict, reasons, _ = explain(decision, policy, consequence, action, calibration)
    return verdict, reasons


def explain(decision, policy, consequence=None, action=None, calibration=None):
    """Return (verdict, reasons, detail). `detail` carries the audit trail."""
    detail = {
        "action": action,
        "class": decision.get("decision") if isinstance(decision, dict) else None,
        "raw_confidence": decision.get("confidence") if isinstance(decision, dict) else None,
        "calibrated_confidence": None,
        "threshold": None,
        "threshold_source": None,
        "consequence": None,
        "calibration_group": None,
        "calibration_samples": None,
    }

    # Shape and allowed labels are a contract question: a malformed result is
    # rejected. Whether there is enough evidence to act on is a policy question,
    # checked below, and answerable by a person. Validating with
    # require_evidence=False keeps the two from collapsing into one verdict.
    schema_errors = validate(
        decision,
        allowed_decisions=policy["allowed_decisions"],
        require_evidence=False,
    )
    if schema_errors:
        return "REJECT_RESULT", schema_errors, detail

    # The model declined. There is no decision to gate.
    if decision["abstained"]:
        missing = decision.get("missing_information") or []
        reason = "the model abstained"
        if missing:
            reason += f"; it needs: {', '.join(missing)}"
        return "ABSTAIN", [reason], detail

    if policy["require_evidence"] and not decision["evidence"]:
        return "HUMAN_REVIEW", ["required evidence is missing"], detail
    if decision["needs_review"]:
        return "HUMAN_REVIEW", ["the decision requested review"], detail

    actions = policy.get("actions") or {}
    if action is not None and actions and action not in actions:
        return "HUMAN_REVIEW", [
            f"action '{action}' is not described by the policy, so its cost is unknown; "
            f"the policy describes: {sorted(actions)}"
        ], detail

    level, conflict = _resolve_consequence(policy, action, consequence)
    detail["consequence"] = level
    if conflict:
        return "HUMAN_REVIEW", [conflict], detail

    cap = policy.get("max_consequence")
    if cap is not None:
        if level is None:
            return "HUMAN_REVIEW", [
                "the policy limits consequence but neither the caller nor the policy "
                "stated the consequence of this action"
            ], detail
        if CONSEQUENCE_ORDER[level] > CONSEQUENCE_ORDER[cap]:
            return "HUMAN_REVIEW", [f"consequence '{level}' exceeds the policy limit '{cap}'"], detail

    raw = decision["confidence"]
    resolution = resolve_threshold(policy, decision["decision"], action, calibration, raw)
    detail["threshold"] = resolution.threshold
    detail["threshold_source"] = resolution.source
    detail["calibration_group"] = resolution.group
    detail["calibration_samples"] = resolution.sample_count

    observed = resolution.calibrated_confidence
    if observed is None and calibration is not None:
        # The threshold came from the policy rather than the data, but the
        # observed accuracy is still worth reporting next to the verdict.
        key, group = select_group(calibration, decision["decision"], action)
        if group:
            observed = calibrated_confidence(raw, group.get("bins") or [])
            if detail["calibration_group"] is None:
                detail["calibration_group"] = key
                detail["calibration_samples"] = group.get("count")
    detail["calibrated_confidence"] = observed

    if not resolution.resolved:
        return "HUMAN_REVIEW", list(resolution.notes), detail

    if raw < resolution.threshold:
        note = (f"confidence {raw} is below the threshold {resolution.threshold} "
                f"({resolution.source})")
        if observed is not None:
            note += f"; decisions in this confidence range were correct {observed} of the time"
        return "HUMAN_REVIEW", [note] + list(resolution.notes), detail

    allowed_note = f"confidence {raw} meets the threshold {resolution.threshold} ({resolution.source})"
    if observed is not None:
        allowed_note += f"; decisions in this confidence range were correct {observed} of the time"
    return "AUTOMATION_ALLOWED", [allowed_note] + list(resolution.notes), detail


def main():
    parser = argparse.ArgumentParser(description="Apply a decision policy to a decision object.")
    parser.add_argument("decision", help="path to a decision JSON file")
    parser.add_argument("policy", help="path to a policy JSON file")
    parser.add_argument(
        "--consequence",
        choices=sorted(CONSEQUENCE_ORDER),
        help="consequence of the action this decision would trigger",
    )
    parser.add_argument("--action", metavar="NAME", help="the action the caller intends to take")
    parser.add_argument(
        "--calibration", metavar="PATH",
        help="calibration artifact; overrides calibration.path in the policy",
    )
    parser.add_argument("--judgment", metavar="ID", help="gate one judgment by id, when the file holds several")
    parser.add_argument("--json", action="store_true", help="print the full audit trail as JSON")
    args = parser.parse_args()

    decision = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))

    if isinstance(decision, dict) and "judgments" in decision:
        if args.judgment is None:
            print("INVALID USAGE")
            print(f"- the file holds several judgments; pass --judgment with one of: "
                  f"{sorted(decision['judgments'])}")
            raise SystemExit(2)
        if args.judgment not in decision["judgments"]:
            print("INVALID USAGE")
            print(f"- no judgment '{args.judgment}'; the file has: {sorted(decision['judgments'])}")
            raise SystemExit(2)
        decision = decision["judgments"][args.judgment]
    elif args.judgment is not None:
        print("INVALID USAGE")
        print("- --judgment was given but the file holds a single decision")
        raise SystemExit(2)

    policy_errors = validate_policy(policy)
    if policy_errors:
        print("INVALID POLICY")
        for error in policy_errors:
            print(f"- {error}")
        raise SystemExit(2)

    calibration = None
    path = args.calibration or (policy.get("calibration") or {}).get("path")
    if path:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path(args.policy).parent / path
        if not resolved.exists():
            print("INVALID POLICY")
            print(f"- calibration artifact not found: {resolved}")
            raise SystemExit(2)
        calibration = json.loads(resolved.read_text(encoding="utf-8"))
        artifact_errors = validate_calibration(calibration)
        if artifact_errors:
            print("INVALID POLICY")
            for error in artifact_errors:
                print(f"- {error}")
            raise SystemExit(2)

    verdict, reasons, detail = explain(decision, policy, args.consequence, args.action, calibration)
    if args.json:
        print(json.dumps({"verdict": verdict, "reasons": reasons, **detail}, indent=2))
    else:
        print(verdict)
        for reason in reasons:
            print(f"- {reason}")
    raise SystemExit(EXIT_CODES[verdict])


if __name__ == "__main__":
    main()
