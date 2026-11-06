"""Minimal Crustdata REST client: auth, retries, clear errors, on-disk cache.

Standard library only. Every call goes through `call()`.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

BASE_URL = "https://api.crustdata.com"
API_VERSION = "2025-11-01"
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "raw" / "cache"
MAX_RETRIES = 4


class CrustdataError(Exception):
    def __init__(self, status, message, retryable=False):
        super().__init__(f"Crustdata {status}: {message}")
        self.status, self.message, self.retryable = status, message, retryable


def api_key():
    key = os.environ.get("CRUSTDATA_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "CRUSTDATA_API_KEY":
                    key = value.strip().strip("'\"")
    if not key:
        raise CrustdataError(401, "CRUSTDATA_API_KEY is not set (add it to .env)")
    return key


def has_api_key():
    try:
        return bool(api_key())
    except CrustdataError:
        return False


def check_key(key):
    """Validate a key with the free credits endpoint. Returns the balance, or raises CrustdataError."""
    req = urllib.request.Request(BASE_URL + "/account/credits", method="GET", headers={
        "authorization": f"Bearer {key}", "x-api-version": API_VERSION, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return (json.loads(resp.read()).get("account") or {}).get("credits")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise CrustdataError(e.code, "That key was rejected by Crustdata.") from None
        raise CrustdataError(e.code, "Crustdata didn't respond as expected. Try again.") from None
    except urllib.error.URLError as e:
        raise CrustdataError(0, f"Couldn't reach Crustdata: {e.reason}") from None


def save_api_key(key):
    """Write the key to .env (gitignored) and use it for this process."""
    env = ROOT / ".env"
    lines = env.read_text().splitlines() if env.exists() else []
    lines = [l for l in lines if l.partition("=")[0].strip() != "CRUSTDATA_API_KEY"]
    env.write_text("\n".join(lines + [f"CRUSTDATA_API_KEY={key}"]) + "\n")
    env.chmod(0o600)
    os.environ["CRUSTDATA_API_KEY"] = key


def credits():
    """Current balance (free call), or None if it can't be read."""
    try:
        return call("/account/credits", method="GET", use_cache=False)["account"]["credits"]
    except (CrustdataError, KeyError, TypeError):
        return None


def _cache_path(method, path, body):
    raw = json.dumps([method, path, body], sort_keys=True).encode()
    return CACHE_DIR / date.today().isoformat() / f"{hashlib.sha256(raw).hexdigest()[:24]}.json"


def _wait_seconds(headers, attempt):
    reset = headers.get("x-ratelimit-reset") if headers else None
    try:
        value = float(reset)
        # The header may be seconds-to-wait or an epoch timestamp.
        return max(1.0, value - time.time()) if value > 1e9 else max(1.0, value)
    except (TypeError, ValueError):
        return min(30.0, 2.0 ** attempt)


def call(path, body=None, method="POST", use_cache=True):
    """Call an endpoint and return parsed JSON. Cached per day unless use_cache=False."""
    cache = _cache_path(method, path, body)
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "authorization": f"Bearer {api_key()}",
        "x-api-version": API_VERSION,
        "content-type": "application/json",
        "accept": "application/json",
    }
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read() or b"null")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload))
            return payload
        except urllib.error.HTTPError as e:
            message = e.read().decode(errors="replace")[:500]
            if e.code == 401:
                raise CrustdataError(401, "API key rejected. Check CRUSTDATA_API_KEY.") from None
            if e.code == 402:
                raise CrustdataError(402, "Out of credits. Retrying won't help.") from None
            if e.code == 403:
                raise CrustdataError(403, f"Not allowed on this plan: {message}") from None
            if e.code == 429 or e.code >= 500:
                if attempt == MAX_RETRIES:
                    raise CrustdataError(e.code, message, retryable=True) from None
                time.sleep(_wait_seconds(e.headers, attempt))
                continue
            raise CrustdataError(e.code, message) from None
        except urllib.error.URLError as e:
            if attempt == MAX_RETRIES:
                raise CrustdataError(0, f"Network error: {e.reason}", retryable=True) from None
            time.sleep(min(30.0, 2.0 ** attempt))


# ---- thin endpoint helpers -------------------------------------------------

def chunks(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def identify(domains, fields=("crustdata_company_id", "basic_info")):
    """Free. Returns a list of {matched_on, matches: [{confidence_score, company_data}]}."""
    out = []
    for batch in chunks(list(domains), 25):
        out += call("/company/identify", {"domains": batch, "fields": list(fields)})
    return out


def enrich(company_ids, fields, use_cache=True):
    """2 credits per returned match. Always by id, never by name/domain."""
    out = []
    for batch in chunks(list(company_ids), 25):
        out += call("/company/enrich", {"crustdata_company_ids": batch, "fields": list(fields)},
                    use_cache=use_cache)
    return out


def posting_counts(company_ids, start, end, use_cache=True):
    """Free aggregation: {company_id: number of postings added in [start, end)}."""
    body = {
        "filters": {"op": "and", "conditions": [
            {"field": "company.basic_info.company_id", "type": "in", "value": list(company_ids)},
            {"field": "metadata.date_added", "type": "=>", "value": start},
            {"field": "metadata.date_added", "type": "<", "value": end},
        ]},
        "limit": 0,
        "aggregations": [{"type": "group_by", "field": "company.basic_info.company_id", "agg": "count", "size": 1000}],
    }
    res = call("/job/search", body, use_cache=use_cache)
    buckets = (res.get("aggregations") or [{}])[0].get("buckets", [])
    return {int(b["key"]): b.get("count", 0) for b in buckets}
