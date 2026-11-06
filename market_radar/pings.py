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
        "company_id": r.get("id"),
        "track": market["role"],
        "client": None if market["role"] == "you" else market["self_name"],
        # Dedupe key: market + company + event + month. A situation that persists
        # is re-raised at most once a month; a change event uses its own key.
        "key": f"{market['key']}:{r['domain']}:{kind}:{fetched[:7]}",
    }


def funding_round(market, r, prev_funding, cur_funding, fetched):
    """A new raise since the last snapshot. Rivals raising = threat; clients/prospects = opportunity."""
    new_date = (cur_funding or {}).get("last_date")
    if not new_date or new_date == (prev_funding or {}).get("last_date"):
        return None
    rnd = ((cur_funding or {}).get("last_round") or "funding round").replace("_", " ")
    is_rival = market["role"] == "you" and not r["is_self"]
    p = _ping(
        "threat" if is_rival else "opportunity", r, f"{r['name']} just raised a {rnd}",
        ("New money usually means more hiring and ad spend in the next two quarters."
         if is_rival else "Fresh budget: a good moment to talk about expanding."),
        ("Expect a push. Check your biggest accounts' renewal dates now." if is_rival
         else "Reach out this week while the budget is being planned."),
        ["last_raise", "postings_change", "visitors_3m"], fetched, market)
    p["key"] = f"{market['key']}:{r['domain']}:funding:{new_date[:10]}"
    return p


def new_competitor(market, domain, name, fetched):
    """A company that has started bidding on the same Google ads."""
    r = {"name": name, "domain": domain, "id": None}
    p = _ping(
        "watch", r, f"New competitor: {name}",
        f"{name} has started bidding on the same Google ads as {market['self_name']}.",
        "Take a look at its pricing and positioning. It's now tracked in this market.",
        [], fetched, market)
    p["sources"] = [{"field": "competitors · bids on the same Google ads", "value": domain, "fetched": fetched}]
    p["key"] = f"{market['key']}:{domain}:new_competitor"
    return p


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
