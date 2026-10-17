"""Tests for the synthetic ledger generator.

The generator is the evidence base for every number in the report, so its
determinism and its internal consistency are load-bearing, not incidental.
"""
import unittest
from decimal import Decimal as D

from recv.generator import generate, fingerprint
from recv import metrics


class TestDeterminism(unittest.TestCase):
    def test_same_seed_produces_an_identical_ledger(self):
        self.assertEqual(fingerprint(generate(seed=7)), fingerprint(generate(seed=7)))

    def test_different_seeds_produce_different_ledgers(self):
        self.assertNotEqual(fingerprint(generate(seed=7)), fingerprint(generate(seed=8)))

    def test_default_seed_is_stable_across_calls(self):
        self.assertEqual(fingerprint(generate()), fingerprint(generate()))


class TestShape(unittest.TestCase):
    def setUp(self):
        self.led = generate(seed=20260101)

    def test_has_the_documented_number_of_customers(self):
        self.assertEqual(len(self.led.customers), 60)

    def test_covers_eighteen_months(self):
        self.assertEqual(len(self.led.months), 18)

    def test_carries_an_unapplied_cash_receipt(self):
        self.assertGreater(self.led.unapplied_cash, D("0"))

    def test_contains_disputed_invoices(self):
        self.assertTrue(any(i.is_disputed for i in self.led.invoices))

    def test_some_accounts_are_fully_settled(self):
        open_ids = {
            i.customer_id for i in self.led.invoices
            if i.amount - i.paid_amount > 0 and i.paid_date is None
        }
        self.assertTrue(len(self.led.customers) - len(open_ids) > 0)


class TestInvariants(unittest.TestCase):
    def setUp(self):
        self.led = generate(seed=20260101)

    def test_every_invoice_belongs_to_a_known_customer(self):
        self.assertTrue(all(i.customer_id in self.led.customers for i in self.led.invoices))

    def test_no_invoice_is_overpaid(self):
        for i in self.led.invoices:
            self.assertLessEqual(i.paid_amount, i.amount, i.invoice_id)

    def test_paid_date_is_set_exactly_when_cash_has_arrived(self):
        for i in self.led.invoices:
            if i.paid_amount > 0:
                self.assertIsNotNone(i.paid_date, i.invoice_id)
            else:
                self.assertIsNone(i.paid_date, i.invoice_id)

    def test_due_date_follows_the_customer_terms(self):
        for i in self.led.invoices:
            terms = self.led.customers[i.customer_id].credit_terms_days
            self.assertEqual((i.due_date - i.invoice_date).days, terms, i.invoice_id)

    def test_no_invoice_is_dated_after_the_reporting_date(self):
        for i in self.led.invoices:
            self.assertLessEqual(i.invoice_date, self.led.as_of, i.invoice_id)

    def test_ageing_buckets_reconcile_to_total_receivables(self):
        buckets = metrics.ageing_buckets(self.led, self.led.as_of)
        self.assertEqual(sum(buckets.values()), metrics.total_ar(self.led, self.led.as_of))


if __name__ == "__main__":
    unittest.main()
