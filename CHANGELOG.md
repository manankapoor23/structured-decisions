# Changelog

## 0.2.1 - 2026-09-17

- Fixed the CI check for abstention, which still asserted exit code 10 after 0.2.0 moved abstention
  to its own verdict at exit code 30. The behaviour was correct; the check was not, and it failed
  the build for v0.2.0.

## 0.2.0 - 2026-09-17

Thresholds are no longer one global number.

- **Hierarchical threshold selection.** The gate takes the first that applies: an action's own
  threshold, the action's consequence via a cost ladder, an explicit per-class threshold, a
  threshold derived from labelled outcomes, then `automation_threshold` as a fallback. When none
  applies the decision goes to a person rather than to a guessed number. `automation_threshold` is
  now optional and documented as a fallback rather than the preferred strategy.
- **Thresholds follow cost, not class identity.** `actions` describes what each action does and what
  it costs; `consequence_thresholds` maps cost to required confidence. The same decision at the same
  confidence can automate one action and require review for another.
- **Calibration can set the threshold.** `calibrate.py --artifact` writes per-class and per-action
  observed accuracy, and a policy can derive its cutoff from the lowest confidence bin that reached
  a target accuracy.
- **Rare classes do not get their own fitted threshold.** `calibration.min_samples` sets the bar and
  `calibration.insufficient_data` chooses the fallback: `review` (default) refuses to automate the
  group, `shrink` pulls its accuracies toward the global rate weighted by sample count, `global`
  uses the population threshold. A class bin with no global counterpart is dropped rather than
  trusted.
- **`ABSTAIN` is now its own verdict**, exit code 30, separate from `HUMAN_REVIEW`. A decision that
  needs checking and the absence of a decision meant different things to the caller and now read
  differently. Only exit code 0 still means automate.
- **Empty evidence routes to review rather than rejection.** Shape is a contract question; whether
  there is enough evidence to act is a policy question a person can answer. The `require_evidence`
  branch in the gate was previously unreachable, because validation failed the decision first.
- **An action that names a consequence with no matching ladder entry is now a policy error**, rather
  than silently falling through to the global fallback.
- **A conflicting policy is rejected at validation.** A cost ladder that decreases as consequence
  rises, an action threshold below its own consequence floor, a class threshold for a label that is
  not an allowed decision, and `review_below` without `automation_threshold` are all errors. If the
  caller and the policy disagree about an action's consequence at gate time, the decision goes to a
  person.
- **The model still cannot reach any of this.** Threshold, action, and consequence come from the
  policy and the caller. A decision carrying such a field is rejected by the validator, and there
  are tests asserting it.
- New `scripts/thresholds.py`, `schemas/calibration.schema.json`, `examples/policy-tiered.json`,
  `examples/calibration.json`, `examples/predictions-labelled.jsonl`, and `gate.py --json` for the
  full audit trail. 27 tests to 87.
- `review_below` is still accepted and validated, but it has no effect on any verdict.

## 0.1.7 - 2026-09-17

- Fixed the install path in `references/integration.md`, which read `~/skills/decide/SKILL.md`. Claude
  Code looks in `~/.claude/skills`, so the path as written pointed nowhere. It now gives both the
  per-project and the every-project location.
- The repository layout in the README omitted `examples/predictions.jsonl`, which one of its own
  commands names, and `tests/_load.py`.

## 0.1.6 - 2026-09-17

- Renamed the marketplace from `manan-skills` to `typed-decision`, so the plugin installs as
  `typed-decision@typed-decision` and the repository, marketplace, and plugin names all agree.
- Anyone who added the marketplace under its old name should remove and re-add it:
  `/plugin marketplace remove manan-skills`, then
  `/plugin marketplace add manankapoor23/typed-decision`, then
  `/plugin install typed-decision@typed-decision`. A marketplace rename has no migration path, since
  the `renames` field maps plugin names rather than marketplace names.

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
