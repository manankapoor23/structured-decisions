---
name: typed-decision
description: Produces machine-actionable typed decisions with explicit uncertainty, evidence, abstention, and validation. Use when a task requires classification, routing, triage, approval, risk assessment, policy checks, structured choices, or any decision that downstream code may execute.
---

# Typed Decision Engine

Treat the task as a decision problem, not a prose-generation problem. The goal is a compact, schema-valid result that software can consume safely.

## Core contract

Every decision should have:

- `decision`: one allowed value from the caller's decision set.
- `confidence`: a number from 0 to 1 representing model-reported confidence, not a calibrated probability unless calibration data is available.
- `needs_review`: whether a human should inspect the result before consequential action.
- `evidence`: concise observations supporting the decision.
- `reason`: a short explanation of how the evidence maps to the decision.
- `abstained`: whether the engine declined to make a substantive decision.

If the caller provides a schema, decision labels, thresholds, or policy, those constraints override this default contract.

## Decision procedure

1. Parse the question into:
   - input facts
   - candidate decisions
   - hard constraints
   - consequences of being wrong
   - required output schema
2. Identify the evidence actually present. Do not invent missing facts.
3. Compare the candidate decisions against the evidence.
4. Select the best-supported allowed decision, or abstain when the evidence is insufficient or contradictory.
5. Estimate confidence conservatively.
6. Apply the review policy:
   - low confidence -> review
   - high-impact decision -> review unless the caller explicitly provides a safe automation threshold
   - conflicting evidence -> review
   - missing required evidence -> review or abstain
7. Return only schema-valid structured output when structured output is requested.

## Abstention

Abstention is a first-class outcome. Prefer uncertainty over fabricated certainty.

Use `abstained: true` when:

- no candidate decision is supported by the available evidence;
- required information is missing;
- the input is outside the decision domain;
- candidate labels are ambiguous;
- the consequences are high and the caller has not supplied an acceptable automation policy.

When abstaining, set `needs_review: true` and explain what information would resolve the uncertainty.

## Confidence policy

Do not present confidence as statistical probability unless it has been empirically calibrated.

Use this interpretation by default:

- `0.00-0.49`: weak support; review.
- `0.50-0.74`: moderate support; review.
- `0.75-0.89`: strong support; review for consequential actions.
- `0.90-1.00`: very strong support; automation is still subject to the caller's policy.

If a calibration table is provided, use it to convert raw confidence into calibrated confidence and label the field accordingly. Never fabricate calibration data.

## Evidence discipline

Evidence must be traceable to the input, tool output, or referenced source. Separate:

- `observed`: directly present facts;
- `inferred`: reasonable conclusions from observed facts;
- `missing`: information needed but unavailable.

Never cite an invented source, quote text that was not provided, or claim a tool was used when it was not.

## Safety boundary

The skill does not authorize consequential actions by itself. A decision result is an output; execution belongs to the surrounding application and its policy layer.

For sensitive or high-impact domains, prefer `needs_review: true` unless the caller explicitly supplies a validated policy and an appropriate human-oversight path.

## Output shape

Use this default shape when no caller schema exists:

```json
{
  "decision": "<allowed label>",
  "confidence": 0.0,
  "needs_review": true,
  "abstained": false,
  "evidence": [
    {"kind": "observed", "text": "..."}
  ],
  "reason": "...",
  "missing_information": []
}
```

If the caller asks for a different schema, satisfy that schema instead.

## Examples

### Ticket routing

Input: `401 only in production; login works locally.`

```json
{
  "decision": "authentication_configuration",
  "confidence": 0.86,
  "needs_review": false,
  "abstained": false,
  "evidence": [
    {"kind": "observed", "text": "Authentication succeeds locally."},
    {"kind": "observed", "text": "Production returns HTTP 401."}
  ],
  "reason": "The environment-specific 401 points to production authentication configuration or credentials.",
  "missing_information": []
}
```

### Ambiguous classification

Input: `Route this issue: 'It stopped working after the update.'`

```json
{
  "decision": "review",
  "confidence": 0.34,
  "needs_review": true,
  "abstained": true,
  "evidence": [
    {"kind": "observed", "text": "The report only says the system stopped working after an update."}
  ],
  "reason": "There is not enough information to identify the failing subsystem or route safely.",
  "missing_information": ["error message", "affected component", "environment"]
}
```

## Operational rules

- Prefer deterministic schemas over prose.
- Keep evidence short and auditable.
- Never add a label outside the caller's allowed set.
- Never use confidence to override hard constraints.
- Never silently turn missing evidence into a positive assumption.
- When a validator or script is available in this skill, use it rather than mentally approximating validation.
- This skill ships `scripts/validate.py` for the decision contract, `scripts/gate.py` for policy decisions, and `scripts/calibrate.py` for empirical confidence bins.

For implementation details, see `references/decision-policy.md` and `references/integration.md`.
