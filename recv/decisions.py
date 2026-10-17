"""Turn the measures into decisions an owner can act on.

Ranking rule: cash at risk x likelihood of recovering it. An account that owes
a great deal but has gone quiet ranks below one that owes less and still pays,
because the point of the list is what will actually be collected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from . import metrics
from .model import Ledger

ZERO = Decimal("0")
Q = Decimal("0.01")

# Recovery haircuts by age, mirroring the provision matrix.
RECOVERY_RATES = {
    "d1_30": Decimal("0.98"),
    "d31_60": Decimal("0.92"),
    "d61_90": Decimal("0.80"),
    "d90_plus": Decimal("0.55"),
}

GRADE_FACTOR = {"A": Decimal("1.05"), "B": Decimal("1.00"), "C": Decimal("0.90")}

LATE_TERMS_THRESHOLD_DAYS = Decimal("15")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ChaseItem:
    rank: int
    customer_id: str
    customer_name: str
    overdue_balance: Decimal
    recovery_likelihood: Decimal
    expected_recovery: Decimal
    weighted_days_late: Decimal | None
    oldest_days_overdue: int
    action: str


@dataclass(frozen=True)
class TermsChange:
    customer_id: str
    customer_name: str
    current_terms_days: int
    recommended_terms_days: int
    recommended_terms_label: str
    weighted_days_late: Decimal
    overdue_balance: Decimal
    reason: str


def _customer_overdue(ledger: Ledger, as_of: date):
    """customer_id -> {bucket: balance} plus the oldest overdue day count."""
    buckets: dict[str, dict[str, Decimal]] = {}
    oldest: dict[str, int] = {}
    for inv in ledger.invoices:
        if inv.outstanding <= ZERO or inv.due_date >= as_of:
            continue
        bucket = metrics.bucket_for(inv.due_date, as_of)
        row = buckets.setdefault(inv.customer_id, {})
        row[bucket] = row.get(bucket, ZERO) + inv.outstanding
        age = metrics.days_overdue(inv.due_date, as_of)
        oldest[inv.customer_id] = max(oldest.get(inv.customer_id, 0), age)
    return buckets, oldest


def _action_for(oldest_days: int, disputed: bool) -> str:
    if disputed:
        return "Resolve the dispute before chasing: call the buyer, not the ledger"
    if oldest_days > 90:
        return "Formal demand, stop supply, agree a written payment plan"
    if oldest_days > 60:
        return "Owner-level call, withhold further credit, agree a dated plan"
    if oldest_days > 30:
        return "Phone the account, confirm the invoice is approved and scheduled"
    return "Send a dated reminder with the invoice copy and payment link"


def chase_list(ledger: Ledger, as_of: date, limit: int | None = None) -> list[ChaseItem]:
    buckets, oldest = _customer_overdue(ledger, as_of)
    late = metrics.weighted_days_to_late(ledger)
    disputed_ids = {
        i.customer_id for i in ledger.invoices if i.is_disputed and i.outstanding > ZERO
    }
    items = []
    for cid, row in buckets.items():
        overdue = sum(row.values(), ZERO)
        if overdue <= ZERO:
            continue
        grade = ledger.customers[cid].risk_grade
        factor = GRADE_FACTOR.get(grade, Decimal("1.00"))
        recovered = sum(
            (bal * RECOVERY_RATES.get(bucket, ZERO) for bucket, bal in row.items()), ZERO
        ) * factor
        recovered = min(recovered, overdue)
        items.append(ChaseItem(
            rank=0,
            customer_id=cid,
            customer_name=ledger.customers[cid].name,
            overdue_balance=_q(overdue),
            recovery_likelihood=_q(recovered / overdue),
            expected_recovery=_q(recovered),
            weighted_days_late=_q(late[cid]) if cid in late else None,
            oldest_days_overdue=oldest.get(cid, 0),
            action=_action_for(oldest.get(cid, 0), cid in disputed_ids),
        ))
    items.sort(key=lambda i: (-i.expected_recovery, -i.overdue_balance, i.customer_id))
    ranked = [ChaseItem(**{**i.__dict__, "rank": n}) for n, i in enumerate(items, start=1)]
    return ranked[:limit] if limit else ranked


def terms_changes(ledger: Ledger, as_of: date) -> list[TermsChange]:
    """Shorten terms for accounts that pay materially late, but only where history exists."""
    late = metrics.weighted_days_to_late(ledger)
    buckets, _ = _customer_overdue(ledger, as_of)
    out = []
    for cid, mean_late in late.items():
        if mean_late <= LATE_TERMS_THRESHOLD_DAYS:
            continue
        overdue = sum(buckets.get(cid, {}).values(), ZERO)
        if overdue <= ZERO:
            continue
        customer = ledger.customers[cid]
        if customer.credit_terms_days > 30:
            recommended, label = 30, "30 days"
            reason = (f"Pays {_q(mean_late)} days late on average; the {customer.credit_terms_days}-day "
                      f"term is being used as free credit.")
        else:
            recommended, label = 0, "Cash on delivery"
            reason = (f"Pays {_q(mean_late)} days late even on {customer.credit_terms_days}-day terms; "
                      f"term credit is not working for this account.")
        out.append(TermsChange(
            customer_id=cid,
            customer_name=customer.name,
            current_terms_days=customer.credit_terms_days,
            recommended_terms_days=recommended,
            recommended_terms_label=label,
            weighted_days_late=_q(mean_late),
            overdue_balance=_q(overdue),
            reason=reason,
        ))
    out.sort(key=lambda r: (-r.weighted_days_late, r.customer_id))
    return out


def cash_unlock(ledger: Ledger, as_of: date) -> dict[str, Decimal]:
    """Size the opportunity without double counting it.

    ``cash_tied_up_in_overdue`` is the gross receivable sitting past its due
    date. ``recoverable_now`` is the realistically collectible share of it.
    ``total`` is the realistic figure; adding the two would count the same cash
    twice.
    """
    dso_days = metrics.dso(ledger, as_of) or ZERO
    bpdso = metrics.best_possible_dso(ledger, as_of) or ZERO
    tied_up = metrics.overdue_ar(ledger, as_of)
    recoverable = sum((i.expected_recovery for i in chase_list(ledger, as_of)), ZERO)
    return {
        "dso_days": _q(dso_days),
        "best_possible_dso_days": _q(bpdso),
        "dso_gap_days": _q(dso_days - bpdso),
        "cash_tied_up_in_overdue": _q(tied_up),
        "recoverable_now": _q(recoverable),
        "total": _q(recoverable),
    }
