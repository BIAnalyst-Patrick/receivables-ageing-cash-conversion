"""Run the whole analysis: measures, decisions, checks and output files."""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import decisions, metrics
from .generator import fingerprint, generate, to_dict
from .model import Ledger

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
TABLES = OUT / "tables"
DATA = ROOT / "data"


def analyse(ledger: Ledger) -> dict:
    as_of = ledger.as_of
    buckets = metrics.ageing_buckets(ledger, as_of)
    dso = metrics.dso(ledger, as_of)
    bpdso = metrics.best_possible_dso(ledger, as_of)
    dio = metrics.days_inventory_outstanding(ledger, as_of)
    dpo = metrics.days_payables_outstanding(ledger, as_of)
    ccc = metrics.cash_conversion_cycle(dso, dio, dpo)
    sales_90 = metrics.credit_sales(ledger, as_of)
    chase = decisions.chase_list(ledger, as_of)
    unlock = decisions.cash_unlock(ledger, as_of)
    late = metrics.weighted_days_to_late(ledger)

    opening_date = as_of - timedelta(days=90)
    cei = metrics.collection_effectiveness_index(
        opening_ar=metrics.ar_at(ledger, opening_date),
        credit_sales=sales_90,
        closing_ar=metrics.total_ar(ledger, as_of),
        closing_current=buckets["current"],
    )

    return {
        "as_of": as_of.isoformat(),
        "fingerprint": fingerprint(ledger),
        "customers": len(ledger.customers),
        "invoices": len(ledger.invoices),
        "open_invoices": sum(1 for i in ledger.invoices if i.outstanding > 0),
        "revenue_last_90": sales_90,
        "buckets": buckets,
        "total_ar": metrics.total_ar(ledger, as_of),
        "overdue_ar": metrics.overdue_ar(ledger, as_of),
        "disputed_balance": metrics.disputed_balance(ledger, as_of),
        "unapplied_cash": ledger.unapplied_cash,
        "dso": dso,
        "best_possible_dso": bpdso,
        "dio": dio,
        "dpo": dpo,
        "ccc": ccc,
        "cei": cei,
        "provision": metrics.expected_credit_loss(ledger, as_of),
        "chase": chase,
        "terms": decisions.terms_changes(ledger, as_of),
        "unlock": unlock,
        "late": late,
    }


def validate(ledger: Ledger, result: dict) -> list[tuple[str, bool, str]]:
    """Independent checks a reader can repeat. Each returns PASS/FAIL + detail."""
    as_of = ledger.as_of
    buckets = result["buckets"]
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append((name, bool(ok), detail))

    add(
        "Ageing buckets reconcile to total receivables",
        sum(buckets.values()) == result["total_ar"],
        f"sum(buckets)={sum(buckets.values())} total_ar={result['total_ar']}",
    )
    add(
        "Receivables are positive",
        result["total_ar"] > 0,
        f"total_ar={result['total_ar']}",
    )
    add(
        "Overdue is a subset of receivables",
        0 < result["overdue_ar"] <= result["total_ar"],
        f"overdue={result['overdue_ar']} of {result['total_ar']}",
    )
    add(
        "DSO is at least best-possible DSO",
        result["dso"] is not None and result["best_possible_dso"] is not None
        and result["dso"] >= result["best_possible_dso"],
        f"dso={result['dso']} bpdso={result['best_possible_dso']}",
    )
    add(
        "Cash conversion cycle equals DSO + DIO - DPO",
        result["ccc"] == (result["dso"] + result["dio"] - result["dpo"]).quantize(Decimal("0.01")),
        f"ccc={result['ccc']} components={result['dso']}+{result['dio']}-{result['dpo']}",
    )
    add(
        "Collection effectiveness index is a percentage",
        result["cei"] is not None and 0 <= result["cei"] <= 100,
        f"cei={result['cei']}",
    )
    add(
        "Provision does not exceed receivables",
        0 < result["provision"] < result["total_ar"],
        f"provision={result['provision']} of {result['total_ar']}",
    )
    add(
        "Chase list is ranked by expected recovery",
        [c.expected_recovery for c in result["chase"]]
        == sorted((c.expected_recovery for c in result["chase"]), reverse=True),
        f"{len(result['chase'])} accounts ranked",
    )
    add(
        "No expected recovery exceeds the balance owed",
        all(c.expected_recovery <= c.overdue_balance for c in result["chase"]),
        f"max recovery={max((c.expected_recovery for c in result['chase']), default=0)}",
    )
    add(
        "Realistic recovery never exceeds the gross overdue balance",
        result["unlock"]["recoverable_now"] <= result["unlock"]["cash_tied_up_in_overdue"],
        f"recoverable={result['unlock']['recoverable_now']} tied_up={result['unlock']['cash_tied_up_in_overdue']}",
    )
    add(
        "Every invoice's due date follows its customer's terms",
        all((i.due_date - i.invoice_date).days == ledger.customers[i.customer_id].credit_terms_days
            for i in ledger.invoices),
        f"{len(ledger.invoices)} invoices checked",
    )
    add(
        "No invoice is dated after the reporting date",
        all(i.invoice_date <= as_of for i in ledger.invoices),
        f"as_of={as_of}",
    )
    add(
        "Days-to-late is non-negative for every customer",
        all(v >= 0 for v in result["late"].values()),
        f"{len(result['late'])} customers with payment history",
    )
    add(
        "Regenerating from the same seed reproduces the ledger exactly",
        fingerprint(generate()) == result["fingerprint"],
        f"fingerprint={result['fingerprint'][:16]}...",
    )
    add(
        "Chase list covers every customer with an overdue balance",
        len({c.customer_id for c in result["chase"]})
        == len({i.customer_id for i in ledger.invoices
                if i.outstanding > 0 and i.due_date < as_of}),
        f"{len(result['chase'])} accounts",
    )
    return checks


def _money(value) -> str:
    return f"{value:,.2f}" if isinstance(value, Decimal) else str(value)


def write_outputs(ledger: Ledger, result: dict, checks: list[tuple[str, bool, str]]) -> None:
    for path in (OUT, TABLES, DATA):
        path.mkdir(parents=True, exist_ok=True)

    (DATA / "ledger.json").write_text(json.dumps(to_dict(ledger), indent=2), encoding="utf-8")

    key = {
        "as_of": result["as_of"],
        "fingerprint": result["fingerprint"],
        "revenue_last_90": str(result["revenue_last_90"]),
        "total_ar": str(result["total_ar"]),
        "overdue_ar": str(result["overdue_ar"]),
        "disputed_balance": str(result["disputed_balance"]),
        "unapplied_cash": str(result["unapplied_cash"]),
        "buckets": {k: str(v) for k, v in result["buckets"].items()},
        "dso": str(result["dso"]),
        "best_possible_dso": str(result["best_possible_dso"]),
        "dio": str(result["dio"]),
        "dpo": str(result["dpo"]),
        "ccc": str(result["ccc"]),
        "cei": str(result["cei"]),
        "provision": str(result["provision"]),
        "unlock": {k: str(v) for k, v in result["unlock"].items()},
        "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in checks],
    }
    (OUT / "answer_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")

    key_lines = [
        f"# Answer key — synthetic wholesaler receivables, {result['as_of']}",
        "",
        f"Data fingerprint: `{result['fingerprint']}`",
        "",
        "Every figure below is produced by code in `recv/`, not typed by hand.",
        "Re-run `make run` and this file is regenerated; a matching fingerprint",
        "means every number is reproduced exactly.",
        "",
        "| Measure | Value |",
        "|---|---:|",
        f"| Credit sales, last 90 days | {_money(result['revenue_last_90'])} |",
        f"| Total receivables | {_money(result['total_ar'])} |",
        f"| Overdue receivables | {_money(result['overdue_ar'])} |",
        f"| Disputed balance | {_money(result['disputed_balance'])} |",
        f"| Unapplied cash | {_money(result['unapplied_cash'])} |",
        f"| DSO | {result['dso']} days |",
        f"| Best-possible DSO | {result['best_possible_dso']} days |",
        f"| DSO gap | {result['unlock']['dso_gap_days']} days |",
        f"| DIO | {result['dio']} days |",
        f"| DPO | {result['dpo']} days |",
        f"| Cash conversion cycle | {result['ccc']} days |",
        f"| Collection effectiveness index | {result['cei']}% |",
        f"| Expected credit loss provision | {_money(result['provision'])} |",
        f"| Cash recoverable now | {_money(result['unlock']['recoverable_now'])} |",
        "",
        "## Ageing buckets",
        "",
        "| Bucket | Balance | Share of receivables |",
        "|---|---:|---:|",
    ]
    for name, value in result["buckets"].items():
        share = (value / result["total_ar"] * 100).quantize(Decimal("0.01")) if result["total_ar"] else Decimal("0")
        key_lines.append(f"| {name} | {value:,.2f} | {share}% |")
    key_lines += [
        "",
        f"All figures are **synthetic** — generated from a documented, seeded mechanism,",
        "not taken from a real company. See the limits section of the README.",
        "",
    ]
    (OUT / "answer_key.md").write_text("\n".join(key_lines), encoding="utf-8")

    with (TABLES / "ageing.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bucket", "balance", "share_of_ar"])
        for name, value in result["buckets"].items():
            share = (value / result["total_ar"] * 100).quantize(Decimal("0.01")) if result["total_ar"] else Decimal("0")
            w.writerow([name, value, share])

    with (TABLES / "chase_list.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "customer_id", "customer", "overdue", "expected_recovery",
                    "recovery_likelihood", "weighted_days_late", "oldest_days_overdue", "action"])
        for c in result["chase"]:
            w.writerow([c.rank, c.customer_id, c.customer_name, c.overdue_balance,
                        c.expected_recovery, c.recovery_likelihood,
                        c.weighted_days_late, c.oldest_days_overdue, c.action])

    with (TABLES / "terms_changes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_id", "customer", "current_terms_days",
                    "recommended_terms_days", "recommended_terms_label",
                    "weighted_days_late", "overdue_balance"])
        for t in result["terms"]:
            w.writerow([t.customer_id, t.customer_name, t.current_terms_days,
                        t.recommended_terms_days, t.recommended_terms_label,
                        t.weighted_days_late, t.overdue_balance])

    passed = sum(1 for _, ok, _ in checks if ok)
    lines = [
        "# Validation report",
        "",
        f"Reporting date: **{result['as_of']}**. Data fingerprint: `{result['fingerprint']}`.",
        "",
        f"**{passed}/{len(checks)} checks passed.**",
        "",
        "| # | Check | Result | Detail |",
        "|---|-------|--------|--------|",
    ]
    for n, (name, ok, detail) in enumerate(checks, start=1):
        lines.append(f"| {n} | {name} | {'PASS' if ok else 'FAIL'} | `{detail}` |")
    lines += [
        "",
        "Every check is computed by `recv/pipeline.py:validate` and can be re-run with `make run`.",
        "They compare derived figures against independent identities (buckets against total",
        "receivables, CCC against its own components, the chase list against its sort order)",
        "rather than against numbers copied into this file.",
        "",
    ]
    (OUT / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")


def run(seed: int | None = None) -> dict:
    ledger = generate() if seed is None else generate(seed)
    result = analyse(ledger)
    checks = validate(ledger, result)
    write_outputs(ledger, result, checks)
    return {"result": result, "checks": checks}
