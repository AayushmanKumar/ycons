"""Fetch companies from Crustdata and turn them into normalised records and measures.

A *record* is the stored form of one company (one snapshot). *Metrics* are the
measures computed from a record as of a given date, using only data that
existed on that date.
"""
import hashlib
import json
from datetime import date

from . import crustdata, resolve

# Fields fetched for every company (one enrich call, 2 credits per company).
COMPANY_FIELDS = ["basic_info", "headcount", "web_traffic", "seo", "followers", "funding", "competitors"]

# Employer-of-record platforms count client staff in their headcount.
EOR_DOMAINS = {"deel.com", "remote.com", "oysterhr.com"}

POSTING_MONTHS = 12


# ---- normalising ------------------------------------------------------------

def _monthly(ts, key):
    """[{date, <key>}] -> [[YYYY-MM, value]] (last value per month, last 24 months)."""
    out = {}
    for p in ts or []:
        if p.get(key) is not None and p.get("date"):
            out[str(p["date"])[:7]] = p[key]
    return [[m, v] for m, v in sorted(out.items())][-24:]


def record(data, domain, postings):
    """Normalise one enrich `company_data` into a record. `postings` = [[YYYY-MM, count]]."""
    info = data.get("basic_info") or {}
    dt = (data.get("web_traffic") or {}).get("domain_traffic") or {}
    # Only ever use traffic for the company's own domain (HubSpot's came back for gzconsulting.org).
    t = dt.get(domain) or dt.get(resolve.normalize_domain(info.get("primary_domain"))) or {}
    hc = data.get("headcount") or {}
    fol = data.get("followers") or {}
    fund = data.get("funding") or {}
    comp = data.get("competitors") or {}
    return {
        "id": data.get("crustdata_company_id"),
        "name": (info.get("name") or domain).replace("®", "").strip(),
        "domain": domain,
        "size": info.get("employee_count_range"),
        "industries": info.get("industries") or [],
        "traffic": {
            "monthly_visitors": t.get("monthly_visitors"),
            "qoq_pct": t.get("qoq_pct"),
            "search_pct": t.get("source_search_pct"),
            "direct_pct": t.get("source_direct_pct"),
            "paid_pct": t.get("source_paid_referral_pct"),
            "series": _monthly(t.get("monthly_visitors_timeseries"), "monthly_visitors"),
            "search_series": _monthly(t.get("source_search_pct_timeseries"), "traffic_source_search_pct"),
            "direct_series": _monthly(t.get("source_direct_pct_timeseries"), "traffic_source_direct_pct"),
            "paid_series": _monthly(t.get("source_paid_referral_pct_timeseries"), "traffic_source_paid_referral_pct"),
        } if t else None,
        "traffic_domains": sorted(dt),
        "seo": data.get("seo") or None,
        "headcount": {"total": hc.get("total"), "growth": hc.get("growth_percent"),
                      "series": _monthly(hc.get("timeseries"), "employee_count")},
        "followers": {"count": fol.get("count"), "yoy": fol.get("yoy_percent"),
                      "series": _monthly(fol.get("timeseries"), "follower_count")},
        "funding": {
            "total_usd": fund.get("total_investment_usd"),
            "last_round": fund.get("last_round_type"),
            "last_date": fund.get("last_fundraise_date"),
            "investors": (fund.get("investors") or [])[:4],
            # Noisy in Crustdata (a company "acquired by" itself; Square "by" Bridg, which it bought),
            # so view.py only uses it when the acquirer is another company in the same market.
            "acquired_by": [{"id": a.get("crustdata_company_id"), "name": a.get("name")}
                            for a in fund.get("acquired_by") or [] if isinstance(a, dict)],
            "acquisition_ids": [a.get("acquiree_company_id") for a in fund.get("acquisitions") or []
                                if isinstance(a, dict) and a.get("acquiree_company_id")],
        },
        "paid_seo": [d for d in (resolve.normalize_domain(x) for x in comp.get("paid_seo") or []) if d],
        "organic_seo": [d for d in (resolve.normalize_domain(x) for x in comp.get("organic_seo") or []) if d],
        "postings": postings,
    }


def fingerprint(rec, today):
    """Content hash of a record, ignoring the still-changing current month of postings.

    Crustdata's enrich response carries no 'last updated' date, so an identical
    fingerprint is how we know a company hasn't been refreshed.
    """
    current = f"{today.year:04d}-{today.month:02d}"
    stable = {**rec, "postings": [p for p in rec.get("postings", []) if p[0] < current]}
    stable.pop("snapshot_date", None)
    return hashlib.sha1(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def _month_starts(today, n):
    """First days of the last n months, oldest first, plus the current month."""
    y, m = today.year, today.month
    out = []
    for _ in range(n + 1):
        out.append(date(y, m, 1))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return sorted(out)


def fetch(companies, today=None, use_cache=True):
    """companies: [{id, domain}] -> {domain: record}. Costs 2 credits per company; postings are free."""
    today = today or date.today()
    ids = sorted({c["id"] for c in companies})
    by_id = {}
    for row in crustdata.enrich(ids, COMPANY_FIELDS, use_cache=use_cache):
        data = ((row.get("matches") or [{}])[0]).get("company_data") or {}
        if data.get("crustdata_company_id"):
            by_id[data["crustdata_company_id"]] = data

    starts = _month_starts(today, POSTING_MONTHS)
    counts = {}
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        counts[start.strftime("%Y-%m")] = crustdata.posting_counts(ids, start.isoformat(), end.isoformat(),
                                                                   use_cache=use_cache)
    out = {}
    for c in companies:
        data = by_id.get(c["id"])
        if data:
            postings = [[m, counts[m].get(c["id"], 0)] for m in sorted(counts)]
            out[c["domain"]] = record(data, c["domain"], postings)
    return out


# ---- measures ---------------------------------------------------------------

def complete_months(series, asof):
    """Keep monthly points whose month has fully ended before `asof` (a date)."""
    cutoff = f"{asof.year:04d}-{asof.month:02d}"
    return [(m, v) for m, v in series or [] if m < cutoff and v is not None]


def _pct(new, old):
    if new is None or not old:
        return None
    return (new / old - 1) * 100


def _months_between(iso_date, today):
    if not iso_date:
        return None
    y, m, _ = (int(x) for x in iso_date[:10].split("-"))
    return (today.year - y) * 12 + today.month - m


def _as_of(series, asof, fallback):
    """Latest complete-month value of a monthly series, or `fallback` if there's no history."""
    pts = complete_months(series, asof)
    return pts[-1][1] if pts else fallback


def company_metrics(c, asof):
    """Measures for one company using only data that existed on `asof`.

    Snapshot-only fields (search ranks, ad budget) exist only from the date the
    snapshot was taken (`c["snapshot_date"]`).
    """
    live = asof.isoformat() >= (c.get("snapshot_date") or "9999")
    t = c.get("traffic") or {}
    s = (c.get("seo") or {}) if live else {}
    traffic = complete_months(t.get("series"), asof)
    series = [v for _, v in traffic]
    followers = [v for _, v in complete_months((c.get("followers") or {}).get("series"), asof)]
    headcount = [v for _, v in complete_months((c.get("headcount") or {}).get("series"), asof)]
    posts = complete_months(c.get("postings"), asof)
    flags = []

    visitors = series[-1] if series else None
    kw_total = s.get("total_organic_results")
    seo_ok = live and not (kw_total is not None and kw_total < 5000 and (visitors or 0) > 1_000_000)
    if live and not seo_ok:
        flags.append(("seo_unreliable", "Search data looks broken for this brand, so search and ad measures are ignored"))
    if not t:
        flags.append(("no_traffic", "No website traffic recorded for this company's own domain"))
    elif len(series) < 13:
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
    if raise_date and raise_date[:10] > asof.isoformat():
        raise_date = None  # the raise hadn't happened yet on this date

    # Traffic-source shares have monthly history in live records; older records only have today's value.
    snap = lambda key: t.get(key) if live else None
    return {
        "id": c["id"],
        "name": c["name"].replace("®", ""),
        "domain": c["domain"],
        "size": c.get("size"),
        "visitors": visitors,
        "visitor_series": traffic,
        "visitors_12m": _pct(series[-1], series[-13]) if len(series) >= 13 else None,
        "visitors_3m": _pct(series[-1], series[-4]) if len(series) >= 4 else None,
        "search_pct": _as_of(t.get("search_series"), asof, snap("search_pct")),
        "direct_pct": _as_of(t.get("direct_series"), asof, snap("direct_pct")),
        "paid_pct": _as_of(t.get("paid_series"), asof, snap("paid_pct")),
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
