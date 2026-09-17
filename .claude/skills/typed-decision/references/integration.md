# Integration Patterns

Project skill:

```text
.claude/skills/typed-decision/SKILL.md
```

Personal skill:

```text
~/.claude/skills/typed-decision/SKILL.md
```

For applications, use the skill as the behavioral contract and enforce the schema in application code. If the model API supports structured outputs, use constrained JSON output in addition to prompt instructions.

Recommended flow:

```text
request -> model -> typed decision JSON -> schema validation -> policy gate -> human review OR executor
```

The policy gate should live outside the model response so the model cannot lower its own threshold or authorize an action merely by changing a field.

## Scripts shipped with the skill

```text
scripts/validate.py   shape, type, and allowed-label validation
scripts/gate.py       policy gate returning AUTOMATION_ALLOWED, HUMAN_REVIEW, or REJECT_RESULT
scripts/calibrate.py  empirical confidence bins from labeled predictions
```

Call `gate.py` from application code, or import `gate(decision, policy, consequence)` directly. The consequence of the action is an argument supplied by the caller; it is deliberately not a field the model can set.
