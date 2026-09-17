# Changelog

## 0.1.5 - 2026-09-17

- The README now documents copying the skill, rather than installing from this repository as a
  marketplace, until the community marketplace listing appears in the public catalog. Examples are
  written as `/decide`, which is what a copied skill is called.
- The plugin manifests are unchanged, so this repository remains a valid plugin and marketplace. The
  marketplace install still works for anyone who prefers it:
  `/plugin marketplace add manankapoor23/typed-decision` then
  `/plugin install typed-decision@manan-skills`.

## 0.1.4 - 2026-09-17

- Added a quick start at the top: two install commands, one prompt, and the shape of the answer, so
  the project can be evaluated in a few seconds without reading further.
- Removed the "Why" section, which restated the opening paragraph in different words.

## 0.1.3 - 2026-09-17

- Fixed every documented command. They said `python`, which does not exist on macOS or on many Linux
  installations, so each one failed with `command not found` for anyone copying from the README. They
  now say `python3`, with a note that Windows uses `python`.
- Added `examples/predictions.jsonl`, so the calibration command can be run as written. It previously
  named a file the repository did not ship.
- Said where the command-line examples run from, since someone who installed the plugin has no
  `skills/` directory in their own project.

## 0.1.2 - 2026-09-17

- Renamed the repository to `typed-decision`, matching the plugin name, so the two install commands
  read consistently. Installs become
  `/plugin marketplace add manankapoor23/typed-decision` followed by
  `/plugin install typed-decision@manan-skills`. The old repository URL redirects.
- The skill stays `decide`, so the command remains `/typed-decision:decide`. Plugin skills are always
  namespaced by plugin name, so naming the skill `typed-decision` would produce
  `/typed-decision:typed-decision` rather than a single word.
- No change to the decision contract, the validator, or the gate.

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
  `/plugin marketplace add manankapoor23/typed-decision` followed by
  `/plugin install typed-decision@manan-skills`.
- Examples, 27 tests, CI, and MIT license.
