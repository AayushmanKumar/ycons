import unittest
from datetime import date
from unittest import mock

from market_radar import check, crustdata, store
from tests.fake_crustdata import FakeAPI, company

TODAY = date(2026, 11, 9)


def world():
    return FakeAPI([
        company(1, "Alpha", "alpha.com", "1001-5000", 0.03, paid_seo=["beta.com", "gamma.com", "delta.com", "tiny.com"]),
        company(2, "Beta", "beta.com", "1001-5000", 0.06, ads=4_000_000, posts=120),
        company(3, "Gamma", "gamma.com", "1001-5000", -0.03, ads=200_000, posts=10),
        company(4, "Delta", "delta.com", "501-1000", 0.0),
        company(5, "Tiny", "tiny.com", "11-50", 0.1),
        company(10, "Client", "client.com", "1001-5000", 0.04, paid_seo=["rival.com", "rival2.com", "rival3.com"]),
        company(11, "Rival", "rival.com", "1001-5000", -0.02),
        company(12, "Rival Two", "rival2.com", "1001-5000", 0.01),
        company(13, "Rival Three", "rival3.com", "1001-5000", 0.0),
    ])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.db = store.connect(":memory:")
        self.addCleanup(self.db.close)
        self.api = world()
        patcher = mock.patch.object(crustdata, "call", self.api.call)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_setup_builds_markets_and_first_check(self):
        with mock.patch.object(check, "date") as d:
            d.today.return_value = TODAY
            summary = check.setup(self.db, "https://www.alpha.com", ["client.com", "alpha.com"])
        keys = {m["key"]: m["role"] for m in store.markets(self.db)}
        self.assertEqual(keys, {"self": "you", "client": "client"})
        members = {m["domain"]: m for m in store.members(self.db, "self")}
        self.assertFalse(members["tiny.com"]["kept"])  # too small
        self.assertEqual(summary["refreshed"], 8)    # alpha + 3 rivals + client + 3 rivals
        self.assertEqual(summary["errors"], [])

        vm = check.build(self.db, TODAY)
        self.assertEqual({m["key"] for m in vm["markets"]}, {"self", "client"})
        self.assertEqual(vm["self_domain"], "alpha.com")

    def test_second_run_stores_and_pings_nothing_new(self):
        check.setup(self.db, "alpha.com", ["client.com"])
        first = len(store.pings(self.db))
        again = check.run(self.db, today=TODAY)
        self.assertEqual(again["refreshed"], 0)
        self.assertEqual(again["unchanged"], 8)
        self.assertEqual(again["new_pings"], [])
        self.assertEqual(len(store.pings(self.db)), first)

    def test_new_funding_round_pings_once(self):
        check.setup(self.db, "alpha.com", ["client.com"])
        self.api.companies["beta.com"]["funding"]["last_fundraise_date"] = "2026-11-01"
        self.api.companies["beta.com"]["funding"]["last_round_type"] = "series_c"
        r1 = check.run(self.db, today=TODAY)
        self.assertEqual(r1["refreshed"], 1)
        self.assertIn("Beta just raised a series c", r1["new_pings"])
        r2 = check.run(self.db, today=TODAY)
        self.assertNotIn("Beta just raised a series c", r2["new_pings"])

    def test_new_competitor_detected_and_tracked(self):
        check.setup(self.db, "alpha.com", [])
        self.api.companies["epsilon.com"] = company(6, "Epsilon", "epsilon.com", "1001-5000", 0.02)
        self.api.companies["alpha.com"]["competitors"]["paid_seo"].append("epsilon.com")
        r = check.run(self.db, today=TODAY)
        self.assertEqual(r["new_competitors"], ["epsilon.com"])
        self.assertIn("New competitor: Epsilon", r["new_pings"])
        kept = {m["domain"] for m in store.members(self.db, "self", kept_only=True)}
        self.assertIn("epsilon.com", kept)


if __name__ == "__main__":
    unittest.main()
