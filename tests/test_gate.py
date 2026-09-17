import unittest

from _load import load

mod = load("gate")

POLICY = {
    "allowed_decisions": ["approve", "reject", "review"],
    "automation_threshold": 0.90,
    "review_below": 0.90,
    "max_consequence": "medium",
    "require_evidence": True,
}


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


class GateTests(unittest.TestCase):
    def test_automation_allowed(self):
        verdict, _ = mod.gate(decision(), POLICY, consequence="low")
        self.assertEqual(verdict, "AUTOMATION_ALLOWED")

    def test_invalid_decision_is_rejected(self):
        verdict, reasons = mod.gate(decision(confidence=2), POLICY, consequence="low")
        self.assertEqual(verdict, "REJECT_RESULT")
        self.assertTrue(reasons)

    def test_label_outside_policy_is_rejected(self):
        verdict, _ = mod.gate(decision(decision="delete_account"), POLICY, consequence="low")
        self.assertEqual(verdict, "REJECT_RESULT")

    def test_abstention_goes_to_review(self):
        obj = decision(abstained=True, needs_review=True, missing_information=["y"], decision="review")
        self.assertEqual(mod.gate(obj, POLICY, consequence="low")[0], "HUMAN_REVIEW")

    def test_low_confidence_goes_to_review(self):
        self.assertEqual(mod.gate(decision(confidence=0.5), POLICY, consequence="low")[0], "HUMAN_REVIEW")

    def test_requested_review_is_honoured(self):
        self.assertEqual(mod.gate(decision(needs_review=True), POLICY, consequence="low")[0], "HUMAN_REVIEW")

    def test_consequence_above_limit_goes_to_review(self):
        self.assertEqual(mod.gate(decision(), POLICY, consequence="high")[0], "HUMAN_REVIEW")

    def test_unstated_consequence_goes_to_review(self):
        verdict, reasons = mod.gate(decision(), POLICY)
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("did not state" in r for r in reasons))

    def test_policy_without_consequence_limit_automates(self):
        policy = {k: v for k, v in POLICY.items() if k != "max_consequence"}
        self.assertEqual(mod.gate(decision(), policy)[0], "AUTOMATION_ALLOWED")

    def test_valid_policy(self):
        self.assertEqual(mod.validate_policy(POLICY), [])

    def test_contradictory_policy(self):
        policy = dict(POLICY, review_below=0.99)
        self.assertTrue(mod.validate_policy(policy))

    def test_policy_missing_fields(self):
        self.assertTrue(mod.validate_policy({"allowed_decisions": ["approve"]}))


if __name__ == "__main__":
    unittest.main()
