"""The weekly check (and "Fetch latest"): re-fetch, snapshot, re-score, ping.

Not real-time. Crustdata refreshes companies every 1-30 days, so a company
whose data hasn't changed since the last snapshot is skipped, and nothing is
pinged twice.

Also `setup()`: build markets for a company and its clients, then run a check.
"""
from datetime import date

from . import competitors, crustdata, pings, resolve, signals, store, view

MAX_NEW_COMPETITORS = 5


# ---- reading live data --------------------------------------------------------

def inputs(db, asof=None):
    """Stored markets + snapshots -> (groups, records, fetched, self_domain)."""
    groups, records, self_domain = [], {}, None
    cutoff = f"{asof.isoformat()}T23:59:59" if asof else None
    for m in store.markets(db):
        mem = store.members(db, m["key"])
        me = next((x for x in mem if x["is_self"]), None)
        if not me:
            continue
        if m["role"] == "you":
            self_domain = me["domain"]
        groups.append({"key": m["key"], "role": m["role"], "self_domain": me["domain"],
                       "members": [{"domain": x["domain"], "kept": bool(x["kept"]), "reason": x["reason"]} for x in mem]})
        for x in mem:
            if x["kept"] and x["company_id"] and x["domain"] not in records:
                snap = store.latest_snapshot(db, x["company_id"], cutoff) or store.earliest_snapshot(db, x["company_id"])
                if snap:
                    records[x["domain"]] = snap["payload"]
    return groups, records, store.last_fetch(db), self_domain


def build(db, asof):
    groups, records, fetched, self_domain = inputs(db, asof)
    if not fetched or not self_domain:
        return None
    return view.build(groups, records, fetched, asof, self_domain)


def has_live_data(db):
    return bool(store.markets(db)) and store.last_fetch(db) is not None


# ---- the check ----------------------------------------------------------------

def _tracked(db):
    seen, out = set(), []
    for m in store.markets(db):
        for x in store.members(db, m["key"], kept_only=True):
            if x["company_id"] and x["company_id"] not in seen:
                seen.add(x["company_id"])
                out.append({"id": x["company_id"], "domain": x["domain"]})
    return out


def _find_new_competitors(db, records, today):
    """Companies that started bidding on the same ads since the market was built."""
    found = []
    for m in store.markets(db):
        mem = store.members(db, m["key"])
        me = next((x for x in mem if x["is_self"]), None)
        rec = records.get(me["domain"]) if me else None
        if not rec:
            continue
        known = {x["domain"] for x in mem}
        fresh = [d for d in rec.get("paid_seo", []) if d not in known][:MAX_NEW_COMPETITORS]
        if not fresh:
            continue
        identified = {r.get("matched_on"): r for r in crustdata.identify(fresh)}
        log = competitors.screen([(d, f"New: started bidding on the same Google ads ({today})") for d in fresh],
                                 identified, me["company_id"])
        kept = [x for x in log if x["kept"]]
        for x in kept:
            c = x["company"]
            store.upsert_company(db, c["id"], c["name"], c["domain"], c["size"])
        store.save_market(db, m["key"], m["role"], me["company_id"],
                          [{"domain": x["domain"], "company_id": x["company_id"], "is_self": bool(x["is_self"]),
                            "kept": bool(x["kept"]), "reason": x["reason"]} for x in mem] + log)
        found += [(m["key"], x["domain"], x["company"]["name"]) for x in kept]
    return found


def run(db, today=None, use_cache=False):
    """Fetch every tracked company, store changed snapshots, and record new pings.

    use_cache=False for the weekly check and "Fetch latest"; True reuses today's cache.
    Returns a summary dict.
    """
    today = today or date.today()
    iso = today.isoformat()
    tracked = _tracked(db)
    if not tracked:
        raise ValueError("No markets set up yet")

    previous = {c["id"]: store.latest_snapshot(db, c["id"]) for c in tracked}
    records = signals.fetch(tracked, today, use_cache=use_cache)

    new_comps = _find_new_competitors(db, records, iso)
    if new_comps:
        extra = [c for c in _tracked(db) if c["domain"] not in records]
        records.update(signals.fetch(extra, today, use_cache=use_cache))

    refreshed = unchanged = 0
    for rec in records.values():
        rec["snapshot_date"] = iso
        if store.add_snapshot(db, rec["id"], rec, signals.fingerprint(rec, today), fetched_at=iso):
            refreshed += 1
        else:
            unchanged += 1

    vm = build(db, today)
    candidates = []
    for m in vm["markets"]:
        candidates += m["pings"]
        for r in m["rows"]:
            prev = previous.get(r["id"])
            cur = records.get(r["domain"])
            if prev and cur:
                p = pings.funding_round(m, r, prev["payload"].get("funding"), cur.get("funding"), iso)
                if p:
                    candidates.append(p)
    by_key = {m["key"]: m for m in vm["markets"]}
    candidates += [pings.new_competitor(by_key[k], d, name, iso) for k, d, name in new_comps if k in by_key]

    new = [p for p in candidates if store.add_ping(db, p, iso)]
    return {
        "date": iso,
        "companies": len(records),
        "refreshed": refreshed,
        "unchanged": unchanged,
        "missing": sorted({c["domain"] for c in tracked} - set(records)),
        "new_competitors": [d for _, d, _ in new_comps],
        "new_pings": [p["title"] for p in new],
    }


# ---- setup ----------------------------------------------------------------------

def client_key(domain, taken):
    base = resolve.normalize_domain(domain).split(".")[0] or "client"
    key, n = base, 2
    while key in taken or key == "self":
        key, n = f"{base}{n}", n + 1
    return key


def setup(db, self_domain, client_domains, use_cache=True):
    """Build your market and one market per client, then run a first check."""
    store.delete_markets(db)
    competitors.build_market(db, "self", "you", self_domain)
    errors, taken = [], set()
    for d in client_domains:
        d = resolve.normalize_domain(d)
        if not d or d == resolve.normalize_domain(self_domain):
            continue
        key = client_key(d, taken)
        try:
            competitors.build_market(db, key, "client", d)
            taken.add(key)
        except (competitors.DiscoveryError, crustdata.CrustdataError) as e:
            errors.append(f"{d}: {e}")
    summary = run(db, use_cache=use_cache)
    summary["errors"] = errors
    return summary
