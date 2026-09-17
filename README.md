# Give Claude Structured Decisions

Claude writes prose. Your code needs a decision it can act on: one label from a fixed set, an explicit confidence, and an honest signal when the answer is not there.

This gives Claude that contract. Ask a question, get a decision object. A dependency-free validator checks its shape, and a policy gate decides whether the decision is allowed to trigger an action.

```text
question -> typed decision -> schema validation -> policy gate -> automation or human review
```

Claude proposes. Your code decides.

## What you get

- **A label, not a paragraph.** One value from the set you allow, and nothing outside it.
- **Confidence you can threshold on.** A number, with an honest caveat about what it does and does not mean.
- **A real answer for "not enough information."** Abstention is a first-class outcome, not a hedge buried in prose.
- **Evidence you can audit.** Each observation tagged as observed, inferred, or missing.
- **Several judgments in one answer.** Ask every question you might need about the same input; your code picks the ones it uses.
- **A gate you control.** Thresholds and consequence limits live in your code, where the model cannot reach them.

## Why

Language models are optimized to produce text for people. Production systems usually need something narrower: a stable label, an explicit uncertainty signal, a path for "not enough information", and a gate that keeps a low-confidence answer from reaching a consequential action.

You get the contract and the gate. Your code still performs the action.

## Install

### Plugin (recommended)

Two commands inside Claude Code:

```text
/plugin marketplace add manankapoor23/structured-decisions
/plugin install typed-decision@manan-skills
```

Claude then reaches for the skill on its own whenever a task calls for a typed decision, and you can invoke it directly as `/typed-decision:decide`. Later releases arrive with:

```text
/plugin update typed-decision@manan-skills
```

### Copy the skill instead

If you would rather not add a marketplace:

```bash
git clone https://github.com/manankapoor23/structured-decisions.git
mkdir -p ~/.claude/skills
cp -R structured-decisions/skills/decide ~/.claude/skills/
```

The skill is then available as `/decide` everywhere. Use `<your-project>/.claude/skills` instead of `~/.claude/skills` to scope it to a single project. This route does not receive updates.

### Requirements

Python 3.10 or newer for the scripts, and no third-party packages. The skill is self-contained: the validator, gate, and calibration scripts ship inside it, so an installed copy is fully functional on its own.

## Usage

Ask Claude Code for a typed decision:

```text
/typed-decision:decide
Route this issue to one of: authentication_configuration, database, frontend,
infrastructure, review.

Issue: Login works locally but returns HTTP 401 in production.
Return the decision object only.
```

Result:

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

### Ask several questions at once

When you have more than one question about the same input, ask them together. Each judgment is answered independently and carries its own confidence and abstention.

```text
/typed-decision:decide
State: the support ticket below.
Questions:
- department: one of infrastructure, database, frontend, authentication_configuration, review
- is_urgent: one of urgent, not_urgent
- refund_owed: one of refund, no_refund, review

Ticket: Our API has returned HTTP 500 on every request for 20 minutes and we
cannot process customer orders. No deploy went out today.
```

```json
{
  "judgments": {
    "department": {"decision": "infrastructure", "confidence": 0.93, "...": "..."},
    "is_urgent": {"decision": "urgent", "confidence": 0.95, "...": "..."},
    "refund_owed": {"decision": "review", "confidence": 0.21, "abstained": true, "...": "..."}
  }
}
```

The third question did not apply to this ticket, and the skill abstained rather than inventing an answer. Asking it anyway costs almost nothing and keeps the response shape predictable.

Keep the input's content separate from the questions you ask about it. When the content is an object with named parts, name the part each question concerns, so a judgment is anchored to evidence instead of to your phrasing.

A judgment that rests on several independent factors should be several questions. Rather than asking "is this pull request risky", ask about blast radius, test coverage, and reviewer familiarity, give each an ordered label set, and weight them in your own code where the weights can change without reprompting.

## The decision contract

| Field | Type | Meaning |
| --- | --- | --- |
| `decision` | string | One label from the caller's allowed set |
| `confidence` | number, 0 to 1 | Model-reported confidence, not a calibrated probability |
| `needs_review` | boolean | Whether a person should inspect the result first |
| `abstained` | boolean | Whether the model declined to decide |
| `evidence` | array | `{kind: observed \| inferred \| missing, text}` entries traceable to the input |
| `reason` | string | How the evidence maps to the decision |
| `missing_information` | array of strings | What would resolve the remaining uncertainty |

Abstention is a first-class outcome. An abstained decision must also set `needs_review` and name what is missing; the validator enforces both.

## Validate a decision

```bash
python skills/decide/scripts/validate.py examples/ticket-routing.json
```

Prints `VALID`, or `INVALID` with one line per problem and exit code 1.

A file holding several judgments is detected automatically, and each problem is reported against the question it came from:

```bash
python skills/decide/scripts/validate.py examples/batch-triage.json
```

## Apply a policy

The gate is the reason this repository exists. It runs in your code, outside the model response, so a decision cannot raise its own threshold or authorize its own action.

```bash
python skills/decide/scripts/gate.py \
  examples/high-confidence.json examples/policy.json --consequence low
```

A policy looks like this:

```json
{
  "allowed_decisions": ["authentication_configuration", "database", "frontend", "infrastructure", "review"],
  "automation_threshold": 0.90,
  "review_below": 0.90,
  "max_consequence": "medium",
  "require_evidence": true
}
```

| Verdict | Exit code | When |
| --- | --- | --- |
| `AUTOMATION_ALLOWED` | 0 | Valid, confident, within the consequence limit |
| `HUMAN_REVIEW` | 10 | Abstained, review requested, below threshold, or too consequential |
| `REJECT_RESULT` | 20 | Malformed, or a label outside the policy |

The exit codes let a shell script branch on the verdict without parsing output.

The consequence of the action is a `--consequence` argument supplied by the caller, never a field in the decision object. If a policy sets `max_consequence` and the caller does not state the consequence, the gate returns `HUMAN_REVIEW` rather than assuming the action is safe.

To gate one judgment out of a batch, name it:

```bash
python skills/decide/scripts/gate.py \
  examples/batch-triage.json examples/policy.json --judgment department --consequence low
```

A policy describes one question's answer space, so a batch needs one policy per question. Gating the urgency judgment against the routing policy above returns `REJECT_RESULT`, because `urgent` is not one of the routing labels. That is the intended behavior: it catches a decision that was gated against the wrong policy.

The threshold is a product decision, not a claim about model accuracy. Gate different actions at different levels according to what being wrong costs.

## Confidence is not probability

A model reporting `0.91` does not make the answer 91 percent likely to be correct. Treat confidence as an uncertainty signal until you have measured it on representative labeled data for your own task.

```bash
python skills/decide/scripts/calibrate.py predictions.jsonl
```

Each line needs a confidence and an outcome:

```json
{"confidence":0.91,"correct":true}
```

The output gives mean confidence against empirical accuracy for each bin, then a summary:

```json
{"summary": {"count": 200, "mean_confidence": 0.7208, "accuracy": 0.645, "ece": 0.1087, "brier": 0.2326, "bins_populated": 5}}
```

`ece` is the expected calibration error, the count-weighted average gap between confidence and accuracy; `brier` is the mean squared error of the confidence values. Lower is better for both. An `ece` near zero means confidence tracks accuracy across groups of predictions, which is the only sense in which it can be trusted. It still says nothing about whether any single answer is right.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Architecture

```text
user or event
     |
     v
model            proposes a decision and its evidence
     |
     v
validator        shape, types, and allowed labels
     |
     v
policy gate      threshold, consequence, evidence requirement
     |
  +--+--+
  |     |
review  automation
  |     |
person  executor
```

Keep these layers separate. Collapsing the gate into the prompt gives the model authority over its own authorization.

## Good fits

- Issue, ticket, and support routing
- Code review and pull request triage
- CI failure classification
- Incident severity triage
- Document classification
- Data quality triage
- Extraction that needs an explicit uncertainty path
- Approval workflows where the action is gated separately

## When to use a purpose-built decision model instead

This skill is for the case where an LLM is the only model you have. It gets you a stable contract, an abstention path, and a gate.

Purpose-built decision models take a different approach: they separate the content being evaluated from the questions asked about it, answer several independent questions in one call, and return a probability distribution over a fixed answer space rather than a self-reported number. TypeSafe's Jev is one such model. If you need calibrated probabilities, many judgments per request, or tight latency and cost control, evaluate a dedicated model or an evaluation pipeline instead of this skill.

This project is independent and not affiliated with, endorsed by, or derived from any decision model vendor.

## Repository layout

```text
.claude-plugin/
  plugin.json          plugin manifest
  marketplace.json     marketplace manifest, so the repo installs with /plugin
skills/decide/
  SKILL.md             the decision contract and procedure
  references/
    decision-policy.md
    integration.md
  scripts/
    validate.py
    gate.py
    calibrate.py
schemas/
  decision.schema.json
  judgments.schema.json
  policy.schema.json
examples/
  ticket-routing.json
  high-confidence.json
  ambiguous.json
  batch-triage.json
  policy.json
  policy-urgency.json
tests/
  test_validator.py
  test_gate.py
```

## Roadmap

- Pydantic validator adapter
- TypeScript and Zod validator adapter
- Platt and isotonic calibration
- JSONL batch runner
- Worked examples for issue triage, pull request risk, and CI failures

## Contributing

See `CONTRIBUTING.md`. Include a reproducible example and tests for any change to validation or policy behavior.

## License

MIT. See `LICENSE`.
