# Typed Decision Skill for Claude Code

A Claude Code Skill that turns open-ended model responses into typed, auditable decisions that software can act on.

The skill asks the model for a decision object instead of prose. A dependency-free validator checks its shape, and a policy gate decides whether that decision is allowed to trigger an action.

```text
question -> typed decision -> schema validation -> policy gate -> automation or human review
```

The model proposes. Your application decides.

## Why

Language models are optimized to produce text for people. Production systems usually need something narrower: a stable label, an explicit uncertainty signal, a path for "not enough information", and a gate that keeps a low-confidence answer from reaching a consequential action.

This skill provides the contract and the gate. It does not perform the action.

## Requirements

Python 3.10 or newer. No third-party packages, and nothing to install with pip.

## Install

Clone the repository, then copy the skill into whichever scope you want.

```bash
git clone https://github.com/manankapoor23/typed-decision-skill.git
cd typed-decision-skill
```

For one project:

```bash
mkdir -p /path/to/your/project/.claude/skills
cp -R .claude/skills/typed-decision /path/to/your/project/.claude/skills/
```

For every project on your machine:

```bash
mkdir -p ~/.claude/skills
cp -R .claude/skills/typed-decision ~/.claude/skills/
```

Claude Code discovers skills from `.claude/skills/` in a project and `~/.claude/skills/` for a personal install. The skill is self-contained: the validator, gate, and calibration scripts ship inside it, and none of them require third-party packages.

## Usage

Ask Claude Code for a typed decision:

```text
Use the typed decision skill.
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
python .claude/skills/typed-decision/scripts/validate.py examples/ticket-routing.json
```

Prints `VALID`, or `INVALID` with one line per problem and exit code 1.

## Apply a policy

The gate is the reason this repository exists. It runs in your code, outside the model response, so a decision cannot raise its own threshold or authorize its own action.

```bash
python .claude/skills/typed-decision/scripts/gate.py \
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

The threshold is a product decision, not a claim about model accuracy. Gate different actions at different levels according to what being wrong costs.

## Confidence is not probability

A model reporting `0.91` does not make the answer 91 percent likely to be correct. Treat confidence as an uncertainty signal until you have measured it on representative labeled data for your own task.

```bash
python .claude/skills/typed-decision/scripts/calibrate.py predictions.jsonl
```

Each line needs a confidence and an outcome:

```json
{"confidence":0.91,"correct":true}
```

The output gives you mean confidence against empirical accuracy per bin, which is what tells you whether 0.9 means anything in your domain.

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
.claude/skills/typed-decision/
  SKILL.md
  references/
    decision-policy.md
    integration.md
  scripts/
    validate.py
    gate.py
    calibrate.py
schemas/
  decision.schema.json
  policy.schema.json
examples/
  ticket-routing.json
  high-confidence.json
  ambiguous.json
  policy.json
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
