"""Behavioural tests for the receivables measures.

Every expectation here is hand-computed on a tiny ledger so the test states
the intended arithmetic rather than mirroring the implementation.
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal as D

from recv.model import Customer, Invoice, MonthSnapshot, Ledger
from recv import metrics


AS_OF = date(2026, 6, 30)


def cust(cid="C1", terms=30, grade="B", segment="medium"):
    return Customer(
        customer_id=cid,
        name=f"Customer {cid}",
        segment=segment,
        credit_terms_days=terms,
        credit_limit=D("100000"),
        risk_grade=grade,
        sales_rep="Rep A",
    )


def inv(iid, cid, amount, days_overdue, paid=0, paid_days_after_due=None, disputed=False):
    """Invoice whose due date sits `days_overdue` before AS_OF."""
    due = AS_OF - timedelta(days=days_overdue)
    return Invoice(
        invoice_id=iid,
        customer_id=cid,
        invoice_date=due - timedelta(days=30),
        due_date=due,
        amount=D(str(amount)),
        paid_amount=D(str(paid)),
        paid_date=None if paid_days_after_due is None else due + timedelta(days=paid_days_after_due),
        is_disputed=disputed,
    )


def ledger(invoices, months=None, as_of=AS_OF):
    ids = {i.customer_id for i in invoices}
    return Ledger(
        customers={cid: cust(cid) for cid in ids},
        invoices=list(invoices),
        months=months or [],
        unapplied_cash=D("0"),
        as_of=as_of,
    )


class TestAgeing(unittest.TestCase):
    def test_classifies_each_bucket_by_days_overdue(self):
        led = ledger([
            inv("I1", "C1", 100, 0),      # not yet due
            inv("I2", "C1", 200, 10),
            inv("I3", "C1", 300, 40),
            inv("I4", "C1", 400, 75),
            inv("I5", "C1", 500, 120),
        ])
        b = metrics.ageing_buckets(led, AS_OF)
        self.assertEqual(b["current"], D("100"))
        self.assertEqual(b["d1_30"], D("200"))
        self.assertEqual(b["d31_60"], D("300"))
        self.assertEqual(b["d61_90"], D("400"))
        self.assertEqual(b["d90_plus"], D("500"))

    def test_bucket_edges_are_inclusive_lower_bound(self):
        led = ledger([
            inv("I1", "C1", 1, 0),
            inv("I2", "C1", 2, 1),
            inv("I3", "C1", 4, 30),
            inv("I4", "C1", 8, 31),
            inv("I5", "C1", 16, 60),
            inv("I6", "C1", 32, 61),
            inv("I7", "C1", 64, 90),
            inv("I8", "C1", 128, 91),
        ])
        b = metrics.ageing_buckets(led, AS_OF)
        self.assertEqual(b["current"], D("1"))
        self.assertEqual(b["d1_30"], D("2") + D("4"))
        self.assertEqual(b["d31_60"], D("8") + D("16"))
        self.assertEqual(b["d61_90"], D("32") + D("64"))
        self.assertEqual(b["d90_plus"], D("128"))

    def test_settled_invoices_are_excluded(self):
        led = ledger([
            inv("I1", "C1", 100, 10),
            inv("I2", "C1", 250, 10, paid=250, paid_days_after_due=2),
        ])
        self.assertEqual(metrics.ageing_buckets(led, AS_OF)["d1_30"], D("100"))

    def test_open_balance_uses_paid_amount_not_invoice_total(self):
        led = ledger([inv("I1", "C1", 1000, 10, paid=400)])
        self.assertEqual(metrics.ageing_buckets(led, AS_OF)["d1_30"], D("600"))

    def test_buckets_sum_to_total_ar(self):
        led = ledger([
            inv("I1", "C1", 100, 0),
            inv("I2", "C1", 200, 45, paid=50),
            inv("I3", "C1", 300, 200),
        ])
        b = metrics.ageing_buckets(led, AS_OF)
        self.assertEqual(sum(b.values()), metrics.total_ar(led, AS_OF))


class TestDso(unittest.TestCase):
    def test_dso_is_ar_over_average_daily_credit_sales(self):
        # AR 900, 1800 of sales across a 90 day window => 20/day => 45 days
        led = ledger([inv("I1", "C1", 900, 5)])
        led.months = [
            MonthSnapshot("2026-04", revenue=D("600"), cogs=D("400"),
                          inventory_value=D("0"), payables_value=D("0")),
            MonthSnapshot("2026-05", revenue=D("600"), cogs=D("400"),
                          inventory_value=D("0"), payables_value=D("0")),
            MonthSnapshot("2026-06", revenue=D("600"), cogs=D("400"),
                          inventory_value=D("0"), payables_value=D("0")),
        ]
        self.assertEqual(metrics.dso(led, AS_OF, window_days=90), D("45"))

    def test_dso_is_none_when_there_are_no_sales(self):
        led = ledger([inv("I1", "C1", 900, 5)])
        self.assertIsNone(metrics.dso(led, AS_OF, window_days=90))

    def test_best_possible_dso_uses_only_the_current_bucket(self):
        led = ledger([
            inv("I1", "C1", 300, 0),
            inv("I2", "C1", 600, 45),
        ])
        led.months = [MonthSnapshot("2026-06", revenue=D("1800"), cogs=D("1000"),
                                    inventory_value=D("0"), payables_value=D("0"))]
        # 300 current / (1800/90 = 20 per day) = 15 days
        self.assertEqual(metrics.best_possible_dso(led, AS_OF, window_days=90), D("15"))


class TestCei(unittest.TestCase):
    def test_cei_of_a_period_that_collected_everything_is_100(self):
        led = ledger([])
        self.assertEqual(
            metrics.collection_effectiveness_index(
                opening_ar=D("1000"), credit_sales=D("0"), closing_ar=D("0"), closing_current=D("0")),
            D("100"),
        )

    def test_cei_known_value(self):
        # collected 300 (1000 + 500 - 1200) of the 1200 that was collectible
        # (1000 + 500 - 300) => 25%
        self.assertEqual(
            metrics.collection_effectiveness_index(
                opening_ar=D("1000"), credit_sales=D("500"), closing_ar=D("1200"), closing_current=D("300")),
            D("25"),
        )

    def test_cei_guards_against_zero_collectible_base(self):
        self.assertIsNone(
            metrics.collection_effectiveness_index(
                opening_ar=D("0"), credit_sales=D("0"), closing_ar=D("0"), closing_current=D("0")))


class TestCashConversion(unittest.TestCase):
    def test_cycle_adds_inventory_days_and_subtracts_payable_days(self):
        self.assertEqual(
            metrics.cash_conversion_cycle(dso=D("45"), dio=D("30"), dpo=D("40")),
            D("35"),
        )

    def test_dio_and_dpo_come_from_monthly_snapshots(self):
        led = ledger([], months=[
            MonthSnapshot("2026-05", revenue=D("3000"), cogs=D("3000"),
                          inventory_value=D("3000"), payables_value=D("2000")),
            MonthSnapshot("2026-06", revenue=D("3000"), cogs=D("3000"),
                          inventory_value=D("3000"), payables_value=D("2000")),
        ])
        # cogs 36000/yr => 100/day; inventory 3000 => 30 days; payables 2000 => 20 days
        self.assertEqual(metrics.days_inventory_outstanding(led, AS_OF, window_days=90), D("30"))
        self.assertEqual(metrics.days_payables_outstanding(led, AS_OF, window_days=90), D("20"))


class TestDaysToLate(unittest.TestCase):
    def test_weighted_average_is_amount_weighted(self):
        led = ledger([
            inv("I1", "C1", 100, 0, paid=100, paid_days_after_due=10),
            inv("I2", "C1", 300, 0, paid=300, paid_days_after_due=20),
        ])
        # (100*10 + 300*20) / 400 = 17.5
        self.assertEqual(metrics.weighted_days_to_late(led)["C1"], D("17.5"))

    def test_early_payment_counts_as_zero_days_late(self):
        led = ledger([inv("I1", "C1", 500, 0, paid=500, paid_days_after_due=-5)])
        self.assertEqual(metrics.weighted_days_to_late(led)["C1"], D("0"))

    def test_unpaid_invoices_are_not_used_for_the_average(self):
        led = ledger([
            inv("I1", "C1", 100, 0, paid=100, paid_days_after_due=10),
            inv("I2", "C1", 900, 40),
        ])
        self.assertEqual(metrics.weighted_days_to_late(led)["C1"], D("10"))

    def test_customer_with_no_settled_invoice_is_absent(self):
        led = ledger([inv("I1", "C1", 900, 40)])
        self.assertNotIn("C1", metrics.weighted_days_to_late(led))


class TestArAsAt(unittest.TestCase):
    def test_counts_an_invoice_that_is_still_unpaid_at_that_date(self):
        led = ledger([inv("I1", "C1", 500, 0, paid=500, paid_days_after_due=40)])
        earlier = AS_OF - timedelta(days=30)
        self.assertEqual(metrics.ar_at(led, earlier), D("500"))

    def test_excludes_cash_received_before_that_date(self):
        # due 10 days ago, settled 2 days after the due date => cash already in
        led = ledger([inv("I1", "C1", 500, 10, paid=500, paid_days_after_due=2)])
        self.assertEqual(metrics.ar_at(led, AS_OF), D("0"))

    def test_excludes_invoices_issued_after_that_date(self):
        led = ledger([inv("I1", "C1", 500, 0)])
        self.assertEqual(metrics.ar_at(led, AS_OF - timedelta(days=60)), D("0"))

    def test_ar_at_the_reporting_date_equals_total_ar(self):
        led = ledger([inv("I1", "C1", 500, 40), inv("I2", "C1", 200, 10, paid=200, paid_days_after_due=1)])
        self.assertEqual(metrics.ar_at(led, AS_OF), metrics.total_ar(led, AS_OF))


class TestProvision(unittest.TestCase):
    def test_provision_applies_bucket_rates_to_bucket_balances(self):
        led = ledger([
            inv("I1", "C1", 1000, 0),
            inv("I2", "C1", 500, 45),
            inv("I3", "C1", 200, 200),
        ])
        rates = {"current": D("0.005"), "d1_30": D("0.02"),
                 "d31_60": D("0.08"), "d61_90": D("0.20"), "d90_plus": D("0.45")}
        # 1000*.005 + 500*.08 + 200*.45 = 5 + 40 + 90 = 135
        self.assertEqual(metrics.expected_credit_loss(led, AS_OF, rates), D("135.000"))


if __name__ == "__main__":
    unittest.main()
