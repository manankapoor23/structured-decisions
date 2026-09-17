# Decision Policy Reference

## Separation of concerns

1. **Reasoner** — produces a candidate decision and evidence.
2. **Schema validator** — verifies shape, types, and allowed labels.
3. **Policy gate** — decides whether automation is permitted.
4. **Executor** — performs the real-world action outside the skill.

Never collapse these layers into one prompt.

## Recommended policy

```json
{"allowed_decisions":["approve","reject","review"],"automation_threshold":0.90,"review_below":0.90,"max_consequence":"medium","require_evidence":true}
```

Generic gate:

```text
if schema_invalid: reject_result
elif abstained: human_review
elif missing_required_evidence: human_review
elif confidence < automation_threshold: human_review
elif consequence > allowed_consequence: human_review
else: automation_allowed
```

The threshold is a product decision, not a model capability claim.

## Calibration

Collect representative labeled predictions, bucket raw confidence, compute empirical accuracy, fit a calibration method if appropriate, evaluate on a separate validation set, and version the calibration artifact with the task/domain/model version. Do not reuse calibration data across materially different domains without validation.

## Implementation

`scripts/gate.py` implements the gate above. `validate_policy` checks the policy document, and `gate(decision, policy, consequence)` returns a verdict with the reasons behind it. A policy whose `review_below` exceeds its `automation_threshold` is rejected as contradictory.
