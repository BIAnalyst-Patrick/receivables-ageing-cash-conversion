"""The README makes claims the code computes, so the claims are read back.

The recovery schedule and the "modelled, not collected" distinction are the two
the recoverable figure rests on. If a rate in ``recv/decisions.py`` changes and
the README does not, a reader is misled about where the 6.73M comes from — and
an estimate that reads like cash collected is the one error this report must
never make.
"""
import unittest
from pathlib import Path

from recv.decisions import GRADE_FACTOR, RECOVERY_RATES

ROOT = Path(__file__).resolve().parent.parent


class TestReadmeDisclosures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_quotes_the_recovery_rate_schedule(self):
        for bucket, rate in RECOVERY_RATES.items():
            self.assertIn(f"{rate * 100:.0f}%", self.readme,
                          f"recovery rate for {bucket} missing from the README")
        for grade, factor in GRADE_FACTOR.items():
            self.assertIn(f"{factor:.2f}", self.readme,
                          f"risk-grade factor for {grade} missing from the README")

    def test_the_recoverable_figure_is_labelled_modelled_not_collected(self):
        self.assertIn("modelled, not collected", self.readme)

    def test_the_readme_states_nothing_is_cash_already_collected(self):
        self.assertIn("Nothing here is cash already collected", self.readme)


if __name__ == "__main__":
    unittest.main()
