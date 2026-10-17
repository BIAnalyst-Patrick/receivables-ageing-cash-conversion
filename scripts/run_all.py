#!/usr/bin/env python3
"""Run the full analysis and redraw the charts.

    python3 scripts/run_all.py

Requires nothing beyond the standard library for the analysis. Chart rendering
needs Pillow; if it is missing the analysis still completes and the existing
PNGs are left untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recv import pipeline  # noqa: E402


def main() -> int:
    out = pipeline.run()
    result, checks = out["result"], out["checks"]
    passed = sum(1 for _, ok, _ in checks if ok)

    print(f"Reporting date        {result['as_of']}")
    print(f"Fingerprint           {result['fingerprint'][:24]}...")
    print(f"Receivables           {result['total_ar']:,.2f}")
    print(f"Overdue               {result['overdue_ar']:,.2f}")
    print(f"DSO                   {result['dso']} days (best possible {result['best_possible_dso']})")
    print(f"Cash conversion cycle {result['ccc']} days "
          f"(DIO {result['dio']}, DPO {result['dpo']})")
    print(f"Collection index      {result['cei']}%")
    print(f"Recoverable now       {result['unlock']['recoverable_now']:,.2f}")
    print(f"Validation checks     {passed}/{len(checks)} passed")
    for name, ok, detail in checks:
        if not ok:
            print(f"  FAIL  {name}: {detail}")

    try:
        from recv import charts
        for path in charts.render_all(result, ROOT / "outputs" / "charts"):
            print(f"chart                 {path.relative_to(ROOT)}")
    except ImportError:
        print("chart                 skipped (Pillow not installed); committed PNGs retained")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
