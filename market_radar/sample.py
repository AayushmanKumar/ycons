"""Builds the dashboard view-model from the saved sample (data/raw/sample_market.json).

UI-phase only: the live pipeline will produce the same shape from the API.
"""
import json
from datetime import date
from pathlib import Path

from . import pings, score

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "raw" / "sample_market.json"

SELF = "rippling.com"  # the company whose point of view the dashboard takes

# Hypothetical clients of Rippling (fast-growing tech companies that buy HR software).
CLIENTS = {"datadog": "Datadog", "canva": "Canva", "stripe": "Stripe"}

# Employer-of-record platforms count client staff in their headcount.
EOR_DOMAINS = {"deel.com", "remote.com", "oysterhr.com"}

SMALL_SIZES = {"1-10", "2-10", "11-50", "51-200"}

# Candidates rejected in earlier verification runs (kept so the UI can show why).
EARLIER_DROPS = {
    "self": [
        ("paycor.com", "Acquired by Paychex (2025), so it's no longer a separate competitor"),
        ("dudewipes.com", "From the look-alike-name list, which we ignore"),
    ],
    "datadog": [
        ("site24x7.com", "Product line of Zoho/ManageEngine (24 staff listed)"),
        ("manageengine.com", "Part of Zoho; its jobs are posted under Zoho"),
    ],
}

def complete_months(series, asof):
    """Keep monthly points whose month has fully ended before `asof` (a date)."""
    cutoff = f"{asof.year:04d}-{asof.month:02d}"
    return [(m, v) for m, v in series if m < cutoff and v is not None]


def _pct(new, old):
    if new is None or not old:
        return None
    return (new / old - 1) * 100


def _months_between(iso_date, today):
    if not iso_date:
        return None
    y, m, _ = (int(x) for x in iso_date[:10].split("-"))
    return (today.year - y) * 12 + today.month - m


def company_metrics(c, asof, live):
    """Measures for one company using only data that existed on `asof`.

    `live` is True when asof is on/after the real fetch date: only then do the
    snapshot-only fields (search, ads, traffic sources) exist.
    """
    t = c.get("traffic") or {}
    s = (c.get("seo") or {}) if live else {}
    traffic = complete_months(t.get("series", []), asof)
    series = [v for _, v in traffic]
    followers = [v for _, v in complete_months((c.get("followers") or {}).get("series", []), asof)]
    headcount = [v for _, v in complete_months((c.get("headcount") or {}).get("series", []), asof)]
    posts = complete_months(c.get("postings", []), asof)
    flags = []

    visitors = series[-1] if series else None
    kw_total = s.get("total_organic_results")
    seo_ok = live and not (kw_total is not None and kw_total < 5000 and (visitors or 0) > 1_000_000)
    if live and not seo_ok:
        flags.append(("seo_unreliable", "Search data looks broken for this brand, so search and ad measures are ignored"))
    if len(series) < 13:
        flags.append(("short_history", f"Only {len(series)} months of traffic history"))
    if c["domain"] in EOR_DOMAINS:
        flags.append(("eor_headcount", "Headcount includes staff it employs for clients, so headcount isn't used"))

    last3 = sum(v for _, v in posts[-3:])
    prev3 = sum(v for _, v in posts[-6:-3])
    if len(posts) >= 6 and prev3 < 10:
        flags.append(("few_postings", "Too few job postings to read a hiring trend"))

    net = None
    if seo_ok and kw_total:
        net = ((s.get("gained_ranked_seo_keywords") or 0) + (s.get("newly_ranked_seo_keywords") or 0)
               - (s.get("lost_ranked_seo_keywords") or 0)) / kw_total * 100

    raise_date = (c.get("funding") or {}).get("last_date")
    if raise_date and raise_date > asof.isoformat():
        raise_date = None  # the raise hadn't happened yet on this date

    return {
        "id": c["id"],
        "name": c["name"].replace("®", ""),
        "domain": c["domain"],
        "size": c.get("size"),
        "visitors": visitors,
        "visitor_series": traffic,
        "visitors_12m": _pct(series[-1], series[-13]) if len(series) >= 13 else None,
        "visitors_3m": _pct(series[-1], series[-4]) if len(series) >= 4 else None,
        "search_pct": t.get("search_pct") if live else None,
        "direct_pct": t.get("direct_pct") if live else None,
        "paid_pct": t.get("paid_pct") if live else None,
        "kw_net_pct": net,
        "keywords": kw_total if seo_ok else None,
        "ads_budget": s.get("monthly_google_ads_budget") if seo_ok else None,
        "postings_last3": last3,
        "postings_prev3": prev3,
        "postings_change": _pct(last3, prev3) if len(posts) >= 6 and prev3 >= 10 else None,
        "postings_series": posts,
        "followers_yoy": _pct(followers[-1], followers[-13]) if len(followers) >= 13 else None,
        "headcount": headcount[-1] if headcount else None,
        "headcount_yoy": _pct(headcount[-1], headcount[-13]) if len(headcount) >= 13 else None,
        "last_raise": raise_date,
        "last_round": (c.get("funding") or {}).get("last_round") if raise_date else None,
        "months_since_raise": _months_between(raise_date, asof),
        "flags": flags,
    }


def load():
    return json.loads(SAMPLE.read_text())


def build(asof=None, raw=None):
    raw = raw or load()
    fetched = raw["fetched_at"][:10]
    asof = asof or date.fromisoformat(fetched)
    live = asof >= date.fromisoformat(fetched)
    companies = raw["companies"]

    markets = []
    for g in raw["groups"]:
        self_paid = set(companies.get(g["self"], {}).get("paid_seo", []))
        rows, log = [], []
        for dom in g["domains"]:
            c = companies.get(dom)
            if not c:
                continue
            if dom != g["self"] and c.get("size") in SMALL_SIZES:
                log.append({"domain": dom, "kept": False,
                            "reason": f"Too small to compare ({c['size']} staff); likely a product line"})
                continue
            rows.append(company_metrics(c, asof, live))
            if dom != g["self"]:
                src = "Bids on the same Google ads" if dom in self_paid else "Ranks for the same searches"
                log.append({"domain": dom, "kept": True, "reason": src})
        for dom, why in EARLIER_DROPS.get(g["key"], []):
            log.append({"domain": dom, "kept": False, "reason": why})

        total_search = sum((r["visitors"] or 0) * (r["search_pct"] or 0) / 100 for r in rows)
        for r in rows:
            sv = (r["visitors"] or 0) * (r["search_pct"] or 0) / 100
            r["share_of_search"] = sv / total_search * 100 if total_search else None
            r["is_self"] = r["domain"] == g["self"]

        score.score_market(rows)
        role = "you" if g["key"] == "self" else "client"
        market = {
            "key": g["key"],
            "role": role,
            "self_domain": g["self"],
            "self_name": next(r["name"] for r in rows if r["is_self"]),
            "rows": rows,
            "discovery": log,
        }
        market["pings"] = pings.for_market(market, asof.isoformat())
        markets.append(market)

    return {"fetched_at": fetched, "asof": asof, "live": live, "self_domain": SELF, "markets": markets}
