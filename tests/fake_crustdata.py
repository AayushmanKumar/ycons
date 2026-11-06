"""A tiny in-memory stand-in for the Crustdata API, for tests. No network, no credits."""

MONTHS = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:23]  # 2025-01 .. 2026-11


def company(cid, name, domain, size, growth, paid_seo=(), raised="2024-01-10", ads=1_000_000, posts=50):
    visitors = [int(100_000 * (1 + growth) ** i) for i in range(len(MONTHS))]
    return {
        "crustdata_company_id": cid,
        "basic_info": {"name": name, "primary_domain": domain, "all_domains": [domain],
                       "employee_count_range": size, "industries": ["Software Development"],
                       "description": f"{name} makes software"},
        "web_traffic": {"domain_traffic": {domain: {
            "monthly_visitors": visitors[-1], "qoq_pct": 0, "source_search_pct": 20,
            "source_direct_pct": 50, "source_paid_referral_pct": 1,
            "monthly_visitors_timeseries": [{"date": f"{m}-01T00:00:00+00:00", "monthly_visitors": v}
                                            for m, v in zip(MONTHS, visitors)],
        }}},
        "seo": {"total_organic_results": 50_000, "gained_ranked_seo_keywords": 1000, "newly_ranked_seo_keywords": 1000,
                "lost_ranked_seo_keywords": 500, "monthly_google_ads_budget": ads},
        "headcount": {"total": 1000, "growth_percent": {"yoy": 10},
                      "timeseries": [{"date": f"{m}-15", "employee_count": 1000} for m in MONTHS]},
        "followers": {"count": 10_000, "yoy_percent": 5,
                      "timeseries": [{"date": f"{m}-01", "follower_count": 10_000 + i * 100} for i, m in enumerate(MONTHS)]},
        "funding": {"last_fundraise_date": raised, "last_round_type": "series_b", "total_investment_usd": 1e8,
                    "acquired_by": [], "acquisitions": []},
        "competitors": {"paid_seo": list(paid_seo), "organic_seo": [], "all_domains": ["https://lookalike.com"]},
        "_posts": posts,
    }


class FakeAPI:
    def __init__(self, companies):
        self.companies = {c["basic_info"]["primary_domain"]: c for c in companies}
        self.calls = []

    def call(self, path, body=None, method="POST", use_cache=True):
        self.calls.append(path)
        by_id = {c["crustdata_company_id"]: c for c in self.companies.values()}
        if path == "/company/identify":
            out = []
            for d in body["domains"]:
                c = self.companies.get(d)
                out.append({"matched_on": d, "matches": [{"confidence_score": 1.0, "company_data": {
                    "crustdata_company_id": c["crustdata_company_id"], "basic_info": c["basic_info"]}}] if c else []})
            return out
        if path == "/company/enrich":
            strip = lambda c: {k: v for k, v in c.items() if not k.startswith("_")}
            return [{"matched_on": str(i), "matches": [{"confidence_score": 1, "company_data": strip(by_id[i])}]}
                    for i in body["crustdata_company_ids"] if i in by_id]
        if path == "/job/search":
            ids = body["filters"]["conditions"][0]["value"]
            return {"aggregations": [{"buckets": [{"key": i, "count": by_id[i]["_posts"]} for i in ids if i in by_id]}]}
        if path == "/company/search":
            return {"companies": []}
        raise AssertionError(f"unexpected call {path}")
