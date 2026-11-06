"""Relative scoring: rank each measure within a competitor set, roll up into
four families, and apply the 3-of-4 verdict rule.

Pure functions, no I/O. Same input always gives the same verdict.
"""

# family -> [(metric key, direction)]  direction +1 = higher is "up"
FAMILIES = {
    "demand": [("visitors_12m", 1), ("visitors_3m", 1)],
    "search": [("kw_net_pct", 1)],
    "marketing": [("ads_budget", 1), ("paid_pct", 1)],
    "company": [("postings_change", 1), ("followers_yoy", 1), ("months_since_raise", -1)],
}

FAMILY_LABELS = {
    "demand": "Demand",
    "search": "Search position",
    "marketing": "Marketing push",
    "company": "Company momentum",
}

# A family is "up" in the top 30% of its set, "down" in the bottom 30%.
# (0.6/0.4 let 2nd place in a 4-company set count as "up".)
UP, DOWN = 0.7, 0.3


def percentiles(values):
    """{id: value or None} -> {id: 0..1 rank}; ties share their average rank."""
    present = {k: v for k, v in values.items() if v is not None}
    if len(present) < 2:
        return {}
    ordered = sorted(present.items(), key=lambda kv: kv[1])
    n = len(ordered)
    ranks, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        avg = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            ranks[ordered[k][0]] = avg
        i = j + 1
    return ranks


def score_market(rows):
    """rows: list of dicts with 'id' and metric keys. Adds 'families', 'verdict', 'pattern'."""
    pct = {}
    for metrics in FAMILIES.values():
        for key, direction in metrics:
            ranks = percentiles({r["id"]: r.get(key) for r in rows})
            pct[key] = {k: (v if direction > 0 else 1 - v) for k, v in ranks.items()}

    for r in rows:
        fam = {}
        for name, metrics in FAMILIES.items():
            vals = [pct[k][r["id"]] for k, _ in metrics if r["id"] in pct[k]]
            fam[name] = sum(vals) / len(vals) if vals else None
        r["families"] = fam
        r["verdict"] = verdict(fam)
        r["pattern"] = pattern(fam)
    return rows


def needed_agreement(n_scored):
    """3 of 4 normally; when only 2 families have data (past dates), both must agree."""
    if n_scored >= 3:
        return 3
    if n_scored == 2:
        return 2
    return None


def verdict(fam):
    scored = [v for v in fam.values() if v is not None]
    need = needed_agreement(len(scored))
    if need is None:
        return "mixed"
    if sum(v >= UP for v in scored) >= need:
        return "rising"
    if sum(v <= DOWN for v in scored) >= need:
        return "falling"
    return "mixed"


def _state(v):
    if v is None:
        return None
    return "up" if v >= UP else "down" if v <= DOWN else "flat"


def pattern(fam):
    a, c, d = _state(fam["demand"]), _state(fam["marketing"]), _state(fam["company"])
    if a == "down" and c == "up":
        return "Paying to cover a decline"
    if c == "up" and d == "up":
        return "Making a push"
    if c is None and a == "up" and d == "up":
        return "Expanding fast"  # no ad data on past dates: hiring + demand only
    if a == "up" and c in ("down", "flat"):
        return "Growing efficiently"
    if c == "down" and d == "down":
        return "Pulling back"
    return None
