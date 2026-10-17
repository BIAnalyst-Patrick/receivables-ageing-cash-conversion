# Action register

Reporting date **2026-06-30**. All figures synthetic (see the limits section of
the README). Amounts in KES.

## 1. Collection actions, in order

`outputs/tables/chase_list.csv` holds all 52 accounts. The top five carry
**62.3%** of the overdue balance and **61.0%** of the recoverable cash.

| # | Account | Overdue | Expected recovery | Likelihood | Oldest | Owner | Action | Review |
|--:|---|--:|--:|--:|--:|---|---|---|
| 1 | Juja Fresh Mart | 2,215,162 | 1,398,527 | 63% | 434 days | Credit Controller | Formal demand, stop supply, written plan | 14 days |
| 2 | Baraka Traders | 1,725,877 | 1,014,867 | 59% | 466 days | Credit Controller | Formal demand, stop supply, written plan | 14 days |
| 3 | Tumaini Stores | 1,134,558 | 717,876 | 63% | 408 days | Credit Controller | Formal demand, stop supply, written plan | 14 days |
| 4 | Zawadi Wholesale | 1,096,210 | 602,915 | 55% | 422 days | Credit Controller | Formal demand, stop supply, written plan | 14 days |
| 5 | Nakuru Grocers | 546,292 | 372,220 | 68% | 415 days | Credit Controller | Formal demand, stop supply, written plan | 14 days |

Three of the five pay reasonably when they pay at all (weighted days late 8-31),
so the money is collectible; the failure is that nothing was escalated for over
a year.

## 2. Terms to change

17 accounts qualify. Nine move from 45 or 60 days to 30; eight move to cash on
delivery. `outputs/tables/terms_changes.csv` holds the full list with the
weighted days-late that triggered each.

| Account | Now | Recommended | Days late | Overdue |
|---|---|---:|---:|---:|
| Giza Supplies | 30 | Cash on delivery | 39.9 | 38,660 |
| Nuru Traders | 30 | Cash on delivery | 37.7 | 28,853 |
| Chachu Supplies | 30 | Cash on delivery | 35.4 | 54,264 |
| Rehema Distributors | 30 | Cash on delivery | 32.9 | 5,875 |
| Juja Fresh Mart | 60 | 30 | 31.0 | 2,215,162 |
| Faraja Stores | 45 | 30 | 26.3 | 219,388 |
| Tumaini Stores | 45 | 30 | 24.6 | 1,134,558 |
| Baraka Traders | 60 | 30 | 23.3 | 1,725,877 |

Owner: Sales Director, with the Credit Controller. Review: at the next credit
committee, within 30 days.

The terms edit is the smaller lever. Shortening every 60-day account to 30 days
moves at most 30 days of DSO; the gap between DSO and best-possible DSO is
**83.9 days**. The money is in collection, not in the paperwork.

## 3. What the cash is worth

| Figure | Value |
|---|--:|
| Cash sitting past its due date | 10,787,346 |
| Realistically recoverable now | 6,731,146 |
| Recoverable from the top five accounts | 4,106,405 |
| Provision currently implied by the age profile | 3,776,088 |

Owner: CFO. Review: monthly, against the collection effectiveness index, which
currently sits at **49.1%** — the business is collecting less than half of what
was collectible in the period.

## 4. What to fix structurally

**Fact.** The 90+ bucket holds 8,056,070 against 304,293 in 31-60 and 265,369 in
61-90. **Fact.** All five largest overdue accounts received four to six invoices
in the last 90 days, the most recent in June 2026 — they are still being
supplied while more than a year of invoices sits unpaid.

**Hypothesis, consistent with that shape rather than proven by it.** Accounts
here do not drift into delinquency; they stop paying and keep ordering. If that
is right, the 31-90 band stays thin because balances jump from current to 90+
without lingering in between. Two implications follow, and both are cheap to
test:

1. **A stop-supply trigger.** Any account 45 days past due stops receiving stock
   automatically. Four of the top five are 400+ days overdue and still being
   invoiced, so this would have capped the exposure roughly a year ago.
2. **A weekly ageing review.** A monthly cycle cannot see a balance cross from
   current to 90+, because it never appears in the middle buckets in volume.
