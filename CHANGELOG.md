# Changelog

## 0.1.1 - 2026-09-17

- Say plainly what this is: an experiment in offering the interface of a typed decision model from
  inside Claude Code. Added a section comparing it to a System One model across answer shape,
  uncertainty, calibration, and narration, and explaining why `reason` and `evidence` are required
  here when a model that returns a distribution needs neither.
- No change to the decision contract, the validator, or the gate.

## 0.1.0 - 2026-09-17

- Initial release.
- Gives Claude a typed decision contract: one label from the caller's allowed set, explicit confidence, auditable evidence, and first-class abstention.
- Several independent judgments about one input in a single response, under `{"judgments": {...}}`, each
  carrying the full contract. The validator detects the batch shape automatically and the gate takes
  `--judgment <id>`.
- Guidance for separating the input's content from the questions asked about it, and for splitting a
  judgment that rests on several factors into separate questions weighted in the caller's code.
- Dependency-free validator for the decision contract.
- Policy gate returning `AUTOMATION_ALLOWED`, `HUMAN_REVIEW`, or `REJECT_RESULT`, with the action's consequence supplied by the caller rather than the model.
- JSON Schemas for decisions and policies.
- Empirical confidence calibration utility reporting per-bin accuracy, expected calibration error, and Brier score.
- Distributed as a Claude Code plugin: the repository is a plugin marketplace, so installation is
  `/plugin marketplace add manankapoor23/structured-decisions` followed by
  `/plugin install typed-decision@manan-skills`.
- Examples, 27 tests, CI, and MIT license.
