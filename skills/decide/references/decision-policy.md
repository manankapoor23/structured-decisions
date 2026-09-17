# Decision Policy Reference

## Separation of concerns

1. **Reasoner** — produces a candidate decision and evidence.
2. **Schema validator** — verifies shape, types, and allowed labels.
3. **Calibration** — reports how often past decisions at a confidence were right.
4. **Policy gate** — selects a threshold from risk and cost, and rules.
5. **Executor** — performs the real-world action outside the skill.

Never collapse these layers into one prompt. In particular, the model never sees and never sets the threshold, the action, or the action's consequence. Those live in the policy and in the caller's arguments, so a model cannot widen its own authority by writing a field. The validator rejects any decision carrying fields outside the contract, which is what enforces this.

## Threshold precedence

The gate asks one question: what confidence does *this* decision, driving *this* action, have to clear? It answers in a fixed order and takes the first that applies.

| Level | Source | Where it comes from |
| --- | --- | --- |
| 1a | `action` | `actions[<action>].threshold` |
| 1b | `action_consequence` | `consequence_thresholds[actions[<action>].consequence]` |
| 2 | `class` | `class_thresholds[<decision>]` |
| 3 | `calibrated` | derived from labelled outcomes for the most specific matching group |
| 4 | `global` | `automation_threshold` |
| 5 | `unresolved` | nothing applied, so a person decides |

Level 4 exists so that policies written against the first version of this schema keep working. It is a fallback, not the intended design. One number cannot express that missing a spam message and closing someone's account cost different amounts, which is the entire reason the levels above it exist.

Level 5 is not a failure mode to engineer around. A policy that cannot say what confidence an action requires has not authorised that action, and the gate says so rather than guessing.

## Cost, not class identity

A threshold belongs to what the decision will *do*, not to what it is called. The same `spam` classification at the same confidence can be safe to act on when the action files a message, and unsafe when the action closes an account.

Declare the actions and what each costs:

```json
{
  "consequence_thresholds": {"low": 0.70, "medium": 0.90, "high": 0.98},
  "actions": {
    "auto_delete":  {"consequence": "low"},
    "issue_refund": {"consequence": "medium"},
    "ban_account":  {"consequence": "high", "threshold": 0.995}
  }
}
```

These numbers are one worked example, not recommendations. What counts as high consequence, and what confidence it should demand, is yours to decide from your own costs and your own measured error rates.

Two rules keep a cost ladder honest, both enforced at validation time:

- The ladder must not decrease as consequence rises. A costlier action cannot require less confidence.
- An action that names a consequence but sets no threshold of its own must have a ladder entry for that level. Otherwise declaring a cost would silently leave the action on the global fallback, which is the opposite of what declaring it meant.

`max_consequence` is separate from all of this. It is a hard cap: an action above it goes to a person whatever the confidence, and whatever the threshold resolution said.

## Consequence comes from the caller

The consequence of an action is supplied by the caller, as `--consequence`, or read from the policy's own `actions` entry. It is never a field on the decision.

If the caller states one and the policy declares another, the gate does not pick a winner. It routes to a person, because two parts of the system disagree about what is at stake.

If a policy sets `max_consequence` and neither source states a consequence, the gate routes to a person rather than assuming the action is cheap.

## Calibration

`scripts/calibrate.py --artifact` turns labelled outcomes into per-group observed accuracy. Groups are keyed `global`, `<class>`, and `<action>:<class>`, and the gate prefers the most specific group that exists.

A calibrated threshold is the lowest confidence bin whose observed accuracy reached `calibration.target_accuracy`.

### Rare classes

A class with nine labelled outcomes cannot support a threshold of its own, however clean those nine look. `calibration.min_samples` sets the bar, and `calibration.insufficient_data` says what happens when a group is under it:

- `review` (default) — do not automate this group. The most conservative choice, and the right one when you have no reason to believe the rare class behaves like the population.
- `shrink` — pull each of the group's bin accuracies toward the same bin measured globally, weighted by `shrinkage_weight`, then derive the threshold from the shrunk curve. A bin with many observations barely moves; a thin one ends up near the global rate. A class bin with no global counterpart is dropped rather than trusted, since there is nothing to shrink it toward.
- `global` — use the global group's threshold for this class.

`shrink` trades bias for variance deliberately. It assumes the rare class behaves like the population in the absence of evidence to the contrary, which is exactly the thing a rare class cannot confirm. Prefer `review` unless you have a reason to believe that assumption.

### What calibration does not establish

- Observed accuracy is a count of past outcomes, not a probability, and nothing here computes a confidence interval or reports significance.
- Selecting a cutoff from the same rows used to measure accuracy is in-sample selection. Accuracy in production will tend to fall short of the target. Measure on rows the threshold was not chosen from.
- An artifact is only as current as the model, prompt, and input distribution it was collected under. Outcomes drift; re-measure.
- Nothing here gives a coverage or error guarantee of any kind.

### Raw and calibrated confidence

Thresholds and confidence are compared in one space: raw model confidence. Calibration moves the cutoff; it does not rewrite the number being compared. Calibrated confidence is reported alongside every verdict, so the gap between what the model claimed and what was observed stays visible, but it is deliberately not substituted into the comparison, which would apply the same correction twice.

## Gate order

```text
if schema invalid or label off-policy:        REJECT_RESULT
elif abstained:                               ABSTAIN
elif evidence required and absent:            HUMAN_REVIEW
elif the decision asked for review:           HUMAN_REVIEW
elif the action is not described by policy:   HUMAN_REVIEW
elif caller and policy disagree on cost:      HUMAN_REVIEW
elif consequence exceeds max_consequence:     HUMAN_REVIEW
elif no threshold resolves:                   HUMAN_REVIEW
elif confidence < threshold:                  HUMAN_REVIEW
else:                                         AUTOMATION_ALLOWED
```

Shape is a contract question and a malformed result is rejected. Whether there is enough evidence to act is a policy question, and a person can answer it, so it routes to review rather than rejection.

Only `AUTOMATION_ALLOWED` means automate. `ABSTAIN` is reported separately from `HUMAN_REVIEW` because the two mean different things to whoever is on the other end: one is a decision that needs checking, the other is the absence of a decision.

## Implementation

`scripts/thresholds.py` holds the precedence order and the calibration arithmetic. `scripts/gate.py` holds the verdicts, `validate_policy` for the policy document, and `validate_calibration` for the artifact. `explain(decision, policy, consequence, action, calibration)` returns the verdict, the reasons, and the audit trail, including which level supplied the threshold; `gate(...)` returns the first two. `gate.py --json` prints the whole trail.
