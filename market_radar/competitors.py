"""Find a company's real competitors and record why each candidate was kept or dropped.

Candidates: companies bidding on the same Google ads (paid_seo), then those
ranking for the same searches (organic_seo). Never competitors.all_domains,
which is look-alike names. Fallback: companies doing similar work at a similar size.
"""
from . import crustdata, resolve, store
from .signals import COMPANY_FIELDS  # shared so the daily cache is reused

SMALL_SIZES = {"1-10", "2-10", "11-50", "51-200"}
MAX_COMPETITORS = 10
MIN_COMPETITORS = 3
MAX_CANDIDATES = 25

# Known acquisitions where Crustdata still lists the acquired company separately.
ACQUIRED = {"paycor.com": "Acquired by Paychex (2025), so it's no longer a separate competitor"}


class DiscoveryError(Exception):
    pass


def candidate_domains(self_record, self_domain):
    """Ordered, de-duplicated candidate domains with where each came from."""
    comp = self_record.get("competitors") or {}
    seen, out = {self_domain}, []
    for source, label in (("paid_seo", "Bids on the same Google ads"), ("organic_seo", "Ranks for the same searches")):
        for raw in comp.get(source) or []:
            d = resolve.normalize_domain(raw)
            if d and d not in seen:
                seen.add(d)
                out.append((d, label))
    return out[:MAX_CANDIDATES]


def screen(candidates, identified, self_id):
    """Apply the checks. candidates: [(domain, source)]; identified: {domain: identify row}.

    Returns a list of member dicts {domain, company_id, kept, reason, company}.
    """
    log, kept_ids = [], {self_id}
    for domain, source in candidates:
        if domain in ACQUIRED:
            log.append({"domain": domain, "kept": False, "reason": ACQUIRED[domain]})
            continue
        company, why = resolve.check_match(domain, identified.get(domain))
        if not company:
            log.append({"domain": domain, "kept": False, "reason": why})
            continue
        if not company["size"]:
            log.append({"domain": domain, "kept": False, "reason": "No size data, so it can't be compared fairly"})
            continue
        if company["size"] in SMALL_SIZES:
            log.append({"domain": domain, "kept": False,
                        "reason": f"Too small to compare ({company['size']} staff); likely a blog or product line"})
            continue
        if company["id"] in kept_ids:
            log.append({"domain": domain, "kept": False, "reason": "Same company as one already listed"})
            continue
        if sum(m["kept"] for m in log) >= MAX_COMPETITORS:
            log.append({"domain": domain, "kept": False, "reason": f"Beyond the top {MAX_COMPETITORS}"})
            continue
        kept_ids.add(company["id"])
        log.append({"domain": domain, "company_id": company["id"], "kept": True, "reason": source, "company": company})
    return log


def fallback_search(self_company, headcount, exclude_ids, limit=10):
    """Companies whose description best matches ours, at 0.3x-3x the headcount.

    Industry labels alone are too broad ("Software Development" returned grocery
    and ride-hailing apps for Snowflake), so rank by what the company does.
    """
    if not headcount or not (self_company.get("description") or self_company["industries"]):
        return []
    query = self_company.get("description") or " ".join(self_company["industries"])
    body = {
        "search": {"query": query[:400], "mode": "hybrid"},
        "filters": {"op": "and", "conditions": [
            {"field": "headcount.total", "type": "=>", "value": int(headcount * 0.3)},
            {"field": "headcount.total", "type": "=<", "value": int(headcount * 3)},
        ]},
        "limit": limit,
        "fields": ["crustdata_company_id", "basic_info"],
    }
    res = crustdata.call("/company/search", body)
    out = []
    for c in res.get("companies") or []:
        info = c.get("basic_info") or {}
        cid = c.get("crustdata_company_id")
        domain = resolve.normalize_domain(info.get("primary_domain"))
        if cid and domain and cid not in exclude_ids:
            out.append({"domain": domain, "company_id": cid, "kept": True,
                        "reason": "Does similar work at a similar size (fallback search)",
                        "company": {"id": cid, "name": info.get("name", domain), "domain": domain,
                                    "size": info.get("employee_count_range"), "industries": info.get("industries") or []}})
    return out


def discover(domain):
    """Resolve `domain`, find and screen its competitors. Returns (self_company, members)."""
    domain = resolve.normalize_domain(domain)
    (row,) = crustdata.identify([domain]) or [None]
    me, why = resolve.check_match(domain, row)
    if not me:
        raise DiscoveryError(f"Couldn't verify {domain}: {why}")

    (record,) = crustdata.enrich([me["id"]], COMPANY_FIELDS)
    self_data = ((record.get("matches") or [{}])[0]).get("company_data") or {}
    candidates = candidate_domains(self_data, domain)
    identified = {r.get("matched_on"): r for r in crustdata.identify([d for d, _ in candidates])} if candidates else {}
    log = screen(candidates, identified, me["id"])

    kept = [m for m in log if m["kept"]]
    if len(kept) < MIN_COMPETITORS:
        headcount = (self_data.get("headcount") or {}).get("total")
        extra = fallback_search(me, headcount, {me["id"], *(m["company_id"] for m in kept)})
        log += extra[:MAX_COMPETITORS - len(kept)]

    members = [{"domain": domain, "company_id": me["id"], "is_self": True, "kept": True,
                "reason": "The company being watched", "company": me}] + log
    return me, members


def build_market(db, key, role, domain):
    """Discover and persist a market. Returns the saved members."""
    me, members = discover(domain)
    for m in members:
        c = m.get("company")
        if c:
            store.upsert_company(db, c["id"], c["name"], c["domain"], c["size"])
    store.save_market(db, key, role, me["id"], members)
    return store.members(db, key)


if __name__ == "__main__":
    import sys
    me, members = discover(sys.argv[1])
    print(f"{me['name']} ({me['domain']}, {me['size']})")
    for m in members[1:]:
        print(f"  {'✓' if m['kept'] else '✕'} {m['domain']:<24} {m['reason']}")
