"""Market Radar web app (UI phase: runs on the saved sample with a demo clock)."""
from datetime import date, timedelta
from functools import lru_cache
from statistics import median

from flask import Flask, flash, redirect, render_template, request, url_for

from . import charts, sample, score

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = "dev-only"  # flash messages only; no user data

@app.template_filter("pct")
def fmt_pct(v, digits=0):
    return "–" if v is None else f"{v:+.{digits}f}%"


@app.template_filter("money")
def fmt_money(v):
    return "–" if v is None else "$" + charts.compact(v)


@app.template_filter("num")
def fmt_num(v):
    return charts.compact(v)


@app.template_filter("day")
def fmt_day(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%a %-d %b %Y")


@app.template_filter("monthyear")
def fmt_monthyear(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%b %Y")


@app.template_filter("short")
def fmt_short(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%-d %b")


DEMO_START = date(2026, 7, 6)  # a Monday; the story unfolds Aug -> Nov
WEEKDAY_CHECK = 0  # weekly check runs on Mondays


@lru_cache(maxsize=1)
def raw():
    return sample.load()


@lru_cache(maxsize=256)
def build(asof):
    return sample.build(asof, raw())


def live_date():
    return date.fromisoformat(raw()["fetched_at"][:10])


def ping_history(asof):
    """Replay weekly checks from DEMO_START to asof; remember when each ping first appeared."""
    first_seen, d = {}, min(DEMO_START, asof)
    checks = []
    while d <= asof:
        checks.append(d)
        d += timedelta(days=7)
    if checks[-1] != asof:
        checks.append(asof)
    for d in checks:
        for m in build(d)["markets"]:
            for p in m["pings"]:
                first_seen.setdefault((p["domain"], p["market"], p["kind"]), d)
    return first_seen


def kpis(market):
    me = next(r for r in market["rows"] if r["is_self"])
    rivals = [r for r in market["rows"] if not r["is_self"]]
    med = lambda k: median([r[k] for r in rivals if r.get(k) is not None] or [0])
    total = sum(r["visitors"] or 0 for r in market["rows"]) or 1
    ranked = sorted(market["rows"], key=lambda r: -(r["visitors"] or 0))
    agree = [v for v in me["families"].values() if v is not None]
    return {
        "me": me,
        "share": (me["visitors"] or 0) / total * 100,
        "share_rank": ranked.index(me) + 1,
        "n": len(market["rows"]),
        "visitors_12m_vs": (me["visitors_12m"] or 0) - med("visitors_12m"),
        "ads_median": med("ads_budget") if me.get("ads_budget") is not None else None,
        "families_scored": len(agree),
        "need": score.needed_agreement(len(agree)),
    }


@app.route("/")
def dashboard():
    try:
        asof = date.fromisoformat(request.args.get("asof", ""))
    except ValueError:
        asof = DEMO_START
    asof = min(asof, live_date())
    f = {
        "view": request.args.get("view", "you") if request.args.get("view") in ("you", "clients") else "you",
        "focus": request.args.get("focus", ""),
        "verdict": request.args.get("verdict", "all"),
        "kind": request.args.get("kind", "all"),
        "range": int(request.args.get("range", 12)) if request.args.get("range") in ("12", "24") else 12,
    }
    vm = build(asof)
    first_seen = ping_history(asof)
    week_ago = asof - timedelta(days=7)

    # Pings feed is global (both tracks); only the ping-type filter applies.
    feed = []
    for m in vm["markets"]:
        for p in m["pings"]:
            seen = first_seen.get((p["domain"], p["market"], p["kind"]), asof)
            if f["kind"] in ("all", p["kind"]):
                feed.append({**p, "first_seen": seen, "is_new": seen > week_ago})
    feed.sort(key=lambda p: (not p["is_new"], {"threat": 0, "opportunity": 1, "watch": 2}[p["kind"]], p["title"]))

    you = next(m for m in vm["markets"] if m["role"] == "you")
    client_markets = [m for m in vm["markets"] if m["role"] == "client"]
    accounts = [account_summary(m, feed, f["range"]) for m in client_markets]
    if f["focus"] not in {a["key"] for a in accounts}:
        # Default to the most urgent account: Protect, then Upsell, then most new pings.
        order = {"Protect": 0, "Upsell": 1, "Steady": 2}
        f["focus"] = min(accounts, key=lambda a: (order[a["call"][0]], -a["new"]))["key"] if accounts else ""

    focus_market = you if f["view"] == "you" else next((m for m in client_markets if m["key"] == f["focus"]), None)
    panel = market_panel(focus_market, f) if focus_market else None

    next_check = asof + timedelta(days=(WEEKDAY_CHECK - asof.weekday()) % 7 or 7)
    return render_template(
        "dashboard.html", vm=vm, f=f, asof=asof, live=live_date(), demo_start=DEMO_START,
        feed=feed, new_count=sum(p["is_new"] for p in feed), panel=panel, accounts=accounts, k=kpis(you),
        you=you, client_new=sum(a["new"] for a in accounts),
        next_check=next_check, charts=charts, labels=score.FAMILY_LABELS,
        prev_week=max(asof - timedelta(days=7), DEMO_START), next_week=min(asof + timedelta(days=7), live_date()),
        next_month=min(asof + timedelta(days=28), live_date()),
    )


def account_call(verdict):
    if verdict == "rising":
        return ("Upsell", "good")
    if verdict == "falling":
        return ("Protect", "critical")
    return ("Steady", "neutral")


def market_panel(m, f):
    rows = [r for r in m["rows"] if f["verdict"] == "all" or r["verdict"] == f["verdict"] or r["is_self"]]
    line_svg, line_table = charts.line_index(rows, f["range"])
    me = next(r for r in m["rows"] if r["is_self"])
    rivals = [r for r in m["rows"] if not r["is_self"]]
    counts = {v: sum(r["verdict"] == v for r in rivals) for v in ("rising", "mixed", "falling")}
    moves = [(r["name"], r["pattern"], r["verdict"]) for r in rivals if r["pattern"] or r["verdict"] != "mixed"]
    kept = sum(d["kept"] for d in m["discovery"])
    return {"m": m, "me": me, "rows": rows, "line": line_svg, "line_table": line_table,
            "scatter": charts.scatter(rows), "bars": charts.share_bars(rows),
            "account": account_call(me["verdict"]) if m["role"] == "client" else None,
            "counts": counts, "moves": moves, "kept": kept, "dropped": len(m["discovery"]) - kept}


def account_summary(m, feed, n_months):
    """One row in the Client accounts table."""
    me = next(r for r in m["rows"] if r["is_self"])
    rivals = [r for r in m["rows"] if not r["is_self"]]
    rival_12m = [r["visitors_12m"] for r in rivals if r["visitors_12m"] is not None]
    pings = [p for p in feed if p["market"] == m["key"]]
    return {
        "key": m["key"], "name": me["name"], "domain": me["domain"], "me": me,
        "call": account_call(me["verdict"]),
        "n_rivals": len(rivals),
        "vs_rivals": (me["visitors_12m"] - median(rival_12m)) if me["visitors_12m"] is not None and rival_12m else None,
        "rising": sum(r["verdict"] == "rising" for r in rivals),
        "falling": sum(r["verdict"] == "falling" for r in rivals),
        "prospects": sum(p["title"].startswith("Prospect") for p in pings),
        "new": sum(p["is_new"] for p in pings),
        "spark": charts.versus_spark(me, rivals, n_months),
    }


@app.post("/fetch")
def fetch_latest():
    flash("Fetch latest will pull fresh data from Crustdata once the live pipeline is connected. "
          "This preview runs on the saved sample.")
    return redirect(url_for("dashboard", **request.args))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
