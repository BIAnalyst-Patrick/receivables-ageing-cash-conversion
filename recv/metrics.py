"""Receivables and working-capital measures.

Conventions
-----------
* Money is ``Decimal`` throughout; results are quantised to two places.
* Ageing is driven by *days overdue* against the due date, not the invoice date.
* DSO and best-possible DSO divide a stated nominal sales window (default 90
  days) by the credit sales booked in it.
* DIO and DPO divide by the month-normalised span actually covered by the
  monthly snapshots (30 days per month), which is the annualised run-rate.

Every function here is pure: it takes a ledger and returns a number, so the
same inputs always give the same answer.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .model import Ledger

ZERO = Decimal("0")
Q = Decimal("0.01")

BUCKETS = ("current", "d1_30", "d31_60", "d61_90", "d90_plus")

# Loss rates used for the IFRS 9 style provision. Assumed, not fitted; see
# docs/01_method.md and the limits section of the README.
DEFAULT_LOSS_RATES = {
    "current": Decimal("0.005"),
    "d1_30": Decimal("0.02"),
    "d31_60": Decimal("0.08"),
    "d61_90": Decimal("0.20"),
    "d90_plus": Decimal("0.45"),
}


def _q(value: Decimal) -> Decimal:
    return value.quantize(Q, rounding=ROUND_HALF_UP)


def days_overdue(due_date: date, as_of: date) -> int:
    return (as_of - due_date).days


def bucket_for(due_date: date, as_of: date) -> str:
    overdue = days_overdue(due_date, as_of)
    if overdue <= 0:
        return "current"
    if overdue <= 30:
        return "d1_30"
    if overdue <= 60:
        return "d31_60"
    if overdue <= 90:
        return "d61_90"
    return "d90_plus"


def ageing_buckets(ledger: Ledger, as_of: date) -> dict[str, Decimal]:
    totals = {name: ZERO for name in BUCKETS}
    for inv in ledger.invoices:
        balance = inv.outstanding
        if balance <= ZERO:
            continue
        totals[bucket_for(inv.due_date, as_of)] += balance
    return totals


def total_ar(ledger: Ledger, as_of: date) -> Decimal:
    return sum((i.outstanding for i in ledger.invoices if i.outstanding > ZERO), ZERO)


def ar_at(ledger: Ledger, when: date) -> Decimal:
    """Receivables as they stood on a past date.

    An invoice counts only if it was issued by then, and only the part not yet
    settled by then: cash dated after ``when`` has not arrived yet.
    """
    total = ZERO
    for inv in ledger.invoices:
        if inv.invoice_date > when:
            continue
        paid_by_then = inv.paid_amount if (inv.paid_date and inv.paid_date <= when) else ZERO
        balance = inv.amount - paid_by_then
        if balance > ZERO:
            total += balance
    return total


def overdue_ar(ledger: Ledger, as_of: date) -> Decimal:
    return sum(
        (i.outstanding for i in ledger.invoices
         if i.outstanding > ZERO and i.due_date < as_of),
        ZERO,
    )


def _months_in_window(ledger: Ledger, as_of: date, window_days: int):
    start = as_of - timedelta(days=window_days)
    picked = []
    for snap in ledger.months:
        year, month = (int(p) for p in snap.month.split("-"))
        if date(year, month, 1) >= start:
            picked.append(snap)
    return picked


def credit_sales(ledger: Ledger, as_of: date, window_days: int = 90) -> Decimal:
    return sum((m.revenue for m in _months_in_window(ledger, as_of, window_days)), ZERO)


def dso(ledger: Ledger, as_of: date, window_days: int = 90) -> Decimal | None:
    """Days sales outstanding: receivables / average daily credit sales."""
    sales = credit_sales(ledger, as_of, window_days)
    if sales <= ZERO:
        return None
    daily = sales / Decimal(window_days)
    return _q(total_ar(ledger, as_of) / daily)


def best_possible_dso(ledger: Ledger, as_of: date, window_days: int = 90) -> Decimal | None:
    """DSO if every overdue invoice were collected and only current AR remained."""
    sales = credit_sales(ledger, as_of, window_days)
    if sales <= ZERO:
        return None
    daily = sales / Decimal(window_days)
    return _q(ageing_buckets(ledger, as_of)["current"] / daily)


def collection_effectiveness_index(
    opening_ar: Decimal,
    credit_sales: Decimal,
    closing_ar: Decimal,
    closing_current: Decimal,
) -> Decimal | None:
    """CEI = collected / collectible, as a percentage."""
    collectible = opening_ar + credit_sales - closing_current
    if collectible <= ZERO:
        return None
    collected = opening_ar + credit_sales - closing_ar
    return _q(collected / collectible * Decimal("100"))


def _snapshot_rates(ledger: Ledger, as_of: date, window_days: int):
    snaps = _months_in_window(ledger, as_of, window_days)
    if not snaps:
        return None, None, ZERO
    days = Decimal(30 * len(snaps))
    cogs = sum((m.cogs for m in snaps), ZERO)
    if cogs <= ZERO:
        return None, None, ZERO
    per_day = cogs / days
    avg_inventory = sum((m.inventory_value for m in snaps), ZERO) / Decimal(len(snaps))
    avg_payables = sum((m.payables_value for m in snaps), ZERO) / Decimal(len(snaps))
    return avg_inventory, avg_payables, per_day


def days_inventory_outstanding(ledger: Ledger, as_of: date, window_days: int = 90) -> Decimal | None:
    avg_inventory, _, per_day = _snapshot_rates(ledger, as_of, window_days)
    if avg_inventory is None or per_day <= ZERO:
        return None
    return _q(avg_inventory / per_day)


def days_payables_outstanding(ledger: Ledger, as_of: date, window_days: int = 90) -> Decimal | None:
    _, avg_payables, per_day = _snapshot_rates(ledger, as_of, window_days)
    if avg_payables is None or per_day <= ZERO:
        return None
    return _q(avg_payables / per_day)


def cash_conversion_cycle(dso: Decimal | None, dio: Decimal | None, dpo: Decimal | None) -> Decimal | None:
    """DSO + DIO - DPO. The DSO leg can be negative when customers prepay."""
    if dso is None or dio is None or dpo is None:
        return None
    return _q(dso + dio - dpo)


def weighted_days_to_late(ledger: Ledger) -> dict[str, Decimal]:
    """Amount-weighted average days paid after the due date, per customer.

    Only settled invoices carry payment behaviour. Early payment counts as zero.
    """
    weighted: dict[str, Decimal] = {}
    weight: dict[str, Decimal] = {}
    for inv in ledger.invoices:
        if inv.paid_date is None or inv.paid_amount <= ZERO:
            continue
        late = max(0, (inv.paid_date - inv.due_date).days)
        weighted[inv.customer_id] = weighted.get(inv.customer_id, ZERO) + inv.paid_amount * late
        weight[inv.customer_id] = weight.get(inv.customer_id, ZERO) + inv.paid_amount
    return {cid: weighted[cid] / weight[cid] for cid in weighted}


def expected_credit_loss(
    ledger: Ledger,
    as_of: date,
    rates: dict[str, Decimal] | None = None,
) -> Decimal:
    """Ageing-matrix provision: bucket balance x bucket loss rate."""
    rates = rates or DEFAULT_LOSS_RATES
    buckets = ageing_buckets(ledger, as_of)
    return sum((buckets[name] * rates[name] for name in BUCKETS), ZERO).quantize(Q)


def disputed_balance(ledger: Ledger, as_of: date) -> Decimal:
    return sum(
        (i.outstanding for i in ledger.invoices
         if i.is_disputed and i.outstanding > ZERO),
        ZERO,
    )
