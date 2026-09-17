#!/usr/bin/env python3
"""Apply a policy to a validated decision. No external dependencies.

The gate runs outside the model. A decision object cannot raise its own
threshold or declare its own consequence, because the consequence of the
action is supplied by the caller, not by the model.

Verdicts and exit codes:
  AUTOMATION_ALLOWED   0
  HUMAN_REVIEW        10
  REJECT_RESULT       20
  usage/policy error   2
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate import validate  # noqa: E402

CONSEQUENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
POLICY_REQUIRED = {"allowed_decisions", "automation_threshold", "review_below", "require_evidence"}


def validate_policy(policy):
    errors = []
    if not isinstance(policy, dict):
        return ["policy must be an object"]
    missing = POLICY_REQUIRED - policy.keys()
    if missing:
        errors.append(f"missing policy fields: {sorted(missing)}")
    extra = set(policy) - POLICY_REQUIRED - {"max_consequence"}
    if extra:
        errors.append(f"unexpected policy fields: {sorted(extra)}")
    allowed = policy.get("allowed_decisions")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(x, str) and x for x in allowed):
        errors.append("allowed_decisions must be a non-empty array of non-empty strings")
    for field in ("automation_threshold", "review_below"):
        value = policy.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append(f"{field} must be a number between 0 and 1")
    if not isinstance(policy.get("require_evidence"), bool):
        errors.append("require_evidence must be boolean")
    if "max_consequence" in policy and policy["max_consequence"] not in CONSEQUENCE_ORDER:
        errors.append(f"max_consequence must be one of {sorted(CONSEQUENCE_ORDER)}")
    if not errors and policy["review_below"] > policy["automation_threshold"]:
        errors.append("review_below must not exceed automation_threshold")
    return errors


def gate(decision, policy, consequence=None):
    """Return (verdict, reasons). Order follows references/decision-policy.md."""
    schema_errors = validate(
        decision,
        allowed_decisions=policy["allowed_decisions"],
        require_evidence=policy["require_evidence"],
    )
    if schema_errors:
        return "REJECT_RESULT", schema_errors

    if decision["abstained"]:
        return "HUMAN_REVIEW", ["the decision abstained"]
    if policy["require_evidence"] and not decision["evidence"]:
        return "HUMAN_REVIEW", ["required evidence is missing"]
    if decision["needs_review"]:
        return "HUMAN_REVIEW", ["the decision requested review"]
    if decision["confidence"] < policy["automation_threshold"]:
        return "HUMAN_REVIEW", [
            f"confidence {decision['confidence']} is below the automation threshold "
            f"{policy['automation_threshold']}"
        ]

    limit = policy.get("max_consequence")
    if limit is not None:
        if consequence is None:
            return "HUMAN_REVIEW", [
                "the policy limits consequence but the caller did not state the "
                "consequence of this action"
            ]
        if CONSEQUENCE_ORDER[consequence] > CONSEQUENCE_ORDER[limit]:
            return "HUMAN_REVIEW", [f"consequence '{consequence}' exceeds the policy limit '{limit}'"]

    return "AUTOMATION_ALLOWED", []


def main():
    parser = argparse.ArgumentParser(description="Apply a decision policy to a decision object.")
    parser.add_argument("decision", help="path to a decision JSON file")
    parser.add_argument("policy", help="path to a policy JSON file")
    parser.add_argument(
        "--consequence",
        choices=sorted(CONSEQUENCE_ORDER),
        help="consequence of the action this decision would trigger",
    )
    args = parser.parse_args()

    decision = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))

    policy_errors = validate_policy(policy)
    if policy_errors:
        print("INVALID POLICY")
        for error in policy_errors:
            print(f"- {error}")
        raise SystemExit(2)

    verdict, reasons = gate(decision, policy, args.consequence)
    print(verdict)
    for reason in reasons:
        print(f"- {reason}")
    raise SystemExit({"AUTOMATION_ALLOWED": 0, "HUMAN_REVIEW": 10, "REJECT_RESULT": 20}[verdict])


if __name__ == "__main__":
    main()
