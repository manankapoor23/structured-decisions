# Changelog

## 0.1.0 - 2026-09-17

- Initial release.
- Gives Claude a typed decision contract: one label from the caller's allowed set, explicit confidence, auditable evidence, and first-class abstention.
- Dependency-free validator for the decision contract.
- Policy gate returning `AUTOMATION_ALLOWED`, `HUMAN_REVIEW`, or `REJECT_RESULT`, with the action's consequence supplied by the caller rather than the model.
- JSON Schemas for decisions and policies.
- Empirical confidence calibration utility.
- Distributed as a Claude Code plugin: the repository is a plugin marketplace, so installation is
  `/plugin marketplace add manankapoor23/typed-decision-skill` followed by
  `/plugin install typed-decision@manan-skills`.
- Examples, 20 tests, CI, and MIT license.
