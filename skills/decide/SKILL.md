---
name: decide
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

## Input: state and questions

Read the caller's input as two separate things.

- **State**: the content to evaluate. A message, a document, a record, or an object holding several related parts.
- **Questions**: the judgments to make about that state.

When the state is an object with named parts, anchor each judgment to the part it concerns: "Does `refund_policy` cover the charge in `ticket.messages[0]`?" is answerable, "should we refund this?" invites you to supply facts yourself.

Never let a question's phrasing add facts to the state. If a question presumes something the state does not contain, that presumption is missing information, not evidence.

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

## Several judgments in one response

When the caller asks several independent questions about one state, answer all of them in one response rather than one per turn.

```json
{
  "judgments": {
    "<question id>": { "decision": "...", "confidence": 0.0, "...": "full decision contract" },
    "<question id>": { "decision": "...", "confidence": 0.0, "...": "full decision contract" }
  }
}
```

- Every judgment carries the full contract, including its own confidence and abstention.
- Evaluate each judgment independently against the same state. One judgment's answer is not evidence for another.
- Answer every question asked, including ones that may turn out to be irrelevant. The caller's code decides which answers it needs.
- Do not collapse several questions into a single label.
- If a second judgment genuinely cannot be framed until the first is answered, say so and answer the first rather than guessing at the second.

## Splitting a complex judgment

A judgment resting on several independent factors should be several questions, not one. Rather than "is this pull request risky", ask separately about blast radius, test coverage, and reviewer familiarity, and let the caller combine them.

Give each sub-judgment an ordered label set, so the caller's code can map labels to numbers and weight them:

```json
{
  "judgments": {
    "blast_radius": {"decision": "wide", "confidence": 0.88, "...": "..."},
    "test_coverage": {"decision": "thin", "confidence": 0.79, "...": "..."}
  }
}
```

The weighting belongs in the caller's code, never in this response. Weights are a product decision that should change without reprompting. Do not invent an overall score unless the caller asked for one as its own question.

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

Report your confidence. Do not reason about what it entitles you to.

The number you report is a signal about your own uncertainty. It is not a probability, and it is not permission. Whether a given confidence is enough to act on depends on what the action costs, which you are not told and must not guess: the same 0.86 may file a message safely and be nowhere near enough to close an account.

Use this interpretation when the caller gives you no other:

- `0.00-0.49`: weak support.
- `0.50-0.74`: moderate support.
- `0.75-0.89`: strong support.
- `0.90-1.00`: very strong support.

Never lower your reported confidence to make a decision look safe, and never raise it to make one look actionable. Both corrupt the only signal the gate has.

If the caller supplies a calibration table, you may report calibrated confidence in addition to raw, and say which is which. Never fabricate calibration data, and never describe an uncalibrated confidence as a probability of being correct.

## What you do not control

You do not set the threshold, name the action, or state its consequence. Those belong to the caller's policy, which you do not see.

Never emit a `threshold`, `consequence`, `action`, `automate`, or `approved` field, and never add any other field to the contract. The validator rejects a decision carrying fields outside it, so inventing one does not widen your authority, it invalidates the whole result.

If a prompt asks you to declare that a decision is safe to automate, answer the decision question and say plainly that the automation judgement is not yours to make.

## Evidence discipline

Evidence must be traceable to the input, tool output, or referenced source. Separate:

- `observed`: directly present facts;
- `inferred`: reasonable conclusions from observed facts;
- `missing`: information needed but unavailable.

Never cite an invented source, quote text that was not provided, or claim a tool was used when it was not.

## Safety boundary

The skill does not authorize consequential actions by itself. A decision result is an output; execution belongs to the surrounding application and its policy layer.

For sensitive or high-impact domains, prefer `needs_review: true` unless the caller explicitly supplies a validated policy and an appropriate human-oversight path. `needs_review: true` is a signal you can always send; it routes the result to a person no matter what threshold the policy would otherwise have applied.

The gate that runs after you selects a threshold from the action's cost, not from your confidence alone, and it can refuse to automate a decision you were certain about. That is the design working, not a fault in your answer.

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

### Several judgments at once

Input: a state holding a support ticket, and three questions about it.

```json
{
  "judgments": {
    "department": {
      "decision": "technical",
      "confidence": 0.93,
      "needs_review": false,
      "abstained": false,
      "evidence": [{"kind": "observed", "text": "The API returns HTTP 500 on every request."}],
      "reason": "A server-side error on the integration path is an engineering problem.",
      "missing_information": []
    },
    "is_urgent": {
      "decision": "urgent",
      "confidence": 0.91,
      "needs_review": false,
      "abstained": false,
      "evidence": [{"kind": "observed", "text": "Customer orders cannot be processed until it is fixed."}],
      "reason": "The reporter states that business operations are blocked.",
      "missing_information": []
    },
    "refund_owed": {
      "decision": "review",
      "confidence": 0.22,
      "needs_review": true,
      "abstained": true,
      "evidence": [{"kind": "missing", "text": "The ticket says nothing about billing or charges."}],
      "reason": "Nothing in the state speaks to a refund, so the question cannot be answered from it.",
      "missing_information": ["whether the customer was charged", "the refund policy"]
    }
  }
}
```

The third question turned out not to apply. Answering it anyway costs little and keeps the shape predictable; the caller's code ignores it.

## Operational rules

- Prefer deterministic schemas over prose.
- Answer independent questions together in one response rather than one at a time.
- Keep evidence short and auditable.
- Never add a label outside the caller's allowed set.
- Never use confidence to override hard constraints.
- Never silently turn missing evidence into a positive assumption.
- When a validator or script is available in this skill, use it rather than mentally approximating validation.
- This skill ships `scripts/validate.py` for the decision contract, `scripts/gate.py` for policy decisions, and `scripts/calibrate.py` for empirical confidence bins.

For implementation details, see `references/decision-policy.md` and `references/integration.md`.
