"""Behavioural tests for the decision layer.

These state the rules an owner would apply: chase the accounts with the most
recoverable cash first, tighten terms for chronic late payers, and size the
cash unlock from both recovery and the DSO gap.
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal as D

from recv.model import Customer, Invoice, MonthSnapshot, Ledger
from recv import decisions


AS_OF = date(2026, 6, 30)


def cust(cid, terms=30, grade="B"):
    return Customer(
        customer_id=cid,
        name=f"Customer {cid}",
        segment="medium",
        credit_terms_days=terms,
        credit_limit=D("100000"),
        risk_grade=grade,
        sales_rep="Rep A",
    )


def inv(iid, cid, amount, days_overdue, paid=0, paid_late=None):
    due = AS_OF - timedelta(days=days_overdue)
    return Invoice(
        invoice_id=iid,
        customer_id=cid,
        invoice_date=due - timedelta(days=30),
        due_date=due,
        amount=D(str(amount)),
        paid_amount=D(str(paid)),
        paid_date=None if paid_late is None else due + timedelta(days=paid_late),
        is_disputed=False,
    )


def make(invoices, months=None, terms=None, grades=None):
    ids = sorted({i.customer_id for i in invoices})
    terms = terms or {}
    grades = grades or {}
    return Ledger(
        customers={c: cust(c, terms.get(c, 30), grades.get(c, "B")) for c in ids},
        invoices=list(invoices),
        months=months or [],
        unapplied_cash=D("0"),
        as_of=AS_OF,
    )


class TestChaseList(unittest.TestCase):
    def test_ranks_accounts_by_expected_recovery_descending(self):
        # C1: 1000 fully in the 90+ bucket -> 55% recoverable = 550
        # C2: 500 in the 31-60 bucket      -> 92% recoverable = 460
        led = make([inv("I1", "C1", 1000, 200), inv("I2", "C2", 500, 45)])
        ranked = decisions.chase_list(led, AS_OF)
        self.assertEqual([r.customer_id for r in ranked], ["C1", "C2"])
        self.assertEqual(ranked[0].expected_recovery, D("550.00"))
        self.assertEqual(ranked[1].expected_recovery, D("460.00"))

    def test_settled_accounts_are_not_chased(self):
        led = make([
            inv("I1", "C1", 1000, 200),
            inv("I2", "C2", 500, 45, paid=500, paid_late=3),
        ])
        self.assertEqual([r.customer_id for r in decisions.chase_list(led, AS_OF)], ["C1"])

    def test_expected_recovery_never_exceeds_the_overdue_balance(self):
        led = make([inv("I1", "C1", 1000, 200)])
        item = decisions.chase_list(led, AS_OF)[0]
        self.assertLessEqual(item.expected_recovery, item.overdue_balance)

    def test_limit_caps_the_returned_actions(self):
        led = make([
            inv("I1", "C1", 1000, 200),
            inv("I2", "C2", 500, 45),
            inv("I3", "C3", 100, 10),
        ])
        self.assertEqual(len(decisions.chase_list(led, AS_OF, limit=2)), 2)


class TestTerms(unittest.TestCase):
    def test_chronic_late_payer_on_60_day_terms_is_moved_to_30(self):
        led = make(
            [inv("I1", "C1", 1000, 10, paid=200, paid_late=25),
             inv("I2", "C1", 500, 40)],
            terms={"C1": 60},
        )
        recs = decisions.terms_changes(led, AS_OF)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].customer_id, "C1")
        self.assertEqual(recs[0].current_terms_days, 60)
        self.assertEqual(recs[0].recommended_terms_days, 30)

    def test_chronic_late_payer_already_on_30_days_moves_to_cod(self):
        led = make([inv("I1", "C1", 1000, 40, paid=500, paid_late=30)],
                   terms={"C1": 30})
        recs = decisions.terms_changes(led, AS_OF)
        self.assertEqual(recs[0].recommended_terms_days, 0)
        self.assertEqual(recs[0].recommended_terms_label, "Cash on delivery")

    def test_reliable_payer_is_not_touched(self):
        led = make([inv("I1", "C1", 1000, 40)], terms={"C1": 60})
        self.assertEqual(decisions.terms_changes(led, AS_OF), [])

    def test_payer_with_no_settled_history_is_not_touched(self):
        led = make([inv("I1", "C1", 1000, 40)], terms={"C1": 60})
        self.assertEqual(decisions.terms_changes(led, AS_OF), [])


class TestCashUnlock(unittest.TestCase):
    def test_separates_gross_opportunity_from_realistic_recovery(self):
        led = make(
            [inv("I1", "C1", 1000, 200)],
            months=[MonthSnapshot("2026-06", revenue=D("9000"), cogs=D("5000"),
                                  inventory_value=D("0"), payables_value=D("0"))],
        )
        unlock = decisions.cash_unlock(led, AS_OF)
        # AR 1000, sales 9000 over 90 days => 100/day => DSO 10 days, nothing current
        self.assertEqual(unlock["dso_days"], D("10"))
        self.assertEqual(unlock["best_possible_dso_days"], D("0"))
        self.assertEqual(unlock["cash_tied_up_in_overdue"], D("1000.00"))
        self.assertEqual(unlock["recoverable_now"], D("550.00"))

    def test_total_is_the_realistic_recovery_not_the_sum_of_both(self):
        led = make(
            [inv("I1", "C1", 1000, 200)],
            months=[MonthSnapshot("2026-06", revenue=D("9000"), cogs=D("5000"),
                                  inventory_value=D("0"), payables_value=D("0"))],
        )
        unlock = decisions.cash_unlock(led, AS_OF)
        self.assertEqual(unlock["total"], unlock["recoverable_now"])
        self.assertNotEqual(unlock["total"],
                            unlock["recoverable_now"] + unlock["cash_tied_up_in_overdue"])


if __name__ == "__main__":
    unittest.main()
