"""The published answer key must match a fresh computation.

This is a drift guard rather than new behaviour: if the generator or any
measure changes, the committed key stops matching and this test fails until
the artefacts are regenerated.
"""
import json
import unittest
from decimal import Decimal
from pathlib import Path

from recv import pipeline
from recv.generator import generate

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "outputs" / "answer_key.json"


class TestAnswerKey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = pipeline.analyse(generate())

    def test_answer_key_file_exists(self):
        self.assertTrue(KEY.exists(), "run `make run` to generate outputs/answer_key.json")

    def test_fingerprint_matches(self):
        published = json.loads(KEY.read_text(encoding="utf-8"))
        self.assertEqual(published["fingerprint"], self.result["fingerprint"])

    def test_headline_figures_match(self):
        published = json.loads(KEY.read_text(encoding="utf-8"))
        for field in ("total_ar", "overdue_ar", "dso", "best_possible_dso",
                      "dio", "dpo", "ccc", "cei", "provision"):
            self.assertEqual(
                Decimal(published[field]),
                Decimal(str(self.result[field])),
                f"{field} in the answer key has drifted from the code",
            )

    def test_all_published_checks_passed(self):
        published = json.loads(KEY.read_text(encoding="utf-8"))
        failed = [c["check"] for c in published["checks"] if not c["passed"]]
        self.assertEqual(failed, [], f"failing checks in the answer key: {failed}")


if __name__ == "__main__":
    unittest.main()
