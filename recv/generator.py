"""Deterministic synthetic ledger for a Kenyan wholesale distributor.

The data is simulated from the mechanism documented here and in
``docs/01_method.md``. Because the mechanism is seeded and reproducible, the
analysis can be graded against a known answer rather than merely asserted.

Seeded behaviours:
  * 60 trade customers across three segments with terms of 30, 45 or 60 days.
  * Per-customer lateness profiles, so some accounts are chronic late payers
    and others pay on or before the due date.
  * ~10% of invoices never settle; ~8% settle partially, leaving a balance.
  * A handful of disputed invoices that are open at the reporting date.
  * One unapplied cash receipt held on account, not matched to an invoice.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .model import Customer, Invoice, Ledger, MonthSnapshot

ZERO = Decimal("0")
Q = Decimal("0.01")
DEFAULT_SEED = 20260101
AS_OF = date(2026, 6, 30)

SEGMENTS = (
    # segment, count, amount low, amount high, terms
    ("large", 8, 80000, 260000, 60),
    ("medium", 22, 20000, 85000, 45),
    ("small", 30, 3000, 22000, 30),
)

NAMES = (
    "Mavuno Wholesale", "Baraka Traders", "Riverside Distributors", "Juja Fresh Mart",
    "Nakuru Grocers", "Tumaini Stores", "Kilele Supplies", "Zawadi Wholesale",
    "Chui Trading", "Sunrise Merchants", "Oasis Distributors", "Simba Wholesale",
    "Pamoja Traders", "Kaskazi Supplies", "Upendo Stores", "Mwangaza Wholesale",
    "Tembo Traders", "Neema Distributors", "Amani Mart", "Bahari Wholesale",
    "Kazi Supplies", "Faraja Stores", "Jipange Traders", "Imara Wholesale",
    "Songa Supplies", "Tuvute Distributors", "Mkuki Traders", "Boresha Stores",
    "Fanaka Wholesale", "Sanaa Distributors", "Tamati Traders", "Zinduka Supplies",
    "Kipaji Mart", "Nyota Wholesale", "Rehema Distributors", "Tunza Stores",
    "Bidii Traders", "Chachu Supplies", "Dhahabu Wholesale", "Ekari Traders",
    "Furaha Distributors", "Giza Supplies", "Haki Wholesale", "Imani Stores",
    "Jasiri Traders", "Kito Distributors", "Lulu Supplies", "Mali Wholesale",
    "Nuru Traders", "Onyx Distributors", "Pendo Stores", "Rafiki Wholesale",
    "Shujaa Supplies", "Tiwi Traders", "Uhuru Distributors", "Vitu Stores",
    "Wema Wholesale", "Yatima Traders", "Zuri Supplies", "Anga Distributors",
)

REPS = ("Achieng", "Barasa", "Chebet", "Dida", "Ekiru")


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2))).quantize(Q, rounding=ROUND_HALF_UP)


def _build_customers(rnd: random.Random) -> dict[str, Customer]:
    customers: dict[str, Customer] = {}
    index = 0
    for segment, count, low, high, terms in SEGMENTS:
        for _ in range(count):
            cid = f"C{index + 1:03d}"
            name = NAMES[index]
            # Terms vary by one band for a few accounts in each segment.
            account_terms = terms
            if rnd.random() < 0.15:
                account_terms = max(0, terms - 15)
            grade = rnd.choices(("A", "B", "C"), weights=(0.35, 0.45, 0.20))[0]
            customers[cid] = Customer(
                customer_id=cid,
                name=name,
                segment=segment,
                credit_terms_days=account_terms,
                credit_limit=_money(rnd.uniform(high * 2, high * 5)),
                risk_grade=grade,
                sales_rep=rnd.choice(REPS),
            )
            index += 1
    return customers


def _months() -> list[str]:
    out = []
    year, month = 2025, 1
    for _ in range(18):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def generate(seed: int = DEFAULT_SEED) -> Ledger:
    rnd = random.Random(seed)
    customers = _build_customers(rnd)

    # Payment behaviour is a property of the account, not of the invoice.
    mean_late = {}
    unpaid_prob = {}
    for cid, customer in customers.items():
        if customer.risk_grade == "A":
            mean_late[cid] = rnd.gauss(2, 3)
            unpaid_prob[cid] = 0.03
        elif customer.risk_grade == "B":
            mean_late[cid] = rnd.gauss(12, 7)
            unpaid_prob[cid] = 0.08
        else:
            mean_late[cid] = rnd.gauss(32, 12)
            unpaid_prob[cid] = 0.22

    invoices: list[Invoice] = []
    revenue_by_month: dict[str, Decimal] = {}
    counter = 0

    for month in _months():
        year, mon = (int(p) for p in month.split("-"))
        month_revenue = ZERO
        for cid, customer in customers.items():
            segment, count, low, high, _ = next(s for s in SEGMENTS if s[0] == customer.segment)
            if customer.segment == "large":
                n_invoices = rnd.choices((1, 2, 3), weights=(0.3, 0.5, 0.2))[0]
            elif customer.segment == "medium":
                n_invoices = rnd.choices((0, 1, 2), weights=(0.2, 0.6, 0.2))[0]
            else:
                n_invoices = rnd.choices((0, 1), weights=(0.45, 0.55))[0]

            for _ in range(n_invoices):
                counter += 1
                day = rnd.randint(1, 28)
                invoice_date = date(year, mon, day)
                if invoice_date > AS_OF:
                    continue
                due_date = invoice_date + timedelta(days=customer.credit_terms_days)
                amount = _money(rnd.uniform(low, high))
                month_revenue += amount

                late = max(0, int(round(rnd.gauss(mean_late[cid], 6))))
                paid_amount = ZERO
                paid_date = None
                if rnd.random() >= unpaid_prob[cid]:
                    settle_date = due_date + timedelta(days=late)
                    if settle_date <= AS_OF:
                        paid_date = settle_date
                        if rnd.random() < 0.08:
                            paid_amount = _money(float(amount) * rnd.uniform(0.4, 0.8))
                        else:
                            paid_amount = amount

                invoices.append(Invoice(
                    invoice_id=f"INV{counter:05d}",
                    customer_id=cid,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    amount=amount,
                    paid_amount=paid_amount,
                    paid_date=paid_date,
                    is_disputed=False,
                ))
        revenue_by_month[month] = month_revenue

    # A few disputed invoices, chosen from what is still open at the report date.
    open_invoices = [i for i in invoices if i.outstanding > ZERO and i.due_date < AS_OF]
    rnd.shuffle(open_invoices)
    disputed = {
        i.invoice_id for i in open_invoices[:3]
    }
    invoices = [
        Invoice(**{**i.__dict__, "is_disputed": i.invoice_id in disputed})
        for i in invoices
    ]

    # Monthly working-capital snapshots. Cost ratio and holding days drift a
    # little month to month so the CCC is not a straight line.
    months: list[MonthSnapshot] = []
    for month in _months():
        revenue = revenue_by_month[month]
        cost_ratio = Decimal(str(round(rnd.uniform(0.62, 0.72), 4)))
        cogs = (revenue * cost_ratio).quantize(Q)
        inventory_days = Decimal(str(round(rnd.uniform(38, 54), 2)))
        payable_days = Decimal(str(round(rnd.uniform(33, 47), 2)))
        months.append(MonthSnapshot(
            month=month,
            revenue=revenue.quantize(Q),
            cogs=cogs,
            inventory_value=(cogs / Decimal(30) * inventory_days).quantize(Q),
            payables_value=(cogs / Decimal(30) * payable_days).quantize(Q),
        ))

    return Ledger(
        customers=customers,
        invoices=invoices,
        months=months,
        unapplied_cash=_money(12_500),
        as_of=AS_OF,
        notes=[
            "Synthetic ledger generated from a documented, seeded mechanism.",
            "Credit notes are out of scope; invoices carry partial payments only.",
            "One unapplied cash receipt is held on account and not matched.",
        ],
    )


def to_dict(ledger: Ledger) -> dict:
    """Canonical serialisation, used for the fingerprint and the data file."""
    return {
        "as_of": ledger.as_of.isoformat(),
        "unapplied_cash": str(ledger.unapplied_cash),
        "notes": ledger.notes,
        "customers": [
            {
                "customer_id": c.customer_id, "name": c.name, "segment": c.segment,
                "credit_terms_days": c.credit_terms_days, "credit_limit": str(c.credit_limit),
                "risk_grade": c.risk_grade, "sales_rep": c.sales_rep,
            }
            for c in sorted(ledger.customers.values(), key=lambda c: c.customer_id)
        ],
        "invoices": [
            {
                "invoice_id": i.invoice_id, "customer_id": i.customer_id,
                "invoice_date": i.invoice_date.isoformat(), "due_date": i.due_date.isoformat(),
                "amount": str(i.amount), "paid_amount": str(i.paid_amount),
                "paid_date": i.paid_date.isoformat() if i.paid_date else None,
                "is_disputed": i.is_disputed,
            }
            for i in sorted(ledger.invoices, key=lambda i: i.invoice_id)
        ],
        "months": [
            {
                "month": m.month, "revenue": str(m.revenue), "cogs": str(m.cogs),
                "inventory_value": str(m.inventory_value), "payables_value": str(m.payables_value),
            }
            for m in ledger.months
        ],
    }


def fingerprint(ledger: Ledger) -> str:
    payload = json.dumps(to_dict(ledger), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
