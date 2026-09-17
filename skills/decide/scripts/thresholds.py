#!/usr/bin/env python3
"""Select an automation threshold for one decision. No external dependencies.

This module is the risk/cost layer. It answers one question: given a policy,
the class the model chose, and the action the caller intends to take, what
confidence is required before automating, and where did that number come from?

It never reads a threshold, an action, or a consequence from the decision
object. Those come from the policy and the caller, so a model cannot raise its
own permission by writing a field.

Precedence, first match wins:

  1a. actions[<action>].threshold          explicit per-action threshold
  1b. consequence_thresholds[<level>]      per-action, via the action's cost
  2.  class_thresholds[<class>]            explicit per-class threshold
  3.  calibration                          derived from labelled outcomes
  4.  automation_threshold                 global fallback, least preferred
  5.  nothing applies                      unresolved, caller must review

Level 4 exists for compatibility with simple policies. It is a fallback, not
the intended way to run this: one number cannot express that missing a spam
message and banning an account cost different amounts.

Calibration, and what it does not promise:

  A calibration artifact records, per group, how often decisions in each raw
  confidence bin turned out correct. A threshold derived from it is the lowest
  bin edge whose observed accuracy reached the policy's target.

  This is an empirical summary of past outcomes, not a probability, and not a
  guarantee about the next decision. Limitations, in the order they bite:

  - The bins are counts. A bin holding 11 rows says little, and this module
    cannot tell you how little: no confidence intervals are computed.
  - Choosing the cutoff from the same rows used to measure accuracy is
    in-sample selection, so the accuracy achieved in production is expected to
    be lower than the target. Measure on rows the threshold was not chosen
    from.
  - Outcomes drift. A calibration artifact is only as current as the model,
    prompt, and input distribution it was collected under.
  - Shrinkage below is a variance-reduction heuristic, not an estimator with a
    stated risk bound.

Thresholds and confidence are compared in one space: raw model confidence.
Calibration moves the cutoff; it does not rewrite the confidence being
compared. Calibrated confidence is reported alongside the verdict so the gap
between claimed and observed accuracy stays visible, but it is deliberately
not substituted into the comparison, which would apply the same correction
twice.
"""
from dataclasses import dataclass, field

CONSEQUENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
INSUFFICIENT_DATA_STRATEGIES = {"review", "shrink", "global"}
DEFAULT_MIN_SAMPLES = 30
DEFAULT_SHRINKAGE_WEIGHT = 30
DEFAULT_INSUFFICIENT_DATA = "review"


@dataclass
class Resolution:
    """The threshold to apply, and an audit trail for how it was chosen."""

    threshold: float | None
    source: str
    notes: list[str] = field(default_factory=list)
    group: str | None = None
    sample_count: int | None = None
    calibrated_confidence: float | None = None

    @property
    def resolved(self):
        return self.threshold is not None


def _calibration_config(policy):
    cfg = dict(policy.get("calibration") or {})
    cfg.setdefault("min_samples", DEFAULT_MIN_SAMPLES)
    cfg.setdefault("shrinkage_weight", DEFAULT_SHRINKAGE_WEIGHT)
    cfg.setdefault("insufficient_data", DEFAULT_INSUFFICIENT_DATA)
    return cfg


def bin_for(confidence, bins):
    """The bin a raw confidence falls in. Upper edge belongs to the last bin."""
    last = len(bins) - 1
    for index, b in enumerate(bins):
        if b["lower"] <= confidence < b["upper"] or (index == last and confidence == b["upper"]):
            return b
    return None


def _group(calibration, key):
    groups = (calibration or {}).get("groups") or {}
    return groups.get(key)


def select_group(calibration, class_label, action):
    """Most specific group first: action+class, then class, then global."""
    for key in (f"{action}:{class_label}" if action else None, class_label, "global"):
        if key is None:
            continue
        group = _group(calibration, key)
        if group is not None:
            return key, group
    return None, None


def shrink_bins(class_bins, global_bins, weight):
    """Pull each bin's accuracy toward the same bin measured globally.

    shrunk = (n * class_accuracy + weight * global_accuracy) / (n + weight)

    A bin with many observations barely moves; a bin with two observations
    ends up close to the global rate. `weight` is the number of global
    observations each class bin is treated as starting with. This trades bias
    for variance on purpose. It is a heuristic, not an estimator with a proven
    risk bound, and it assumes the class behaves like the population in the
    absence of evidence, which is exactly what a rare class cannot confirm.
    """
    by_edge = {(b["lower"], b["upper"]): b for b in global_bins}
    out = []
    for b in class_bins:
        peer = by_edge.get((b["lower"], b["upper"]))
        if peer is None:
            # Nothing to shrink toward, so this bin keeps whatever noise it has.
            # Dropping it is the conservative choice: a bin of two observations
            # must not be allowed to set a threshold on its own.
            continue
        n = b["count"]
        shrunk = (n * b["empirical_accuracy"] + weight * peer["empirical_accuracy"]) / (n + weight)
        out.append(dict(b, empirical_accuracy=round(shrunk, 6), shrunk=True))
    return out


def threshold_from_bins(bins, target_accuracy):
    """Lowest bin edge whose observed accuracy reached the target.

    Returns None when no bin did, which means the data does not support
    automating this group at that target.
    """
    for b in sorted(bins, key=lambda x: x["lower"]):
        if b["count"] and b["empirical_accuracy"] >= target_accuracy:
            return b["lower"]
    return None


def calibrated_confidence(raw, bins):
    """Observed accuracy of the bin this raw confidence falls in."""
    b = bin_for(raw, bins or [])
    return None if b is None else b["empirical_accuracy"]


def _calibrated_threshold(policy, class_label, action, calibration, raw_confidence):
    """Level 3. Returns a Resolution, or None to fall through to level 4."""
    cfg = _calibration_config(policy)
    target = cfg.get("target_accuracy")
    if calibration is None or target is None:
        return None

    key, group = select_group(calibration, class_label, action)
    if group is None:
        return Resolution(
            None, "unresolved",
            [f"calibration holds no group for '{class_label}' and no global group"],
        )

    count = group.get("count", 0)
    minimum = cfg["min_samples"]
    bins = group.get("bins") or []
    notes = []

    if count < minimum and key == "global":
        # Nothing to fall back to: if the population itself is thin, there is no
        # group whose accuracy is worth deriving a cutoff from.
        return Resolution(
            None, "unresolved",
            [f"the global group has {count} labelled outcomes, below the minimum of {minimum}"],
            group=key, sample_count=count,
            calibrated_confidence=calibrated_confidence(raw_confidence, bins),
        )

    if count < minimum:
        strategy = cfg["insufficient_data"]
        global_group = _group(calibration, "global")
        if strategy == "review":
            return Resolution(
                None, "unresolved",
                [f"group '{key}' has {count} labelled outcomes, below the minimum of "
                 f"{minimum}, and insufficient_data is 'review'"],
                group=key, sample_count=count,
            )
        if strategy == "global":
            if global_group is None:
                return Resolution(
                    None, "unresolved",
                    [f"group '{key}' has {count} outcomes, below {minimum}, and there is "
                     "no global group to fall back to"],
                    group=key, sample_count=count,
                )
            notes.append(
                f"group '{key}' has {count} outcomes, below {minimum}; using the global "
                "group instead"
            )
            key, group, count, bins = "global", global_group, global_group.get("count", 0), global_group.get("bins") or []
        elif strategy == "shrink":
            if global_group is None:
                return Resolution(
                    None, "unresolved",
                    [f"group '{key}' has {count} outcomes, below {minimum}, and there is "
                     "no global group to shrink toward"],
                    group=key, sample_count=count,
                )
            bins = shrink_bins(bins, global_group.get("bins") or [], cfg["shrinkage_weight"])
            notes.append(
                f"group '{key}' has {count} outcomes, below {minimum}; its accuracies were "
                f"shrunk toward the global rate with weight {cfg['shrinkage_weight']}"
            )

    derived = threshold_from_bins(bins, target)
    if derived is None:
        return Resolution(
            None, "unresolved",
            notes + [f"no confidence bin in group '{key}' reached the target accuracy {target}"],
            group=key, sample_count=count,
            calibrated_confidence=calibrated_confidence(raw_confidence, bins),
        )
    return Resolution(
        derived, "calibrated",
        notes + [f"threshold {derived} derived from group '{key}' at target accuracy {target}"],
        group=key, sample_count=count,
        calibrated_confidence=calibrated_confidence(raw_confidence, bins),
    )


def resolve_threshold(policy, class_label, action=None, calibration=None, raw_confidence=None):
    """Apply the precedence order. See the module docstring."""
    actions = policy.get("actions") or {}
    ladder = policy.get("consequence_thresholds") or {}

    # 1a and 1b: the action the caller intends to take.
    if action is not None and action in actions:
        entry = actions[action] or {}
        if "threshold" in entry:
            return Resolution(
                entry["threshold"], "action",
                [f"threshold {entry['threshold']} set for action '{action}'"],
            )
        level = entry.get("consequence")
        if level is not None and level in ladder:
            return Resolution(
                ladder[level], "action_consequence",
                [f"action '{action}' is {level} consequence, which requires {ladder[level]}"],
            )

    # 2: the class the model chose.
    class_thresholds = policy.get("class_thresholds") or {}
    if class_label in class_thresholds:
        return Resolution(
            class_thresholds[class_label], "class",
            [f"threshold {class_thresholds[class_label]} set for class '{class_label}'"],
        )

    # 3: what the labelled outcomes support.
    calibrated = _calibrated_threshold(policy, class_label, action, calibration, raw_confidence)
    if calibrated is not None:
        return calibrated

    # 4: the global fallback.
    if "automation_threshold" in policy:
        return Resolution(
            policy["automation_threshold"], "global",
            [f"no action, class, or calibrated threshold applied; using the global "
             f"fallback {policy['automation_threshold']}"],
        )

    # 5: nothing applies.
    return Resolution(
        None, "unresolved",
        ["the policy sets no applicable threshold for this decision"],
    )
