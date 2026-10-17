"""The derived percentages quoted in the README must come from the pipeline.

The headline measures are guarded elsewhere; these are the ratios the prose
leans on (overdue share, concentration in the top accounts, provision as a
share of receivables), so they are computed here rather than typed into
markdown by hand.
"""
import unittest
from decimal import Decimal as D

from recv import pipeline
from recv.generator import generate


class TestDerivedShares(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = pipeline.analyse(generate())

    def test_overdue_share_of_receivables(self):
        r = self.result
        expected = (r["overdue_ar"] / r["total_ar"] * 100).quantize(D("0.01"))
        self.assertEqual(r["overdue_share_of_ar"], expected)

    def test_ninety_plus_share_of_receivables(self):
        r = self.result
        expected = (r["buckets"]["d90_plus"] / r["total_ar"] * 100).quantize(D("0.01"))
        self.assertEqual(r["d90_plus_share_of_ar"], expected)

    def test_ninety_plus_share_of_overdue(self):
        r = self.result
        expected = (r["buckets"]["d90_plus"] / r["overdue_ar"] * 100).quantize(D("0.01"))
        self.assertEqual(r["d90_plus_share_of_overdue"], expected)

    def test_top_three_share_of_overdue(self):
        r = self.result
        top3 = sum((c.overdue_balance for c in r["chase"][:3]), D("0"))
        self.assertEqual(r["top3_overdue_share"], (top3 / r["overdue_ar"] * 100).quantize(D("0.01")))

    def test_top_three_share_of_recoverable_cash(self):
        r = self.result
        top3 = sum((c.expected_recovery for c in r["chase"][:3]), D("0"))
        expected = (top3 / r["unlock"]["recoverable_now"] * 100).quantize(D("0.01"))
        self.assertEqual(r["top3_recovery_share"], expected)

    def test_top_five_shares(self):
        r = self.result
        top5_overdue = sum((c.overdue_balance for c in r["chase"][:5]), D("0"))
        top5_recovery = sum((c.expected_recovery for c in r["chase"][:5]), D("0"))
        self.assertEqual(r["top5_overdue_share"],
                         (top5_overdue / r["overdue_ar"] * 100).quantize(D("0.01")))
        self.assertEqual(r["top5_recovery_share"],
                         (top5_recovery / r["unlock"]["recoverable_now"] * 100).quantize(D("0.01")))

    def test_recoverable_share_of_overdue(self):
        r = self.result
        expected = (r["unlock"]["recoverable_now"] / r["overdue_ar"] * 100).quantize(D("0.01"))
        self.assertEqual(r["recoverable_share_of_overdue"], expected)

    def test_provision_share_of_receivables(self):
        r = self.result
        expected = (r["provision"] / r["total_ar"] * 100).quantize(D("0.01"))
        self.assertEqual(r["provision_share_of_ar"], expected)

    def test_dso_gap_matches_its_components(self):
        r = self.result
        self.assertEqual(r["unlock"]["dso_gap_days"],
                         (r["dso"] - r["best_possible_dso"]).quantize(D("0.01")))


if __name__ == "__main__":
    unittest.main()
