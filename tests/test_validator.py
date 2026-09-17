import unittest

from _load import load

mod = load("validate")


def decision(**overrides):
    base = {
        "decision": "approve",
        "confidence": 0.95,
        "needs_review": False,
        "abstained": False,
        "evidence": [{"kind": "observed", "text": "x"}],
        "reason": "x",
        "missing_information": [],
    }
    base.update(overrides)
    return base


class ValidatorTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(mod.validate(decision()), [])

    def test_abstention_requires_review(self):
        errors = mod.validate(decision(abstained=True, missing_information=["y"]))
        self.assertTrue(any("require review" in e for e in errors))

    def test_abstention_requires_missing_information(self):
        errors = mod.validate(decision(abstained=True, needs_review=True))
        self.assertTrue(any("missing information" in e for e in errors))

    def test_allowed_decisions(self):
        self.assertTrue(mod.validate(decision(decision="maybe"), allowed_decisions=["yes", "no"]))

    def test_confidence_bounds(self):
        self.assertTrue(mod.validate(decision(confidence=1.5)))

    def test_booleans_are_not_confidence(self):
        self.assertTrue(mod.validate(decision(confidence=True)))

    def test_unexpected_field(self):
        self.assertTrue(mod.validate(decision(extra="no")))

    def test_evidence_kind(self):
        self.assertTrue(mod.validate(decision(evidence=[{"kind": "guessed", "text": "x"}])))


class BatchTests(unittest.TestCase):
    def test_valid_batch(self):
        self.assertEqual(mod.validate_batch({"judgments": {"a": decision(), "b": decision()}}), [])

    def test_errors_are_prefixed_with_the_question_id(self):
        errors = mod.validate_batch({"judgments": {"a": decision(confidence=9)}})
        self.assertTrue(any(e.startswith("judgments.a:") for e in errors))

    def test_empty_batch(self):
        self.assertTrue(mod.validate_batch({"judgments": {}}))

    def test_batch_must_be_object(self):
        self.assertTrue(mod.validate_batch([]))

    def test_unexpected_top_level_field(self):
        self.assertTrue(mod.validate_batch({"judgments": {"a": decision()}, "extra": 1}))

    def test_per_question_allowed_labels(self):
        batch = {"judgments": {"route": decision(decision="frontend"), "urgent": decision(decision="urgent")}}
        allowed = {"route": ["frontend", "backend"], "urgent": ["urgent", "not_urgent"]}
        self.assertEqual(mod.validate_batch(batch, allowed_by_id=allowed), [])
        wrong = {"route": ["backend"], "urgent": ["urgent", "not_urgent"]}
        self.assertTrue(mod.validate_batch(batch, allowed_by_id=wrong))


if __name__ == "__main__":
    unittest.main()
