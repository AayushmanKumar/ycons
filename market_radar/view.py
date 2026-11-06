"""Build the dashboard view-model from markets + company records, as of a date.

Shared by the demo sample and live data, so the UI can't tell them apart.

groups:  [{key, role ('you'|'client'), self_domain, members: [{domain, kept, reason}]}]
records: {domain: record}  (see signals.record)
"""
from . import pings, score, signals

MIN_STAFF = 200


def acquired_in_set(records):
    """{domain: reason} for companies acquired by *another company in the same set*.

    Being bought by a PE fund or an outsider doesn't stop a company competing,
    and Crustdata's acquired_by is noisy, so only in-set consolidation counts.
    """
    by_id = {r["id"]: r for r in records}
    out = {}
    for r in records:
        for a in (r.get("funding") or {}).get("acquired_by") or []:
            acquirer = by_id.get(a.get("id")) if isinstance(a, dict) else None
            if acquirer and acquirer["id"] != r["id"]:
                out[r["domain"]] = f"Acquired by {acquirer['name']}, so it's no longer a separate competitor"
        for cid in (r.get("funding") or {}).get("acquisition_ids") or []:
            if cid in by_id and by_id[cid]["domain"] != r["domain"]:
                out[by_id[cid]["domain"]] = f"Acquired by {r['name']}, so it's no longer a separate competitor"
    return out


def build_market(group, records, asof):
    self_domain = group["self_domain"]
    present = [records[m["domain"]] for m in group["members"] if m["kept"] and m["domain"] in records]
    acquired = acquired_in_set(present)

    rows, log = [], []
    for m in group["members"]:
        is_self = m["domain"] == self_domain
        rec = records.get(m["domain"])
        if not is_self and m["kept"] and m["domain"] in acquired:
            log.append({"domain": m["domain"], "kept": False, "reason": acquired[m["domain"]]})
            continue
        staff = ((rec or {}).get("headcount") or {}).get("total")
        if not is_self and m["kept"] and staff is not None and staff < MIN_STAFF:
            # Size labels can show the parent's size (Site24x7 is labelled like Zoho but lists 24 staff).
            log.append({"domain": m["domain"], "kept": False,
                        "reason": f"Only {staff} staff listed; likely a product line of a bigger company"})
            continue
        if m["kept"] and rec:
            row = signals.company_metrics(rec, asof)
            row["is_self"] = is_self
            rows.append(row)
        if not is_self:
            reason = m["reason"] if (rec or not m["kept"]) else "Kept, but no data returned for it yet"
            log.append({"domain": m["domain"], "kept": bool(m["kept"] and rec), "reason": reason})
    if not any(r["is_self"] for r in rows):
        return None

    total_search = sum((r["visitors"] or 0) * (r["search_pct"] or 0) / 100 for r in rows)
    for r in rows:
        sv = (r["visitors"] or 0) * (r["search_pct"] or 0) / 100
        r["share_of_search"] = sv / total_search * 100 if total_search else None

    score.score_market(rows)
    market = {
        "key": group["key"],
        "role": group["role"],
        "self_domain": self_domain,
        "self_name": next(r["name"] for r in rows if r["is_self"]),
        "rows": rows,
        "discovery": log,
    }
    market["pings"] = pings.for_market(market, asof.isoformat())
    return market


def build(groups, records, fetched, asof, self_domain):
    markets = [m for m in (build_market(g, records, asof) for g in groups) if m]
    return {"fetched_at": fetched, "asof": asof, "live": asof.isoformat() >= fetched,
            "self_domain": self_domain, "markets": markets}
