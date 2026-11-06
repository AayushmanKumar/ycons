import unittest

from market_radar import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.db = store.connect(":memory:")
        self.addCleanup(self.db.close)
        store.upsert_company(self.db, 1, "Rippling", "rippling.com", "1001-5000")
        store.upsert_company(self.db, 2, "Deel", "deel.com", "5001-10000")

    def test_market_members_replaced_and_filtered(self):
        store.save_market(self.db, "self", "you", 1, [
            {"domain": "rippling.com", "company_id": 1, "is_self": True, "kept": True, "reason": "You"},
            {"domain": "deel.com", "company_id": 2, "kept": True, "reason": "Bids on the same Google ads"},
            {"domain": "capcut.com", "kept": False, "reason": "Too small to compare"},
        ])
        self.assertEqual(len(store.members(self.db, "self")), 3)
        kept = store.members(self.db, "self", kept_only=True)
        self.assertEqual([m["domain"] for m in kept], ["rippling.com", "deel.com"])
        self.assertTrue(kept[0]["is_self"])

        store.save_market(self.db, "self", "you", 1, [
            {"domain": "rippling.com", "company_id": 1, "is_self": True, "kept": True, "reason": "You"}])
        self.assertEqual(len(store.members(self.db, "self")), 1)

    def test_snapshot_skipped_when_source_not_refreshed(self):
        self.assertTrue(store.add_snapshot(self.db, 2, {"v": 1}, "2026-10-01", fetched_at="2026-10-05"))
        self.assertFalse(store.add_snapshot(self.db, 2, {"v": 2}, "2026-10-01", fetched_at="2026-10-12"))
        self.assertTrue(store.add_snapshot(self.db, 2, {"v": 3}, "2026-10-20", fetched_at="2026-10-26"))
        self.assertEqual(store.latest_snapshot(self.db, 2)["payload"], {"v": 3})
        self.assertEqual(store.latest_snapshot(self.db, 2, as_of="2026-10-20")["payload"], {"v": 1})
        self.assertIsNone(store.latest_snapshot(self.db, 2, as_of="2026-09-01"))

    def test_ping_never_stored_twice(self):
        ping = {"key": "deel.com:threat:2026-10", "market": "self", "company_id": 2, "kind": "threat", "title": "x"}
        self.assertTrue(store.add_ping(self.db, ping, "2026-10-05"))
        self.assertFalse(store.add_ping(self.db, ping, "2026-10-12"))
        stored = store.pings(self.db)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["first_seen"], "2026-10-05")
        self.assertEqual(store.pings(self.db, as_of="2026-10-01"), [])


if __name__ == "__main__":
    unittest.main()
