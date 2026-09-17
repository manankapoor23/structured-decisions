"""Threshold selection, calibration, and the verdicts that follow from them."""
import unittest

from _load import load

gate_mod = load("gate")
th = load("thresholds")
gate = gate_mod.gate
explain = gate_mod.explain


def decision(**overrides):
    base = {
        "decision": "spam",
        "confidence": 0.85,
        "needs_review": False,
        "abstained": False,
        "evidence": [{"kind": "observed", "text": "x"}],
        "reason": "x",
        "missing_information": [],
    }
    base.update(overrides)
    return base


def policy(**overrides):
    base = {"allowed_decisions": ["spam", "refund", "ban", "review"], "require_evidence": True}
    base.update(overrides)
    return base


def bins(*specs):
    """specs: (lower, count, accuracy) at 0.1 width."""
    return [{"lower": lo, "upper": round(lo + 0.1, 4), "count": n,
             "mean_confidence": round(lo + 0.05, 4), "empirical_accuracy": acc}
            for lo, n, acc in specs]


def artifact(groups):
    return {"version": 1, "bins": 10, "min_samples": 30, "groups": groups}


class GlobalFallback(unittest.TestCase):
    def test_global_fallback_is_used_when_nothing_else_applies(self):
        r = th.resolve_threshold(policy(automation_threshold=0.9), "spam")
        self.assertEqual((r.threshold, r.source), (0.9, "global"))

    def test_global_fallback_gates(self):
        p = policy(automation_threshold=0.9)
        self.assertEqual(gate(decision(confidence=0.95), p)[0], "AUTOMATION_ALLOWED")
        self.assertEqual(gate(decision(confidence=0.85), p)[0], "HUMAN_REVIEW")

    def test_no_threshold_at_all_goes_to_review_rather_than_automating(self):
        verdict, reasons = gate(decision(confidence=1.0), policy())
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("no applicable threshold" in r for r in reasons))


class PerClassThreshold(unittest.TestCase):
    def test_class_threshold_applies(self):
        r = th.resolve_threshold(policy(class_thresholds={"spam": 0.7}), "spam")
        self.assertEqual((r.threshold, r.source), (0.7, "class"))

    def test_class_threshold_overrides_global(self):
        p = policy(automation_threshold=0.99, class_thresholds={"spam": 0.7})
        r = th.resolve_threshold(p, "spam")
        self.assertEqual((r.threshold, r.source), (0.7, "class"))
        self.assertEqual(gate(decision(confidence=0.85), p)[0], "AUTOMATION_ALLOWED")

    def test_class_threshold_applies_only_to_its_own_class(self):
        p = policy(automation_threshold=0.99, class_thresholds={"spam": 0.7})
        r = th.resolve_threshold(p, "refund")
        self.assertEqual((r.threshold, r.source), (0.99, "global"))


class PerActionThreshold(unittest.TestCase):
    def test_action_threshold_applies(self):
        p = policy(actions={"ban_account": {"threshold": 0.995}})
        r = th.resolve_threshold(p, "ban", action="ban_account")
        self.assertEqual((r.threshold, r.source), (0.995, "action"))

    def test_action_threshold_overrides_class_and_global(self):
        p = policy(automation_threshold=0.5, class_thresholds={"ban": 0.6},
                   actions={"ban_account": {"threshold": 0.995}})
        r = th.resolve_threshold(p, "ban", action="ban_account")
        self.assertEqual((r.threshold, r.source), (0.995, "action"))
        self.assertEqual(gate(decision(decision="ban", confidence=0.99), p, action="ban_account")[0],
                         "HUMAN_REVIEW")

    def test_cost_not_class_identity_drives_the_threshold(self):
        """The same class, gated for two actions of different cost."""
        p = policy(consequence_thresholds={"low": 0.7, "medium": 0.9, "high": 0.98},
                   actions={"auto_delete": {"consequence": "low"},
                            "ban_account": {"consequence": "high"}})
        cheap = th.resolve_threshold(p, "spam", action="auto_delete")
        costly = th.resolve_threshold(p, "spam", action="ban_account")
        self.assertEqual((cheap.threshold, cheap.source), (0.7, "action_consequence"))
        self.assertEqual((costly.threshold, costly.source), (0.98, "action_consequence"))
        d = decision(confidence=0.85)
        self.assertEqual(gate(d, p, action="auto_delete")[0], "AUTOMATION_ALLOWED")
        self.assertEqual(gate(d, p, action="ban_account")[0], "HUMAN_REVIEW")

    def test_explicit_action_threshold_beats_its_consequence_ladder_entry(self):
        p = policy(consequence_thresholds={"low": 0.7, "high": 0.98},
                   actions={"ban_account": {"consequence": "high", "threshold": 0.995}})
        r = th.resolve_threshold(p, "ban", action="ban_account")
        self.assertEqual((r.threshold, r.source), (0.995, "action"))

    def test_unknown_action_goes_to_review(self):
        p = policy(automation_threshold=0.1, actions={"auto_delete": {"consequence": "low"}})
        verdict, reasons = gate(decision(confidence=1.0), p, action="ban_account")
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("not described by the policy" in r for r in reasons))


class CalibratedThreshold(unittest.TestCase):
    def setUp(self):
        self.cal = artifact({
            "global": {"count": 400, "bins": bins((0.6, 100, 0.70), (0.7, 100, 0.80),
                                                  (0.8, 100, 0.88), (0.9, 100, 0.96))},
            "spam": {"count": 120, "bins": bins((0.6, 30, 0.72), (0.7, 30, 0.86),
                                                (0.8, 30, 0.90), (0.9, 30, 0.97))},
            "ban": {"count": 6, "bins": bins((0.9, 6, 1.0))},
        })

    def test_sufficient_class_data_derives_a_threshold(self):
        p = policy(automation_threshold=0.99,
                   calibration={"target_accuracy": 0.85, "min_samples": 30})
        r = th.resolve_threshold(p, "spam", calibration=self.cal, raw_confidence=0.85)
        self.assertEqual(r.source, "calibrated")
        self.assertEqual(r.threshold, 0.7)   # lowest bin reaching 0.85 observed accuracy
        self.assertEqual(r.group, "spam")
        self.assertEqual(r.sample_count, 120)

    def test_calibrated_threshold_ranks_below_an_explicit_class_threshold(self):
        p = policy(class_thresholds={"spam": 0.95},
                   calibration={"target_accuracy": 0.85, "min_samples": 30})
        r = th.resolve_threshold(p, "spam", calibration=self.cal, raw_confidence=0.85)
        self.assertEqual((r.threshold, r.source), (0.95, "class"))

    def test_calibrated_threshold_ranks_above_the_global_fallback(self):
        p = policy(automation_threshold=0.99,
                   calibration={"target_accuracy": 0.85, "min_samples": 30})
        r = th.resolve_threshold(p, "spam", calibration=self.cal, raw_confidence=0.85)
        self.assertEqual(r.source, "calibrated")

    def test_rare_class_does_not_fit_its_own_threshold(self):
        """6 outcomes at 100% must not authorise automation."""
        p = policy(automation_threshold=0.5,
                   calibration={"target_accuracy": 0.85, "min_samples": 30,
                                "insufficient_data": "review"})
        r = th.resolve_threshold(p, "ban", calibration=self.cal, raw_confidence=0.95)
        self.assertFalse(r.resolved)
        self.assertEqual(r.sample_count, 6)
        self.assertTrue(any("below the minimum" in n for n in r.notes))
        verdict, reasons = gate(decision(decision="ban", confidence=0.95), p, calibration=self.cal)
        self.assertEqual(verdict, "HUMAN_REVIEW")

    def test_rare_class_can_shrink_toward_global_instead(self):
        p = policy(calibration={"target_accuracy": 0.85, "min_samples": 30,
                                "insufficient_data": "shrink", "shrinkage_weight": 30})
        r = th.resolve_threshold(p, "ban", calibration=self.cal, raw_confidence=0.95)
        self.assertTrue(r.resolved)
        self.assertEqual(r.source, "calibrated")
        self.assertTrue(any("shrunk toward the global rate" in n for n in r.notes))

    def test_shrinkage_pulls_a_thin_bin_toward_the_population(self):
        shrunk = th.shrink_bins(bins((0.9, 6, 1.0)), bins((0.9, 400, 0.80)), 30)
        self.assertLess(shrunk[0]["empirical_accuracy"], 1.0)
        self.assertGreater(shrunk[0]["empirical_accuracy"], 0.80)

    def test_rare_class_can_use_the_global_group_instead(self):
        p = policy(calibration={"target_accuracy": 0.85, "min_samples": 30,
                                "insufficient_data": "global"})
        r = th.resolve_threshold(p, "ban", calibration=self.cal, raw_confidence=0.95)
        self.assertEqual(r.group, "global")
        self.assertEqual(r.threshold, 0.8)   # lowest global bin reaching 0.85

    def test_no_bin_reaching_the_target_is_not_automatable(self):
        p = policy(automation_threshold=0.5, calibration={"target_accuracy": 0.999, "min_samples": 30})
        r = th.resolve_threshold(p, "spam", calibration=self.cal, raw_confidence=0.95)
        self.assertFalse(r.resolved)
        self.assertTrue(any("reached the target accuracy" in n for n in r.notes))

    def test_missing_group_and_no_global_is_not_automatable(self):
        p = policy(calibration={"target_accuracy": 0.85})
        r = th.resolve_threshold(p, "refund", calibration=artifact({"spam": {"count": 50, "bins": []}}),
                                 raw_confidence=0.9)
        self.assertFalse(r.resolved)

    def test_a_thin_global_group_does_not_set_a_threshold_either(self):
        thin = artifact({"global": {"count": 5, "bins": bins((0.9, 5, 1.0))}})
        p = policy(automation_threshold=0.5,
                   calibration={"target_accuracy": 0.85, "min_samples": 30})
        r = th.resolve_threshold(p, "spam", calibration=thin, raw_confidence=0.95)
        self.assertFalse(r.resolved)
        self.assertTrue(any("global group has 5" in n for n in r.notes))

    def test_the_reported_accuracy_names_the_group_it_came_from(self):
        cal = artifact({"global": {"count": 400, "bins": bins((0.9, 400, 0.62))}})
        _, _, detail = explain(decision(confidence=0.95),
                               policy(automation_threshold=0.9), calibration=cal)
        self.assertEqual(detail["threshold_source"], "global")
        self.assertEqual(detail["calibration_group"], "global")
        self.assertEqual(detail["calibration_samples"], 400)

    def test_calibration_without_a_target_falls_through(self):
        p = policy(automation_threshold=0.9, calibration={"min_samples": 30})
        r = th.resolve_threshold(p, "spam", calibration=self.cal, raw_confidence=0.9)
        self.assertEqual(r.source, "global")

    def test_action_specific_group_is_preferred_over_the_class_group(self):
        cal = artifact({"global": {"count": 400, "bins": bins((0.9, 400, 0.95))},
                        "spam": {"count": 100, "bins": bins((0.9, 100, 0.95))},
                        "auto_delete:spam": {"count": 80, "bins": bins((0.7, 80, 0.99))}})
        p = policy(calibration={"target_accuracy": 0.9, "min_samples": 30})
        r = th.resolve_threshold(p, "spam", action="auto_delete", calibration=cal, raw_confidence=0.8)
        self.assertEqual(r.group, "auto_delete:spam")
        self.assertEqual(r.threshold, 0.7)


class EvidenceIsAPolicyQuestionNotAShapeQuestion(unittest.TestCase):
    def test_empty_evidence_is_reviewable_not_malformed(self):
        verdict, reasons = gate(decision(evidence=[]),
                                policy(automation_threshold=0.1, require_evidence=True))
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("evidence is missing" in r for r in reasons))

    def test_a_policy_may_allow_automating_without_evidence(self):
        self.assertEqual(gate(decision(evidence=[]),
                              policy(automation_threshold=0.1, require_evidence=False))[0],
                         "AUTOMATION_ALLOWED")

    def test_malformed_evidence_is_still_malformed(self):
        self.assertEqual(gate(decision(evidence=[{"kind": "guessed", "text": "x"}]),
                              policy(automation_threshold=0.1))[0], "REJECT_RESULT")


class ShrinkageEdgeCases(unittest.TestCase):
    def test_a_bin_with_no_global_peer_is_dropped_rather_than_trusted(self):
        shrunk = th.shrink_bins(bins((0.5, 2, 1.0)), bins((0.9, 400, 0.8)), 30)
        self.assertEqual(shrunk, [])

    def test_shrinkage_leaves_a_well_populated_bin_almost_alone(self):
        shrunk = th.shrink_bins(bins((0.9, 3000, 0.99)), bins((0.9, 400, 0.50)), 30)
        self.assertGreater(shrunk[0]["empirical_accuracy"], 0.98)


class CalibratedVersusRawConfidence(unittest.TestCase):
    def test_both_are_reported_and_the_comparison_uses_raw(self):
        cal = artifact({"global": {"count": 400, "bins": bins((0.9, 400, 0.62))}})
        p = policy(automation_threshold=0.9)
        verdict, reasons, detail = explain(decision(confidence=0.95), p, calibration=cal)
        self.assertEqual(detail["raw_confidence"], 0.95)
        self.assertEqual(detail["calibrated_confidence"], 0.62)
        self.assertEqual(verdict, "AUTOMATION_ALLOWED")
        self.assertTrue(any("correct 0.62 of the time" in r for r in reasons))

    def test_calibrated_confidence_is_absent_when_no_artifact_is_supplied(self):
        _, _, detail = explain(decision(confidence=0.95), policy(automation_threshold=0.9))
        self.assertIsNone(detail["calibrated_confidence"])

    def test_bin_lookup_includes_the_upper_edge_of_the_last_bin(self):
        b = bins((0.9, 10, 0.5))
        self.assertIsNotNone(th.bin_for(1.0, b))
        self.assertIsNotNone(th.bin_for(0.9, b))
        self.assertIsNone(th.bin_for(0.89, b))


class Consequence(unittest.TestCase):
    def test_missing_consequence_goes_to_review(self):
        p = policy(automation_threshold=0.5, max_consequence="medium")
        verdict, reasons = gate(decision(confidence=1.0), p)
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("stated the consequence" in r for r in reasons))

    def test_high_consequence_action_exceeds_the_cap(self):
        p = policy(automation_threshold=0.5, max_consequence="medium",
                   actions={"ban_account": {"consequence": "high"}})
        verdict, reasons = gate(decision(confidence=1.0), p, action="ban_account")
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("exceeds the policy limit" in r for r in reasons))

    def test_the_policy_supplies_the_consequence_when_the_caller_does_not(self):
        p = policy(automation_threshold=0.5, max_consequence="high",
                   actions={"issue_refund": {"consequence": "medium"}})
        verdict, _, detail = explain(decision(confidence=1.0), p, action="issue_refund")
        self.assertEqual(verdict, "AUTOMATION_ALLOWED")
        self.assertEqual(detail["consequence"], "medium")

    def test_caller_and_policy_disagreeing_goes_to_review(self):
        p = policy(automation_threshold=0.5, max_consequence="high",
                   actions={"issue_refund": {"consequence": "medium"}})
        verdict, reasons = gate(decision(confidence=1.0), p, consequence="low", action="issue_refund")
        self.assertEqual(verdict, "HUMAN_REVIEW")
        self.assertTrue(any("declares action" in r for r in reasons))


class ModelCannotWidenItsOwnAuthority(unittest.TestCase):
    def test_a_decision_carrying_a_threshold_is_rejected(self):
        d = decision()
        d["threshold"] = 0.01
        verdict, reasons = gate(d, policy(automation_threshold=0.99))
        self.assertEqual(verdict, "REJECT_RESULT")
        self.assertTrue(any("unexpected fields" in r for r in reasons))

    def test_a_decision_carrying_a_consequence_is_rejected(self):
        d = decision()
        d["consequence"] = "low"
        self.assertEqual(gate(d, policy(automation_threshold=0.5, max_consequence="low"))[0],
                         "REJECT_RESULT")

    def test_the_gate_reads_no_field_outside_the_contract(self):
        p = policy(automation_threshold=0.5, max_consequence="high",
                   actions={"ban_account": {"consequence": "high"}})
        plain = gate(decision(confidence=0.9), p, action="ban_account")
        self.assertEqual(plain[0], "AUTOMATION_ALLOWED")


class Abstention(unittest.TestCase):
    def test_abstention_is_its_own_verdict(self):
        d = decision(abstained=True, needs_review=True, decision="review",
                     missing_information=["the error message"])
        verdict, reasons = gate(d, policy(automation_threshold=0.1))
        self.assertEqual(verdict, "ABSTAIN")
        self.assertTrue(any("the error message" in r for r in reasons))

    def test_abstention_never_automates_however_low_the_threshold(self):
        d = decision(abstained=True, needs_review=True, decision="review",
                     confidence=1.0, missing_information=["x"])
        self.assertEqual(gate(d, policy(automation_threshold=0.0))[0], "ABSTAIN")

    def test_abstention_exit_code_is_not_success(self):
        self.assertNotEqual(gate_mod.EXIT_CODES["ABSTAIN"], 0)
        self.assertNotEqual(gate_mod.EXIT_CODES["HUMAN_REVIEW"], 0)
        self.assertEqual(gate_mod.EXIT_CODES["AUTOMATION_ALLOWED"], 0)


class HumanReviewRouting(unittest.TestCase):
    def test_requested_review_is_honoured(self):
        self.assertEqual(gate(decision(needs_review=True), policy(automation_threshold=0.1))[0],
                         "HUMAN_REVIEW")

    def test_missing_evidence_goes_to_review(self):
        self.assertEqual(gate(decision(evidence=[]), policy(automation_threshold=0.1, ))[0],
                         "HUMAN_REVIEW")

    def test_off_policy_label_is_rejected_not_reviewed(self):
        self.assertEqual(gate(decision(decision="delete_everything"),
                              policy(automation_threshold=0.1))[0], "REJECT_RESULT")


class BatchJudgments(unittest.TestCase):
    def test_each_judgment_is_gated_on_its_own_action(self):
        p = policy(consequence_thresholds={"low": 0.7, "high": 0.98},
                   actions={"auto_delete": {"consequence": "low"},
                            "ban_account": {"consequence": "high"}})
        batch = {"judgments": {
            "is_spam": decision(decision="spam", confidence=0.85),
            "should_ban": decision(decision="ban", confidence=0.85),
        }}
        self.assertEqual(gate(batch["judgments"]["is_spam"], p, action="auto_delete")[0],
                         "AUTOMATION_ALLOWED")
        self.assertEqual(gate(batch["judgments"]["should_ban"], p, action="ban_account")[0],
                         "HUMAN_REVIEW")

    def test_an_abstained_judgment_does_not_block_its_siblings(self):
        p = policy(automation_threshold=0.8)
        batch = {"judgments": {
            "route": decision(confidence=0.95),
            "refund_owed": decision(decision="review", abstained=True, needs_review=True,
                                    confidence=0.2, missing_information=["billing"]),
        }}
        self.assertEqual(gate(batch["judgments"]["route"], p)[0], "AUTOMATION_ALLOWED")
        self.assertEqual(gate(batch["judgments"]["refund_owed"], p)[0], "ABSTAIN")


class InvalidAndConflictingPolicies(unittest.TestCase):
    def valid(self, **overrides):
        return gate_mod.validate_policy(policy(**overrides))

    def test_a_minimal_policy_is_valid(self):
        self.assertEqual(self.valid(), [])

    def test_missing_required_fields(self):
        self.assertTrue(gate_mod.validate_policy({"allowed_decisions": ["spam"]}))

    def test_unexpected_field(self):
        self.assertTrue(self.valid(automation_thresholds=0.9))

    def test_threshold_out_of_range(self):
        self.assertTrue(self.valid(automation_threshold=1.5))
        self.assertTrue(self.valid(class_thresholds={"spam": 2}))
        self.assertTrue(self.valid(actions={"a": {"threshold": -0.1}}))

    def test_boolean_is_not_a_threshold(self):
        self.assertTrue(self.valid(automation_threshold=True))

    def test_review_below_above_automation_threshold_conflicts(self):
        self.assertTrue(self.valid(automation_threshold=0.8, review_below=0.9))

    def test_review_below_without_automation_threshold_is_meaningless(self):
        self.assertTrue(self.valid(review_below=0.9))

    def test_class_threshold_for_a_label_that_cannot_be_decided(self):
        errors = self.valid(class_thresholds={"nonexistent": 0.9})
        self.assertTrue(any("not an allowed decision" in e for e in errors))

    def test_consequence_ladder_must_not_decrease(self):
        errors = self.valid(consequence_thresholds={"low": 0.99, "medium": 0.9, "high": 0.8})
        self.assertTrue(any("cannot require less confidence" in e for e in errors))

    def test_action_threshold_below_its_own_consequence_floor_conflicts(self):
        errors = self.valid(consequence_thresholds={"high": 0.98},
                            actions={"ban_account": {"consequence": "high", "threshold": 0.5}})
        self.assertTrue(any("requires at least" in e for e in errors))

    def test_action_must_say_something(self):
        self.assertTrue(self.valid(actions={"ban_account": {}}))

    def test_unknown_consequence_level(self):
        self.assertTrue(self.valid(max_consequence="catastrophic"))
        self.assertTrue(self.valid(actions={"a": {"consequence": "catastrophic"}}))

    def test_calibration_settings_are_checked(self):
        self.assertTrue(self.valid(calibration={"target_accuracy": 1.2}))
        self.assertTrue(self.valid(calibration={"min_samples": 0}))
        self.assertTrue(self.valid(calibration={"shrinkage_weight": 0}))
        self.assertTrue(self.valid(calibration={"insufficient_data": "guess"}))
        self.assertTrue(self.valid(calibration={"unknown": 1}))

    def test_an_action_with_a_cost_but_no_ladder_entry_is_an_error(self):
        """Declaring a cost must not leave the action on the global fallback."""
        errors = self.valid(automation_threshold=0.5,
                            consequence_thresholds={"low": 0.7},
                            actions={"ban_account": {"consequence": "high"}})
        self.assertTrue(any("no 'high' entry" in e for e in errors))

    def test_a_malformed_artifact_is_rejected(self):
        self.assertTrue(gate_mod.validate_calibration({}))
        self.assertTrue(gate_mod.validate_calibration({"groups": {"g": {"count": -1, "bins": []}}}))
        self.assertEqual(gate_mod.validate_calibration(
            artifact({"global": {"count": 10, "bins": bins((0.9, 10, 0.5))}})), [])


if __name__ == "__main__":
    unittest.main()
