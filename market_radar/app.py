"""rivl web app. Live data from SQLite when markets are set up; otherwise the demo sample.

The demo clock works on both: every number is computed from data that existed
on the chosen date.
"""
from datetime import date, timedelta
from functools import lru_cache
from statistics import median

import click
from flask import Flask, flash, g, redirect, render_template, request, url_for

from . import charts, check, crustdata, sample, score, store, view

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = "dev-only"  # flash messages only; no user data

BRAND = "rivl"  # product name shown in the UI; change it here only


@app.context_processor
def inject_brand():
    return {"brand": BRAND}

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


def db():
    if "db" not in g:
        g.db = store.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@lru_cache(maxsize=1)
def sample_inputs():
    return sample.inputs(sample.load())


class Source:
    """Where the dashboard's data comes from for this request: 'live' or 'demo'."""

    def __init__(self, name):
        self.name = name
        if name == "live":
            groups, records, fetched, self_domain = check.inputs(db())
        else:
            (groups, records, fetched), self_domain = sample_inputs(), sample.SELF
        self.groups, self.records, self.self_domain = groups, records, self_domain
        self.live_date = date.fromisoformat(fetched)
        self.demo_start = min(DEMO_START, self.live_date)
        self._cache = {}

    def build(self, asof):
        if asof not in self._cache:
            self._cache[asof] = view.build(self.groups, self.records, self.live_date.isoformat(), asof,
                                           self.self_domain)
        return self._cache[asof]


def choose_source():
    wanted = request.args.get("src")
    has_live, has_demo = check.has_live_data(db()), sample.available()
    if wanted == "demo" and has_demo:
        return Source("demo")
    if wanted == "live" and has_live:
        return Source("live")
    if has_live:
        return Source("live")
    if has_demo:
        return Source("demo")
    return None


def ping_history(src, asof):
    """Replay weekly checks from the start of the clock to asof; remember when each ping first appeared."""
    first_seen, d = {}, min(src.demo_start, asof)
    checks = []
    while d <= asof:
        checks.append(d)
        d += timedelta(days=7)
    if checks[-1] != asof:
        checks.append(asof)
    for d in checks:
        for m in src.build(d)["markets"]:
            for p in m["pings"]:
                first_seen.setdefault((p["domain"], p["market"], p["kind"]), d)
    return first_seen


def stored_change_pings(asof):
    """Funding-round and new-competitor pings recorded by real checks (live data only)."""
    out = []
    for p in store.pings(db(), as_of=f"{asof.isoformat()}T23:59:59"):
        if ":funding:" in p["key"] or p["key"].endswith(":new_competitor"):
            out.append({**p, "first_seen": date.fromisoformat(p["first_seen"][:10])})
    return out


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
    src = choose_source()
    if src is None:
        return redirect(url_for("setup_page"))
    try:
        asof = date.fromisoformat(request.args.get("asof", ""))
    except ValueError:
        asof = src.demo_start if src.name == "demo" else src.live_date
    asof = max(min(asof, src.live_date), src.demo_start)
    f = {
        "src": src.name,
        "view": request.args.get("view", "you") if request.args.get("view") in ("you", "clients") else "you",
        "focus": request.args.get("focus", ""),
        "verdict": request.args.get("verdict", "all"),
        "kind": request.args.get("kind", "all"),
        "range": int(request.args.get("range", 12)) if request.args.get("range") in ("12", "24") else 12,
    }
    vm = src.build(asof)
    you = next((m for m in vm["markets"] if m["role"] == "you"), None)
    if you is None:
        flash("Your own market has no data yet. Run setup or Fetch latest.")
        return redirect(url_for("setup_page"))
    first_seen = ping_history(src, asof)
    week_ago = asof - timedelta(days=7)

    # Pings feed is global (both tracks); only the ping-type filter applies.
    feed = []
    for m in vm["markets"]:
        for p in m["pings"]:
            seen = first_seen.get((p["domain"], p["market"], p["kind"]), asof)
            feed.append({**p, "first_seen": seen, "is_new": seen > week_ago})
    if src.name == "live":
        feed += [{**p, "is_new": p["first_seen"] > week_ago} for p in stored_change_pings(asof)]
    feed = [p for p in feed if f["kind"] in ("all", p["kind"])]
    feed.sort(key=lambda p: (not p["is_new"], {"threat": 0, "opportunity": 1, "watch": 2}[p["kind"]], p["title"]))

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
        "dashboard.html", vm=vm, f=f, asof=asof, live=src.live_date, demo_start=src.demo_start,
        feed=feed, new_count=sum(p["is_new"] for p in feed), panel=panel, accounts=accounts, k=kpis(you),
        you=you, client_new=sum(a["new"] for a in accounts),
        has_live=check.has_live_data(db()), has_demo=sample.available(),
        next_check=next_check, charts=charts, labels=score.FAMILY_LABELS,
        prev_week=max(asof - timedelta(days=7), src.demo_start),
        next_week=min(asof + timedelta(days=7), src.live_date),
        next_month=min(asof + timedelta(days=28), src.live_date),
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


def describe(summary):
    parts = [f"Checked {summary['companies']} companies: {summary['refreshed']} had new data, "
             f"{summary['unchanged']} unchanged since the last check."]
    if summary["new_pings"]:
        parts.append(f"{len(summary['new_pings'])} new ping(s): " + "; ".join(summary["new_pings"][:4]) + ".")
    else:
        parts.append("No new pings.")
    if summary.get("new_competitors"):
        parts.append("New competitors: " + ", ".join(summary["new_competitors"]) + ".")
    if summary.get("missing"):
        parts.append("No data returned for: " + ", ".join(summary["missing"]) + ".")
    for e in summary.get("errors", []):
        parts.append(f"Skipped {e}")
    return " ".join(parts)


@app.post("/fetch")
def fetch_latest():
    args = {k: v for k, v in request.args.items() if k != "asof"}
    if not check.has_live_data(db()):
        flash("You're looking at the demo sample. Set up your own company to fetch live data.")
        return redirect(url_for("setup_page"))
    try:
        flash(describe(check.run(db(), use_cache=False)))
    except crustdata.CrustdataError as e:
        flash(f"Couldn't fetch: {e.message}")
    return redirect(url_for("dashboard", **{**args, "src": "live"}))


DEMO_COMPANY = "rippling.com"
DEMO_CLIENTS = ["datadoghq.com", "canva.com", "stripe.com"]


@app.post("/setup/key")
def save_key():
    key = request.form.get("api_key", "").strip()
    if not key:
        flash("Paste your Crustdata API key.")
        return redirect(url_for("setup_page"))
    try:
        balance = crustdata.check_key(key)
    except crustdata.CrustdataError as e:
        flash(e.message)
        return redirect(url_for("setup_page"))
    crustdata.save_api_key(key)
    flash(f"Connected to Crustdata. Balance: {balance:,.0f} credits." if balance is not None else "Connected to Crustdata.")
    return redirect(url_for("setup_page"))


@app.route("/setup", methods=["GET", "POST"])
def setup_page():
    if request.method == "POST":
        if not crustdata.has_api_key():
            flash("Connect your Crustdata API key first.")
            return redirect(url_for("setup_page"))
        if request.form.get("action") == "demo":
            try:
                flash(describe(check.setup(db(), DEMO_COMPANY, DEMO_CLIENTS)))
                return redirect(url_for("dashboard", src="live"))
            except (check.competitors.DiscoveryError, crustdata.CrustdataError, ValueError) as e:
                flash(f"Setup failed: {e}")
                return redirect(url_for("setup_page"))
        domain = request.form.get("domain", "").strip()
        text = request.form.get("clients", "")
        upload = request.files.get("clients_csv")
        if upload and upload.filename:
            text += "\n" + upload.read().decode("utf-8", errors="replace")
        clients = [c.strip() for line in text.splitlines() for c in line.split(",") if c.strip()]
        clients = [c for c in clients if "." in c]  # skip CSV headers and stray words
        if not domain:
            flash("Enter your company's website domain.")
            return redirect(url_for("setup_page"))
        try:
            summary = check.setup(db(), domain, clients)
            flash(describe(summary))
            return redirect(url_for("dashboard", src="live"))
        except (check.competitors.DiscoveryError, crustdata.CrustdataError, ValueError) as e:
            flash(f"Setup failed: {e}")
            return redirect(url_for("setup_page"))
    current = []
    for m in store.markets(db()):
        me = next((x for x in store.members(db(), m["key"]) if x["is_self"]), None)
        if me:
            current.append({"role": m["role"], "domain": me["domain"], "name": me["name"],
                            "n": len(store.members(db(), m["key"], kept_only=True)) - 1})
    has_key = crustdata.has_api_key()
    key_hint = crustdata.api_key()[-4:] if has_key else None
    return render_template("setup.html", current=current, has_demo=sample.available(),
                           last_fetch=store.last_fetch(db()), has_key=has_key, key_hint=key_hint,
                           balance=crustdata.credits() if has_key else None,
                           demo_company=DEMO_COMPANY, demo_clients=DEMO_CLIENTS)


# ---- command line: `flask --app market_radar.app check` (e.g. weekly from cron) ----

@app.cli.command("check")
def check_command():
    """Run the weekly check: fetch fresh data and record new pings."""
    with app.app_context():
        click.echo(describe(check.run(db(), use_cache=False)))


@app.cli.command("setup")
@click.argument("domain")
@click.option("--clients", default="", help="Comma-separated client domains")
def setup_command(domain, clients):
    """Build your market and your clients' markets, then run a first check."""
    with app.app_context():
        click.echo(describe(check.setup(db(), domain, [c for c in clients.split(",") if c.strip()])))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
