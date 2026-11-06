"""Demo data: the saved sample (data/raw/sample_market.json) as view inputs.

Rippling's point of view, with three hypothetical clients. Used when no live
markets have been set up, or when the demo is chosen explicitly.
"""
import json
from datetime import date
from pathlib import Path

from . import view

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "raw" / "sample_market.json"

SELF = "rippling.com"
SMALL_SIZES = {"1-10", "2-10", "11-50", "51-200"}

# Candidates rejected in earlier verification runs (kept so the UI can show why).
EARLIER_DROPS = {
    "self": [
        ("paycor.com", "Acquired by Paychex (2025), so it's no longer a separate competitor"),
        ("dudewipes.com", "From the look-alike-name list, which we ignore"),
    ],
    "datadog": [
        ("site24x7.com", "Product line of Zoho/ManageEngine (24 staff listed)"),
        ("manageengine.com", "Part of Zoho; its jobs are posted under Zoho"),
    ],
}


def available():
    return SAMPLE.exists()


def load():
    return json.loads(SAMPLE.read_text())


def inputs(raw):
    """Sample JSON -> (groups, records, fetched)."""
    fetched = raw["fetched_at"][:10]
    companies = raw["companies"]
    records = {dom: {**c, "snapshot_date": fetched} for dom, c in companies.items()}
    groups = []
    for g in raw["groups"]:
        self_paid = set(companies.get(g["self"], {}).get("paid_seo", []))
        members = []
        for dom in g["domains"]:
            c = companies.get(dom)
            if not c:
                continue
            if dom == g["self"]:
                members.append({"domain": dom, "kept": True, "reason": "The company being watched"})
            elif c.get("size") in SMALL_SIZES:
                members.append({"domain": dom, "kept": False,
                                "reason": f"Too small to compare ({c['size']} staff); likely a product line"})
            else:
                src = "Bids on the same Google ads" if dom in self_paid else "Ranks for the same searches"
                members.append({"domain": dom, "kept": True, "reason": src})
        members += [{"domain": d, "kept": False, "reason": why} for d, why in EARLIER_DROPS.get(g["key"], [])]
        groups.append({"key": g["key"], "role": "you" if g["key"] == "self" else "client",
                       "self_domain": g["self"], "members": members})
    return groups, records, fetched


def build(asof=None, raw=None):
    groups, records, fetched = inputs(raw or load())
    return view.build(groups, records, fetched, asof or date.fromisoformat(fetched), SELF)
