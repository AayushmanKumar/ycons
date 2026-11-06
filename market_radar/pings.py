"""Turns scored markets into pings: what changed, what it means, what to do, sources.

Rule-based on purpose: the verdict and the action are decided here, not by an LLM.
"""


def _fmt_pct(v):
    return "n/a" if v is None else f"{v:+.0f}%"


def _money(v):
    if v is None:
        return "n/a"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:.0f}"


def _sources(r, keys, fetched):
    fields = {
        "visitors_12m": ("web_traffic · monthly visitors, 12-month change", _fmt_pct),
        "visitors_3m": ("web_traffic · visitors, last quarter", _fmt_pct),
        "ads_budget": ("seo · Google Ads budget per month", _money),
        "postings_change": ("job_search · postings, last 3 vs previous 3 months", _fmt_pct),
        "followers_yoy": ("followers · 12-month change", _fmt_pct),
        "last_raise": ("funding · last raise", lambda v: v or "n/a"),
    }
    return [{"field": fields[k][0], "value": fields[k][1](r.get(k)), "fetched": fetched} for k in keys]


def _ping(kind, r, title, meaning, action, keys, fetched, market):
    return {
        "kind": kind,  # threat | opportunity | watch
        "company": r["name"],
        "domain": r["domain"],
        "title": title,
        "meaning": meaning,
        "action": action,
        "sources": _sources(r, keys, fetched),
        "market": market["key"],
        "track": market["role"],
        "client": None if market["role"] == "you" else market["self_name"],
        "key": f"{r['domain']}:{kind}:{fetched[:7]}",  # dedupe key: company + event + period
    }


def for_market(market, fetched):
    out = []
    client = market["self_name"]
    for r in market["rows"]:
        v, p = r["verdict"], r["pattern"]
        if market["role"] == "you":
            if r["is_self"]:
                continue
            has_ads = r["ads_budget"] is not None
            if p in ("Making a push", "Expanding fast"):
                spend = f"Ad spend {_money(r['ads_budget'])}/mo and h" if has_ads else "H"
                out.append(_ping(
                    "threat", r, f"{r['name']} is making a push",
                    f"{spend}iring {_fmt_pct(r['postings_change'])}, visitors {_fmt_pct(r['visitors_3m'])} "
                    "last quarter. It's investing to win share, and price cuts often follow.",
                    "Lock your biggest accounts into longer contracts before their sales team reaches them.",
                    (["ads_budget"] if has_ads else []) + ["postings_change", "visitors_3m", "last_raise"],
                    fetched, market))
            elif v == "falling" or (p == "Paying to cover a decline" and has_ads):
                spend = f" while still spending {_money(r['ads_budget'])}/mo on ads" if has_ads else ""
                out.append(_ping(
                    "opportunity", r, f"{r['name']} is losing ground",
                    f"Visitors {_fmt_pct(r['visitors_3m'])} last quarter{spend}. "
                    "Its customers may be shopping around.",
                    "Run a switch campaign aimed at its customers this month.",
                    ["visitors_3m", "visitors_12m"] + (["ads_budget"] if has_ads else []), fetched, market))
            elif p == "Pulling back":
                out.append(_ping(
                    "watch", r, f"{r['name']} is cutting back",
                    f"Hiring {_fmt_pct(r['postings_change'])} and ad spend low. It's saving cash, not attacking.",
                    "Lower priority. Watch for layoffs or leadership changes.",
                    ["postings_change", "ads_budget", "last_raise"], fetched, market))
        else:
            if r["is_self"]:
                if v == "rising" or p in ("Growing efficiently", "Making a push", "Expanding fast"):
                    out.append(_ping(
                        "opportunity", r, f"Your client {r['name']} is winning its market",
                        f"Visitors {_fmt_pct(r['visitors_12m'])} over the year, ahead of its rivals. "
                        "Its teams will grow, and so will its need for you.",
                        "Pitch an expansion before the renewal.",
                        ["visitors_12m", "postings_change", "followers_yoy"], fetched, market))
                elif v == "falling" or p in ("Pulling back", "Paying to cover a decline"):
                    out.append(_ping(
                        "threat", r, f"Your client {r['name']} is losing ground",
                        f"Visitors {_fmt_pct(r['visitors_12m'])} over the year, behind its rivals. "
                        "Expect cost cuts, and you're a cost.",
                        "Protect the account: offer flexible terms before renewal.",
                        ["visitors_12m", "postings_change", "ads_budget"], fetched, market))
            elif v == "rising" or p in ("Making a push", "Expanding fast"):
                out.append(_ping(
                    "opportunity", r, f"Prospect: {r['name']} is growing",
                    f"A competitor of your client {client}, growing fast "
                    f"(hiring {_fmt_pct(r['postings_change'])}, visitors {_fmt_pct(r['visitors_12m'])}).",
                    f"Pitch them: teams like {client} already use you.",
                    ["postings_change", "visitors_12m", "last_raise"], fetched, market))
    return out
