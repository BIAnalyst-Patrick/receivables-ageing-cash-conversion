"""Data model for the receivables ledger.

Pure declarations: no behaviour lives here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    segment: str            # "large" | "medium" | "small"
    credit_terms_days: int  # 0 means cash on delivery
    credit_limit: Decimal
    risk_grade: str         # "A" | "B" | "C"
    sales_rep: str


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    customer_id: str
    invoice_date: date
    due_date: date
    amount: Decimal
    paid_amount: Decimal = ZERO
    paid_date: date | None = None
    is_disputed: bool = False

    @property
    def outstanding(self) -> Decimal:
        return self.amount - self.paid_amount


@dataclass(frozen=True)
class MonthSnapshot:
    month: str              # "YYYY-MM"
    revenue: Decimal
    cogs: Decimal
    inventory_value: Decimal
    payables_value: Decimal


@dataclass
class Ledger:
    customers: dict[str, Customer]
    invoices: list[Invoice]
    months: list[MonthSnapshot]
    unapplied_cash: Decimal
    as_of: date
    notes: list[str] = field(default_factory=list)
