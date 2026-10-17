"""Report charts, rendered to repo-local PNG files.

Charts are illustrative; every number they show comes from
``outputs/answer_key.json`` and is asserted by ``tests/``. They are drawn with
Pillow so the output is a plain file in the repository, never a hosted embed.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1240, 700
BG = (255, 255, 255)
INK = (23, 32, 42)
MUTED = (110, 124, 140)
GRID = (226, 232, 240)
ACCENT = (11, 94, 132)
ACCENT_SOFT = (150, 196, 214)
WARN = (176, 58, 46)

FONT_SIZES = {}


def _font(size: int):
    if size not in FONT_SIZES:
        try:
            FONT_SIZES[size] = ImageFont.load_default(size=size)
        except TypeError:  # older Pillow
            FONT_SIZES[size] = ImageFont.load_default()
    return FONT_SIZES[size]


def _canvas(title: str, subtitle: str):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 46), title, font=_font(30), fill=INK)
    d.text((70, 88), subtitle, font=_font(16), fill=MUTED)
    return img, d


def _money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:,.0f}K"
    return f"{value:,.0f}"


def _save(img, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    return path


def ageing_chart(result: dict, path: Path) -> Path:
    buckets = result["buckets"]
    total = float(result["total_ar"]) or 1.0
    labels = ["Current", "1-30", "31-60", "61-90", "90+"]
    values = [float(buckets[k]) for k in ("current", "d1_30", "d31_60", "d61_90", "d90_plus")]
    img, d = _canvas(
        "Receivables by age",
        f"Total receivables {_money(total)} at {result['as_of']}  |  synthetic data",
    )
    left, right, top, bottom = 110, 90, 170, 120
    plot_w, plot_h = WIDTH - left - right, HEIGHT - top - bottom
    peak = max(values) * 1.18

    for i in range(5):
        y = top + plot_h * i / 4
        d.line((left, y, WIDTH - right, y), fill=GRID, width=1)
        d.text((left - 12, y - 7), _money(peak * (4 - i) / 4), font=_font(13), fill=MUTED, anchor="ra")

    slot = plot_w / len(values)
    bar_w = slot * 0.52
    for i, (label, value) in enumerate(zip(labels, values)):
        cx = left + slot * (i + 0.5)
        h = plot_h * value / peak
        x0, y0 = cx - bar_w / 2, top + plot_h - h
        colour = WARN if label == "90+" else ACCENT
        d.rectangle((x0, y0, x0 + bar_w, top + plot_h), fill=colour)
        d.text((cx, y0 - 24), _money(value), font=_font(16), fill=INK, anchor="ma")
        d.text((cx, y0 - 6), f"{value / total * 100:.1f}%", font=_font(13), fill=MUTED, anchor="ma")
        d.text((cx, top + plot_h + 18), label, font=_font(15), fill=INK, anchor="ma")

    d.text((left, HEIGHT - 62),
           "Days past due. The 90+ column is the collection problem, not the ageing curve.",
           font=_font(14), fill=MUTED)
    return _save(img, path)


def chase_chart(result: dict, path: Path, top_n: int = 10) -> Path:
    items = result["chase"][:top_n]
    img, d = _canvas(
        "Where to chase first",
        "Overdue balance versus realistically recoverable cash, ranked by expected recovery",
    )
    left, right, top, bottom = 330, 120, 150, 90
    plot_w = WIDTH - left - right
    row_h = (HEIGHT - top - bottom) / max(len(items), 1)
    peak = max(float(i.overdue_balance) for i in items) * 1.05

    for idx, item in enumerate(items):
        y = top + row_h * idx
        name = item.customer_name
        d.text((left - 18, y + row_h * 0.16), name, font=_font(14), fill=INK, anchor="ra")
        overdue = float(item.overdue_balance)
        recoverable = float(item.expected_recovery)
        w_all = plot_w * overdue / peak
        w_rec = plot_w * recoverable / peak
        bar_h = row_h * 0.30
        d.rectangle((left, y + row_h * 0.14, left + w_all, y + row_h * 0.14 + bar_h), fill=GRID)
        d.rectangle((left, y + row_h * 0.14, left + w_rec, y + row_h * 0.14 + bar_h), fill=ACCENT)
        d.text((left + w_all + 12, y + row_h * 0.10), _money(recoverable),
               font=_font(13), fill=INK)

    d.text((left, HEIGHT - 58), "grey = balance owed   ", font=_font(13), fill=MUTED)
    d.text((left + 150, HEIGHT - 58), "blue = expected cash recovery", font=_font(13), fill=ACCENT)
    return _save(img, path)


def ccc_chart(result: dict, path: Path) -> Path:
    dso = float(result["dso"])
    dio = float(result["dio"])
    dpo = float(result["dpo"])
    ccc = float(result["ccc"])
    img, d = _canvas(
        "Cash conversion cycle",
        "Days. Cash is out of the business for the length of the cycle.",
    )
    left, right, top, bottom = 110, 110, 180, 130
    plot_w, plot_h = WIDTH - left - right, HEIGHT - top - bottom
    steps = [
        ("DSO", dso, ACCENT),
        ("+ DIO", dio, ACCENT_SOFT),
        ("- DPO", -dpo, ACCENT_SOFT),
        ("= CCC", ccc, WARN),
    ]
    running = 0.0
    peak = max(dso, ccc) * 1.25
    slot = plot_w / len(steps)
    bar_w = slot * 0.46

    for i, (label, value, colour) in enumerate(steps):
        cx = left + slot * (i + 0.5)
        x0 = cx - bar_w / 2
        if label == "= CCC":
            top_y = top + plot_h - plot_h * value / peak
            d.rectangle((x0, top_y, x0 + bar_w, top + plot_h), fill=colour)
            d.text((cx, top_y - 26), f"{value:,.1f}", font=_font(22), fill=INK, anchor="ma")
            running = value
        else:
            start = top + plot_h - plot_h * running / peak
            end = top + plot_h - plot_h * (running + value) / peak
            d.rectangle((x0, min(start, end), x0 + bar_w, max(start, end)), fill=colour)
            d.text((cx, min(start, end) - 26), f"{value:+,.1f}", font=_font(18), fill=INK, anchor="ma")
            running += value
        d.text((cx, top + plot_h + 18), label, font=_font(16), fill=INK, anchor="ma")

    d.text((left, HEIGHT - 66),
           f"DSO {dso:,.1f} + DIO {dio:,.1f} - DPO {dpo:,.1f} = {ccc:,.1f} days",
           font=_font(15), fill=MUTED)
    return _save(img, path)


def render_all(result: dict, out_dir: Path) -> list[Path]:
    return [
        ageing_chart(result, out_dir / "01_ageing_by_bucket.png"),
        chase_chart(result, out_dir / "02_chase_priority.png"),
        ccc_chart(result, out_dir / "03_cash_conversion_cycle.png"),
    ]
