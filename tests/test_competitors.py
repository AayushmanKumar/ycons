import unittest

from market_radar import competitors, resolve


def row(domain, cid, name, primary, size, conf=1.0, all_domains=None):
    return {"matched_on": domain, "matches": [{"confidence_score": conf, "company_data": {
        "crustdata_company_id": cid,
        "basic_info": {"name": name, "primary_domain": primary, "all_domains": all_domains or [],
                       "employee_count_range": size, "industries": ["Software Development"]}}}]}


class ResolveTest(unittest.TestCase):
    def test_normalize_domain(self):
        self.assertEqual(resolve.normalize_domain("https://www.Deel.com/pricing "), "deel.com")
        self.assertEqual(resolve.normalize_domain(" bamboohr.com"), "bamboohr.com")
        self.assertEqual(resolve.normalize_domain(""), "")

    def test_wrong_company_at_full_confidence_is_rejected(self):
        # Real case: notion.so resolves to a 26-person company called Hustá.
        company, why = resolve.check_match("notion.so", row("notion.so", 9, "Hustá", None, "11-50"))
        self.assertIsNone(company)
        self.assertIn("Domain mismatch", why)

    def test_secondary_domain_accepted(self):
        company, _ = resolve.check_match("perfios.com", row("perfios.com", 6026, "Perfios", "perfios.ai",
                                                            "1001-5000", all_domains=["perfios.com"]))
        self.assertEqual(company["id"], 6026)


class ScreenTest(unittest.TestCase):
    def test_screening_rules(self):
        candidates = [("deel.com", "Bids on the same Google ads"), ("capcut.com", "Bids on the same Google ads"),
                      ("paycor.com", "Ranks for the same searches"), ("weak.com", "Ranks for the same searches"),
                      ("deel.io", "Ranks for the same searches"), ("nosize.com", "Ranks for the same searches")]
        identified = {
            "deel.com": row("deel.com", 2, "Deel", "deel.com", "5001-10000"),
            "capcut.com": row("capcut.com", 3, "CapCut", "capcut.com", "51-200"),
            "paycor.com": row("paycor.com", 4, "Paycor", "paycor.com", "1001-5000"),
            "weak.com": row("weak.com", 5, "Weak", "weak.com", "1001-5000", conf=0.6),
            "deel.io": row("deel.io", 2, "Deel", "deel.com", "5001-10000", all_domains=["deel.io"]),
            "nosize.com": row("nosize.com", 6, "NoSize", "nosize.com", None),
        }
        log = {m["domain"]: m for m in competitors.screen(candidates, identified, self_id=1)}
        self.assertTrue(log["deel.com"]["kept"])
        self.assertIn("Too small", log["capcut.com"]["reason"])
        self.assertIn("Acquired", log["paycor.com"]["reason"])
        self.assertIn("Weak match", log["weak.com"]["reason"])
        self.assertIn("Same company", log["deel.io"]["reason"])
        self.assertIn("No size data", log["nosize.com"]["reason"])
        self.assertEqual(sum(m["kept"] for m in log.values()), 1)

    def test_candidates_ignore_self_and_lookalike_list(self):
        record = {"competitors": {"paid_seo": [" deel.com", "rippling.com"], "organic_seo": ["deel.com", "paychex.com"],
                                  "all_domains": ["https://dudewipes.com"]}}
        got = competitors.candidate_domains(record, "rippling.com")
        self.assertEqual(got, [("deel.com", "Bids on the same Google ads"), ("paychex.com", "Ranks for the same searches")])


if __name__ == "__main__":
    unittest.main()
