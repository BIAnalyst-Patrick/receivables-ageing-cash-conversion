# Method

Everything the report asserts is computed by `recv/` and checked by `tests/`.
This note states the definitions so a reader can disagree with a formula
deliberately rather than guess at it.

## The data

`recv/generator.py` builds a synthetic 18-month ledger for a wholesale
distributor with 60 trade customers, 1,900-odd invoices and monthly
working-capital snapshots. It is seeded (`20260101`) and therefore
reproducible: the same seed produces a byte-identical ledger, fingerprinted with
SHA-256 over a canonical JSON serialisation.

The mechanism, deliberately chosen so the diagnostic has a knowable answer:

| Element | How it is generated |
|---|---|
| Customers | 60 across large / medium / small, terms of 30, 45 or 60 days, some varied by one band |
| Risk grade | A/B/C weighted 35/45/20 |
| Payment behaviour | A per-customer lateness profile: grade A ≈ 2 days late, B ≈ 12, C ≈ 32 |
| Non-payment | 3% / 8% / 22% of invoices by grade never settle |
| Partial settlement | 8% of settled invoices leave a 40-80% balance |
| Disputes | 3 open invoices are flagged as disputed |
| Cash | One unapplied receipt of KES 12,500 held on account |
| Cost and capital | Monthly COGS at a 62-72% cost ratio, inventory 38-54 days, payables 33-47 days |

What is deliberately **not** modelled: credit notes, multi-currency, taxes,
bad-debt write-offs and any post-reporting-date activity. Each of those would
change the numbers and none of them is silently approximated.

## The measures

All money is `Decimal` and quantised to two places; day counts are two places.

**Ageing** — an open invoice is bucketed by days past its **due date**, not its
invoice date: `current` (not yet due), `1-30`, `31-60`, `61-90`, `90+`. Only the
outstanding balance counts, so a part-paid invoice contributes its remainder.
The buckets sum to total receivables; this is asserted, not assumed.

**DSO** = receivables ÷ (credit sales in the window ÷ window days).

**Best-possible DSO** = current receivables ÷ the same daily sales. It is the
DSO the business would have if every overdue invoice were collected today, so
the gap between the two is the part of DSO that is a collection failure rather
than a terms decision.

Window convention: DSO and best-possible DSO use a stated **90-day nominal
window** of credit sales.

**DIO** = average inventory ÷ (COGS ÷ days) and **DPO** = average payables ÷
(COGS ÷ days). Here the divisor is the span actually covered by the monthly
snapshots, **30 days per month**, which is the annualised run-rate. The two
conventions differ on purpose and are stated wherever the numbers appear.

**Cash conversion cycle** = DSO + DIO − DPO.

**Collection effectiveness index** = (opening receivables + credit sales −
closing receivables) ÷ (opening receivables + credit sales − closing current
receivables) × 100. Opening receivables are rebuilt from the ledger at the
window start: an invoice counts only if it had been issued by then, and only
the part not yet settled by then. A business collecting everything it could
scores 100.

**Expected credit loss** uses an ageing matrix at 0.5% / 2% / 8% / 20% / 45% by
bucket, in the shape of the IFRS 9 simplified approach. The rates are
**assumed, not fitted** — see the limits section.

**Weighted days to late** = Σ(paid amount × days late) ÷ Σ(paid amount) per
customer, where days late is `max(0, paid date − due date)`. Early payment
counts as zero. Only settled invoices carry payment behaviour, so a customer
with no history has no score — they are not treated as reliable.

## The decision rules

**Chase ranking** is cash at risk × likelihood of recovering it. Each overdue
balance is haircut by age (98% / 92% / 80% / 55% for 1-30 / 31-60 / 61-90 / 90+)
and adjusted by risk grade (×1.05 / ×1.00 / ×0.90), capped at the balance owed.
An account that owes a fortune but has gone quiet ranks below one that owes less
and still pays, because the list exists to say what will be collected.

**Terms changes** are recommended only where a customer has payment history and
an open overdue balance, and only when they pay more than **15 days** late on
average. Terms above 30 days are cut to 30; accounts already on 30 days move to
cash on delivery.

**Cash unlock** separates the gross opportunity (cash sitting past its due date)
from the realistic recovery (the chase list's expected total). Adding the two
would count the same cash twice, so the reported total is the realistic figure.

## Reproducing

```
make test     # 50 tests, no third-party packages
make run      # regenerates data/ledger.json, outputs/*, and the charts
```

`outputs/answer_key.json` carries the fingerprint and every headline figure;
`tests/test_answer_key.py` fails if the published key ever drifts from the code.
