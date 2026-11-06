import unittest
from datetime import date

from market_radar import score, signals, view
from tests.fake_crustdata import company


class ScoreTest(unittest.TestCase):
    def test_percentiles_share_ties(self):
        p = score.percentiles({"a": 1, "b": 2, "c": 2, "d": 3, "e": None})
        self.assertEqual(p["a"], 0)
        self.assertEqual(p["b"], p["c"])
        self.assertEqual(p["d"], 1)
        self.assertNotIn("e", p)

    def test_verdict_needs_three_of_four(self):
        self.assertEqual(score.verdict({"demand": 0.9, "search": 0.8, "marketing": 0.75, "company": 0.1}), "rising")
        self.assertEqual(score.verdict({"demand": 0.9, "search": 0.8, "marketing": 0.5, "company": 0.1}), "mixed")
        self.assertEqual(score.verdict({"demand": 0.1, "search": 0.2, "marketing": 0.3, "company": None}), "falling")

    def test_two_families_must_both_agree(self):
        self.assertEqual(score.verdict({"demand": 0.9, "search": None, "marketing": None, "company": 0.8}), "rising")
        self.assertEqual(score.verdict({"demand": 0.9, "search": None, "marketing": None, "company": 0.5}), "mixed")
        self.assertEqual(score.verdict({"demand": 0.9, "search": None, "marketing": None, "company": None}), "mixed")

    def test_second_place_of_four_is_not_up(self):
        rows = [{"id": i, "visitors_12m": v, "visitors_3m": v} for i, v in enumerate([1, 2, 3, 4])]
        score.score_market(rows)
        self.assertLess(rows[2]["families"]["demand"], score.UP)  # 2nd place = 0.67


class SignalsTest(unittest.TestCase):
    def rec(self, **kw):
        data = company(1, "Alpha", "alpha.com", "1001-5000", 0.05, **kw)
        postings = [[m, 50] for m in ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]]
        r = signals.record({k: v for k, v in data.items() if not k.startswith("_")}, "alpha.com", postings)
        r["snapshot_date"] = "2026-11-09"
        return r

    def test_traffic_only_from_own_domain(self):
        data = company(1, "HubSpot", "hubspot.com", "5001-10000", 0.0)
        data["web_traffic"]["domain_traffic"] = {"gzconsulting.org": data["web_traffic"]["domain_traffic"]["hubspot.com"]}
        r = signals.record(data, "hubspot.com", [])
        self.assertIsNone(r["traffic"])

    def test_metrics_use_only_data_that_existed(self):
        r = self.rec()
        past = signals.company_metrics(r, date(2026, 6, 15))
        self.assertEqual(past["visitor_series"][-1][0], "2026-05")   # June isn't complete yet
        self.assertIsNone(past["ads_budget"])                         # snapshot-only, taken in Nov
        self.assertIsNone(past["postings_change"])                    # needs 6 complete months
        now = signals.company_metrics(r, date(2026, 11, 9))
        self.assertEqual(now["ads_budget"], 1_000_000)
        self.assertEqual(now["postings_last3"], 150)                  # Aug-Oct; Nov is partial

    def test_raise_after_date_is_hidden(self):
        r = self.rec(raised="2026-09-01")
        self.assertIsNone(signals.company_metrics(r, date(2026, 8, 1))["last_raise"])
        self.assertEqual(signals.company_metrics(r, date(2026, 9, 2))["last_raise"], "2026-09-01")

    def test_fingerprint_ignores_partial_month(self):
        a, b = self.rec(), self.rec()
        b["postings"][-1][1] = 999  # current month still filling up
        self.assertEqual(signals.fingerprint(a, date(2026, 11, 9)), signals.fingerprint(b, date(2026, 11, 9)))

    def test_acquired_company_dropped_from_market(self):
        parent = self.rec()
        child = {**self.rec(), "id": 2, "domain": "child.com", "name": "Child"}
        parent["funding"]["acquisition_ids"] = [2]
        out = view.acquired_in_set([parent, child])
        self.assertIn("Acquired by Alpha", out["child.com"])


if __name__ == "__main__":
    unittest.main()
