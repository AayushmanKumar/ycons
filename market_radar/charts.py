"""Server-rendered SVG charts. Plain strings, no JS needed to draw.

Form choices (dataviz method): emphasis = one accent series, everyone else gray;
one y-axis only; thin marks; hairline grid; selective direct labels; every chart
has a table twin in the template.
"""
import json
import math

from markupsafe import Markup, escape

ACCENT = "var(--accent)"
MUTED_LINE = "var(--deemph)"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def month_label(ym, with_year=False):
    y, m = ym.split("-")
    label = MONTHS[int(m) - 1]
    return f"{label} {y[2:]}" if with_year else label


def compact(v):
    if v is None:
        return "–"
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    if a >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:.0f}"


def _nice_ticks(lo, hi, target=4):
    span = hi - lo or 1
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + step * 0.001:
        ticks.append(round(t, 6))
        t += step
    if ticks[-1] < hi:
        ticks.append(ticks[-1] + step)
    return ticks


def line_index(rows, n_months, width=640, height=230):
    """Monthly visitors indexed to 100 at the window start. Self = accent, rest gray."""
    months = sorted({m for r in rows for m, _ in r["visitor_series"]})[-n_months:]
    if len(months) < 2:
        return Markup('<p class="empty">Not enough traffic history for this date.</p>'), []
    series = []
    for r in rows:
        vals = dict(r["visitor_series"])
        base = next((vals[m] for m in months if vals.get(m)), None)
        if not base:
            continue
        idx = [round(vals[m] / base * 100, 1) if vals.get(m) else None for m in months]
        series.append({"name": r["name"], "self": r["is_self"], "idx": idx,
                       "raw": [vals.get(m) for m in months]})
    allv = [v for s in series for v in s["idx"] if v is not None]
    ticks = _nice_ticks(min(allv), max(allv))
    lo, hi = ticks[0], ticks[-1]
    L, R, T, B = 40, 96, 10, 26
    pw, ph = width - L - R, height - T - B
    x = lambda i: L + pw * i / (len(months) - 1)
    y = lambda v: T + ph * (1 - (v - lo) / (hi - lo))

    out = [f'<svg class="chart line" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Monthly website visitors, indexed to 100" '
           f'data-x0="{L}" data-dx="{pw / (len(months) - 1):.3f}" data-top="{T}" data-bottom="{T + ph}" '
           f'data-series=\'{escape(json.dumps({"months": [month_label(m, True) for m in months], "series": series}))}\'>']
    for t in ticks:
        cls = "base" if t == 100 else "grid"
        out.append(f'<line class="{cls}" x1="{L}" x2="{L + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    step = max(1, len(months) // 6)
    for i, m in enumerate(months):
        if i % step == 0 or i == len(months) - 1:
            out.append(f'<text class="tick" x="{x(i):.1f}" y="{height - 6}" text-anchor="middle">'
                       f'{month_label(m, m.endswith("-01") or i == 0)}</text>')
    for s in sorted(series, key=lambda s: s["self"]):
        pts = [(x(i), y(v)) for i, v in enumerate(s["idx"]) if v is not None]
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        color = ACCENT if s["self"] else MUTED_LINE
        out.append(f'<path class="series{" self" if s["self"] else ""}" data-name="{escape(s["name"])}" d="{d}" stroke="{color}"/>')
        if s["self"] and pts:
            px, py = pts[-1]
            out.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{color}"/>')
            out.append(f'<text class="end-label" x="{px + 8:.1f}" y="{py + 4:.1f}">'
                       f'{escape(s["name"])} {s["idx"][-1] or 0:g}</text>')
    out.append(f'<line class="crosshair" x1="0" x2="0" y1="{T}" y2="{T + ph}" visibility="hidden"/>')
    out.append(f'<rect class="hit" x="{L}" y="{T}" width="{pw}" height="{ph}" fill="transparent"/>')
    out.append("</svg>")
    table = [{"name": s["name"], "start": s["raw"][0], "end": s["raw"][-1], "index": s["idx"][-1]} for s in series]
    return Markup("".join(out)), table


def scatter(rows, width=420, height=230):
    """Hiring change (x) vs visitors 12-month change (y). Quadrants tell the story."""
    pts = [r for r in rows if r.get("postings_change") is not None and r.get("visitors_12m") is not None]
    if len(pts) < 2:
        return Markup('<p class="empty">Not enough hiring and traffic data to plot.</p>')
    clamp = lambda v, a, b: max(a, min(b, v))
    xs = [clamp(r["postings_change"], -100, 300) for r in pts]
    ys = [r["visitors_12m"] for r in pts]
    xt, yt = _nice_ticks(min(xs + [0]), max(xs + [0]), 4), _nice_ticks(min(ys + [0]), max(ys + [0]), 4)
    L, R, T, B = 40, 16, 10, 30
    pw, ph = width - L - R, height - T - B
    X = lambda v: L + pw * (v - xt[0]) / (xt[-1] - xt[0])
    Y = lambda v: T + ph * (1 - (v - yt[0]) / (yt[-1] - yt[0]))
    out = [f'<svg class="chart scatter" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Hiring change against visitor change">']
    for t in yt:
        out.append(f'<line class="{"base" if t == 0 else "grid"}" x1="{L}" x2="{L + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 6}" y="{Y(t) + 4:.1f}" text-anchor="end">{t:+g}%</text>')
    for t in xt:
        out.append(f'<line class="{"base" if t == 0 else "grid"}" y1="{T}" y2="{T + ph}" x1="{X(t):.1f}" x2="{X(t):.1f}"/>')
        out.append(f'<text class="tick" x="{X(t):.1f}" y="{height - 14}" text-anchor="middle">{t:+g}%</text>')
    out.append(f'<text class="axis-title" x="{L + pw}" y="{height - 2}" text-anchor="end">Hiring, last 3 months vs previous →</text>')
    q = [("Growing and hiring", L + pw - 4, T + 12, "end"), ("Growing, lean", L + 4, T + 12, "start"),
         ("Hiring into a decline", L + pw - 4, T + ph - 6, "end"), ("Shrinking and cutting", L + 4, T + ph - 6, "start")]
    for label, qx, qy, anchor in q:
        out.append(f'<text class="quadrant" x="{qx:.1f}" y="{qy:.1f}" text-anchor="{anchor}">{label}</text>')
    for r, xv, yv in sorted(zip(pts, xs, ys), key=lambda t: t[0]["is_self"]):
        cx, cy = X(xv), Y(yv)
        tip = escape(json.dumps([r["name"], f'Visitors {yv:+.0f}% over 12 months',
                                 f'Hiring {r["postings_change"]:+.0f}% (3 months)']))
        color = ACCENT if r["is_self"] else MUTED_LINE
        out.append(f'<g class="pt" tabindex="0" data-tip=\'{tip}\'><circle class="hit" cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="transparent"/>'
                   f'<circle class="dot{" self" if r["is_self"] else ""}" cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}"/>'
                   f'<text class="pt-label" x="{cx + 8:.1f}" y="{cy + 4:.1f}">{escape(r["name"])}</text></g>')
    out.append("</svg>")
    return Markup("".join(out))


def share_bars(rows):
    """Ranked horizontal bars (HTML, so text stays full size): share of visitors."""
    total = sum(r["visitors"] or 0 for r in rows)
    if not total:
        return Markup('<p class="empty">No traffic data.</p>')
    ranked = sorted(rows, key=lambda r: -(r["visitors"] or 0))
    top = (ranked[0]["visitors"] or 0) / total * 100
    out = ['<ol class="hbars" aria-label="Share of visitors">']
    for r in ranked:
        share = (r["visitors"] or 0) / total * 100
        tip = escape(json.dumps([r["name"], f"{share:.1f}% of visitors", f'{compact(r["visitors"])} visitors/month']))
        out.append(f'<li tabindex="0" data-tip=\'{tip}\' class="{"self" if r["is_self"] else ""}">'
                   f'<span class="name">{escape(r["name"])}</span>'
                   f'<span class="track"><span class="bar" style="width:{max(share / top * 100, 1):.1f}%"></span></span>'
                   f'<span class="val">{share:.1f}%</span></li>')
    out.append("</ol>")
    return Markup("".join(out))


def versus_spark(me, rivals, n_months, width=150, height=36):
    """Client (accent) vs the median of its rivals (gray), both indexed to 100."""
    months = [m for m, _ in me["visitor_series"]][-n_months:]
    if len(months) < 2:
        return Markup("")

    def indexed(r):
        vals = dict(r["visitor_series"])
        base = next((vals[m] for m in months if vals.get(m)), None)
        return [vals[m] / base * 100 if base and vals.get(m) else None for m in months]

    mine = indexed(me)
    rival_idx = [indexed(r) for r in rivals]
    med = []
    for i in range(len(months)):
        col = sorted(v[i] for v in rival_idx if v[i] is not None)
        med.append(col[len(col) // 2] if col else None)
    allv = [v for v in mine + med if v is not None]
    lo, hi = min(allv), max(allv)
    span = hi - lo or 1

    def path(vals):
        pts = [(3 + (width - 8) * i / (len(months) - 1), 4 + (height - 8) * (1 - (v - lo) / span))
               for i, v in enumerate(vals) if v is not None]
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts), pts[-1] if pts else (0, 0)

    d_med, _ = path(med)
    d_me, (lx, ly) = path(mine)
    return Markup(f'<svg class="spark vs" viewBox="0 0 {width} {height}" role="img" '
                  f'aria-label="{escape(me["name"])} visitors vs rivals\' median">'
                  f'<path d="{d_med}" stroke="var(--deemph)"/>'
                  f'<path d="{d_me}" stroke="var(--accent)" stroke-width="2"/>'
                  f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="var(--accent)" stroke="var(--surface)" stroke-width="1.5"/></svg>')


def sparkline(series, is_self=False, width=96, height=24):
    vals = [v for _, v in series][-12:]
    if len(vals) < 2:
        return Markup("")
    lo, hi = min(vals), max(vals)
    span = hi - lo or 1
    pts = [(2 + (width - 6) * i / (len(vals) - 1), 3 + (height - 6) * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return Markup(f'<svg class="spark" viewBox="0 0 {width} {height}" aria-hidden="true">'
                  f'<path d="{d}" stroke="var(--deemph)"/>'
                  f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.5" fill="{ACCENT if is_self else "var(--ink-2)"}"/></svg>')
