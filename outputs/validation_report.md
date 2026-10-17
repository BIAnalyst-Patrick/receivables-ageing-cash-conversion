# Validation report

Reporting date: **2026-06-30**. Data fingerprint: `b486c28acb5e74af0f5d763611651c6ad35c2c579b32d9ea3e7428ac6edb1a8a`.

**15/15 checks passed.**

| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | Ageing buckets reconcile to total receivables | PASS | `sum(buckets)=16828686.74 total_ar=16828686.74` |
| 2 | Receivables are positive | PASS | `total_ar=16828686.74` |
| 3 | Overdue is a subset of receivables | PASS | `overdue=10787346.18 of 16828686.74` |
| 4 | DSO is at least best-possible DSO | PASS | `dso=130.87 bpdso=46.98` |
| 5 | Cash conversion cycle equals DSO + DIO - DPO | PASS | `ccc=140.74 components=130.87+47.87-38.00` |
| 6 | Collection effectiveness index is a percentage | PASS | `cei=49.12` |
| 7 | Provision does not exceed receivables | PASS | `provision=3776087.55 of 16828686.74` |
| 8 | Chase list is ranked by expected recovery | PASS | `52 accounts ranked` |
| 9 | No expected recovery exceeds the balance owed | PASS | `max recovery=1398526.78` |
| 10 | Realistic recovery never exceeds the gross overdue balance | PASS | `recoverable=6731146.40 tied_up=10787346.18` |
| 11 | Every invoice's due date follows its customer's terms | PASS | `964 invoices checked` |
| 12 | No invoice is dated after the reporting date | PASS | `as_of=2026-06-30` |
| 13 | Days-to-late is non-negative for every customer | PASS | `60 customers with payment history` |
| 14 | Regenerating from the same seed reproduces the ledger exactly | PASS | `fingerprint=b486c28acb5e74af...` |
| 15 | Chase list covers every customer with an overdue balance | PASS | `52 accounts` |

Every check is computed by `recv/pipeline.py:validate` and can be re-run with `make run`.
They compare derived figures against independent identities (buckets against total
receivables, CCC against its own components, the chase list against its sort order)
rather than against numbers copied into this file.
