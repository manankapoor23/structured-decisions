# Give Claude Structured Decisions

Claude writes prose. Your code needs a decision it can act on: one label from a fixed set, an explicit confidence, and an honest signal when the answer is not there.

This gives Claude that contract. Ask a question, get a decision object. A dependency-free validator checks its shape, and a policy gate decides whether the decision is allowed to trigger an action.

```text
question -> typed decision -> schema validation -> policy gate -> automation or human review
```

Claude proposes. Your code decides.

> **An experiment.** TypeSafe's Jev and other System One models answer a question with a typed value and a probability instead of prose. This skill asks how much of that *interface* a Claude Code skill can offer on its own — a fixed answer space, explicit uncertainty, no narration, nothing for your code to parse out of a paragraph — using a prompt contract, a schema, and a policy gate. It is not that kind of model, and [the comparison below](#how-this-compares-to-a-system-one-model) says where it differs.

## Quick start

```bash
git clone https://github.com/manankapoor23/typed-decision.git
mkdir -p ~/.claude/skills
cp -R typed-decision/skills/decide ~/.claude/skills/
```

Then ask Claude Code for a decision:

```text
/decide
Route this issue to one of: authentication_configuration, database, frontend,
infrastructure, review.
Issue: Login works locally but returns HTTP 401 in production.
```

```json
{"decision": "authentication_configuration", "confidence": 0.86, "needs_review": false,
 "abstained": false, "evidence": [...], "reason": "...", "missing_information": []}
```

That is the whole idea. [Usage](#usage) shows the full response and how to ask several questions at once.

## What you get

- **A label, not a paragraph.** One value from the set you allow, and nothing outside it.
- **Confidence you can threshold on.** A number, with an honest caveat about what it does and does not mean.
- **A real answer for "not enough information."** Abstention is a first-class outcome, not a hedge buried in prose.
- **Evidence you can audit.** Each observation tagged as observed, inferred, or missing.
- **Several judgments in one answer.** Ask every question you might need about the same input; your code picks the ones it uses.
- **A threshold that matches the stakes.** Per-action, per-class, or derived from measured outcomes, so filing a message and closing an account are not held to one number. The model never sees it.

## Install

Copy the skill into your Claude Code skills directory:

```bash
git clone https://github.com/manankapoor23/typed-decision.git
mkdir -p ~/.claude/skills
cp -R typed-decision/skills/decide ~/.claude/skills/
```

Claude picks the skill up on its next session. It reaches for it on its own whenever a task calls for a typed decision, and you can invoke it directly as `/decide`.

For a single project rather than every project, copy it to that project instead:

```bash
mkdir -p <your-project>/.claude/skills
cp -R typed-decision/skills/decide <your-project>/.claude/skills/
```

To update later, pull and copy again:

```bash
cd typed-decision && git pull && cp -R skills/decide ~/.claude/skills/
```

A one-command install is on the way: this repository is also a Claude Code plugin, and a community marketplace listing has passed review and is waiting to appear in the public catalog. These instructions will get shorter when it does.

### Requirements

Python 3.10 or newer for the scripts, and no third-party packages. The skill is self-contained: the validator, gate, and calibration scripts ship inside it, so a copied skill is fully functional on its own.

The commands below use `python3`, which is what macOS and most Linux distributions provide. On Windows, use `python` instead.

## Usage

Ask Claude Code for a typed decision:

```text
/decide
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
/decide
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

Run the commands in this section and the next from a clone of this repository:

```bash
git clone https://github.com/manankapoor23/typed-decision.git
cd typed-decision
```

The same scripts ship inside the installed plugin, where the skill uses them itself. Copy them into your own project when you want the validator and gate in your pipeline.


```bash
python3 skills/decide/scripts/validate.py examples/ticket-routing.json
```

Prints `VALID`, or `INVALID` with one line per problem and exit code 1.

A file holding several judgments is detected automatically, and each problem is reported against the question it came from:

```bash
python3 skills/decide/scripts/validate.py examples/batch-triage.json
```

## Apply a policy

The gate is the reason this repository exists. It runs in your code, outside the model response, so a decision cannot raise its own threshold or authorise its own action.

```bash
python3 skills/decide/scripts/gate.py \
  examples/high-confidence.json examples/policy.json --consequence low
```

| Verdict | Exit code | When |
| --- | --- | --- |
| `AUTOMATION_ALLOWED` | 0 | Valid, clears the applicable threshold, within the consequence cap |
| `HUMAN_REVIEW` | 10 | Below threshold, no threshold resolved, review requested, or too consequential |
| `ABSTAIN` | 30 | The model declined to decide; there is nothing to act on |
| `REJECT_RESULT` | 20 | Malformed, or a label outside the policy |

Only exit code 0 means automate. The codes let a shell script branch without parsing output.

### The threshold depends on what the action costs

One global threshold cannot express that missing a spam message and closing someone's account cost different amounts. Thresholds attach to the action:

```json
{
  "allowed_decisions": ["spam", "refund", "ban", "review"],
  "require_evidence": true,
  "consequence_thresholds": {"low": 0.70, "medium": 0.90, "high": 0.98},
  "actions": {
    "auto_delete":  {"consequence": "low"},
    "issue_refund": {"consequence": "medium"},
    "ban_account":  {"consequence": "high", "threshold": 0.995}
  }
}
```

The same decision at the same confidence, gated for three actions:

```bash
$ python3 skills/decide/scripts/gate.py examples/spam-decision.json examples/policy-tiered.json --action auto_delete
AUTOMATION_ALLOWED
$ python3 skills/decide/scripts/gate.py examples/spam-decision.json examples/policy-tiered.json --action issue_refund
HUMAN_REVIEW
$ python3 skills/decide/scripts/gate.py examples/spam-decision.json examples/policy-tiered.json --action ban_account
HUMAN_REVIEW
```

Those numbers are one worked example, not advice. What counts as high consequence, and what confidence it should demand, comes from your costs and your measured error rates.

### Precedence

The gate takes the first threshold that applies:

| Level | Source | From |
| --- | --- | --- |
| 1a | `action` | that action's own threshold |
| 1b | `action_consequence` | that action's consequence, via the cost ladder |
| 2 | `class` | `class_thresholds[<decision>]` |
| 3 | `calibrated` | derived from labelled outcomes |
| 4 | `global` | `automation_threshold`, the fallback |
| 5 | `unresolved` | nothing applied, so a person decides |

**Level 4 is a fallback, not the intended design.** It exists so simple policies keep working. Omit `automation_threshold` entirely and anything unresolved goes to a person, which is usually what you want.

`gate.py --json` prints which level supplied the number, alongside the raw confidence, the calibrated confidence, and the consequence, so a verdict can be audited after the fact.

### Thresholds from measured outcomes

With a calibration artifact, level 3 derives the cutoff from what actually happened rather than from a number someone picked:

```json
{
  "calibration": {
    "path": "calibration.json",
    "target_accuracy": 0.85,
    "min_samples": 30,
    "insufficient_data": "review"
  }
}
```

The threshold becomes the lowest confidence bin whose observed accuracy reached the target.

**Rare classes are the trap here.** A class with six labelled outcomes at 100% accuracy is not evidence of anything, and fitting it a threshold of its own would be the worst kind of false precision. `min_samples` sets the bar, and `insufficient_data` says what happens below it: `review` refuses to automate that class, `shrink` pulls its bin accuracies toward the global rate weighted by sample count, and `global` uses the population threshold instead. The default is `review`.

### What the caller controls, and the model does not

The action and its consequence come from the policy and the caller's arguments. The decision object has no field for either, and the validator rejects a decision that invents one. If the caller states a consequence that contradicts the policy's, the gate routes to a person rather than picking a winner.

`max_consequence` remains a hard cap: an action above it goes to a person whatever the confidence.

Full precedence rules, the calibration arithmetic, and its limitations are in [`skills/decide/references/decision-policy.md`](skills/decide/references/decision-policy.md).

## Confidence is not probability

A model reporting `0.91` does not make the answer 91 percent likely to be correct. Treat confidence as an uncertainty signal until you have measured it on representative labeled data for your own task.

```bash
python3 skills/decide/scripts/calibrate.py examples/predictions.jsonl
```

Add `--artifact` to write a file the gate can select thresholds from, grouped by class and by action:

```bash
python3 skills/decide/scripts/calibrate.py examples/predictions-labelled.jsonl \
  --artifact examples/calibration.json --min-samples 30
```

The repository ships a small example. Your own file needs one JSON object per line, each with a confidence and an outcome:

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
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Architecture

Each stage answers one question, and none of them can answer another's.

```text
user or event
     |
     v
model              proposes a decision, evidence, and its own raw confidence
     |
     v
validator          shape, types, allowed labels        -> REJECT_RESULT
     |
     v
calibration        how often was this confidence right in the past?
     |
     v
risk/cost policy   what does this action cost?
     |
     v
threshold          action -> class -> calibrated -> global fallback
     |
  +--+--+--+
  |  |  |  |
  |  |  |  +-- ABSTAIN             the model declined; nothing to act on
  |  |  +----- HUMAN_REVIEW        below threshold, or no threshold resolved
  |  +-------- AUTOMATION_ALLOWED  executor may act
  +----------- REJECT_RESULT       malformed or off-policy
```

The model contributes exactly one number to this, its raw confidence, and sees none of the rest. Collapsing any stage into the prompt gives the model authority over its own authorisation.

## Good fits

- Issue, ticket, and support routing
- Code review and pull request triage
- CI failure classification
- Incident severity triage
- Document classification
- Data quality triage
- Extraction that needs an explicit uncertainty path
- Approval workflows where the action is gated separately

## How this compares to a System One model

System One models, such as TypeSafe's Jev, are purpose-built for typed decisions. This skill borrows the interface, not the machinery. The differences are worth knowing before you pick one:

| | System One model | This skill |
| --- | --- | --- |
| What answers | a model trained for typed decisions, behind its own API | whichever model your Claude Code session is already running |
| The answer | a typed value from a fixed answer space | one label from the set you allow |
| Uncertainty | a probability distribution over the answer space, with confidence derived from its shape | one number the model reports about itself |
| Calibration | trained against outcomes | unmeasured until you measure it, with `calibrate.py` |
| Narration | none by design | `reason` and `evidence` are required fields |
| Answer types | several shapes, including ordered levels and yes/no probabilities | a single label per judgment |
| Many questions | independent questions evaluated together against one state | several judgments in one response |
| Gating | your code | your code, with `gate.py` |

So: use a purpose-built decision model when you need calibrated probabilities, a probability distribution rather than a single answer, or tight control over latency, cost, and determinism. Use this when you are already working in Claude Code and want the contract, the abstention path, and the gate without adding a dependency.

The required `reason` and `evidence` fields are a deliberate departure. A model that returns a distribution does not need to explain itself, because the distribution *is* the uncertainty. A language model reporting a single number does need to, so the contract makes it show its work and keeps that work auditable.

This project is independent. It is not affiliated with, endorsed by, sponsored by, or derived from TypeSafe or any other decision model vendor, and it makes no claim about how its accuracy, calibration, latency, or cost compares to theirs. Jev and System One are referred to here only to describe what this skill is and is not.

## Repository layout

```text
.claude-plugin/
  plugin.json          plugin manifest
  marketplace.json     marketplace manifest, kept ready for the plugin install
skills/decide/
  SKILL.md             the decision contract and procedure
  references/
    decision-policy.md
    integration.md
  scripts/
    validate.py
    thresholds.py      threshold precedence and calibration arithmetic
    gate.py
    calibrate.py
schemas/
  decision.schema.json
  judgments.schema.json
  policy.schema.json
  calibration.schema.json
examples/
  ticket-routing.json
  high-confidence.json
  ambiguous.json
  batch-triage.json
  policy.json
  policy-urgency.json
  policy-tiered.json
  spam-decision.json
  calibration.json
  predictions.jsonl
  predictions-labelled.jsonl
tests/
  _load.py
  test_validator.py
  test_gate.py
  test_thresholds.py
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
