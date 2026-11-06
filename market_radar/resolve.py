"""Domain -> verified Crustdata company. Never trust a match without checking it."""
from urllib.parse import urlparse

MIN_CONFIDENCE = 0.9


def normalize_domain(value):
    """'https://www.Deel.com/pricing ' -> 'deel.com'."""
    value = (value or "").strip().lower()
    if not value:
        return ""
    host = urlparse(value if "://" in value else f"//{value}").hostname or ""
    return host.removeprefix("www.")


def check_match(domain, identify_row):
    """Verify one identify result for `domain`.

    Returns (company, None) when it passes, or (None, reason) when it doesn't.
    company = {id, name, domain, size, industries}
    """
    matches = (identify_row or {}).get("matches") or []
    if not matches:
        return None, "No company found for this domain"
    best = matches[0]
    data = best.get("company_data") or {}
    info = data.get("basic_info") or {}
    if (best.get("confidence_score") or 0) < MIN_CONFIDENCE:
        return None, f"Weak match ({best.get('confidence_score', 0):.2f} confidence)"
    domains = {normalize_domain(d) for d in [info.get("primary_domain"), *(info.get("all_domains") or [])] if d}
    if domain not in domains:
        found = info.get("primary_domain") or "no domain"
        return None, f"Domain mismatch: matched {info.get('name') or 'unknown'} ({found})"
    if not info.get("name") or not data.get("crustdata_company_id"):
        return None, "Match is missing a name or id"
    return {
        "id": data["crustdata_company_id"],
        "name": info["name"].replace("®", "").strip(),
        "domain": domain,
        "size": info.get("employee_count_range"),
        "industries": info.get("industries") or [],
        "description": info.get("description") or "",
    }, None
