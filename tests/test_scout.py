"""Tests for the Scout Agent (discovery + enrichment)."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.scout import (
    BusinessDiscovery,
    GBPExtractor,
    ReviewScraper,
    ScoutAgent,
    WebsiteScraper,
)


class TestBusinessDiscovery(unittest.TestCase):
    """Unit tests for the BusinessDiscovery search engine scraper."""

    def test_clean_name_removes_suffixes(self):
        disc = BusinessDiscovery()
        self.assertEqual(disc._clean_name("Ace HVAC LLC - Austin"), "Ace HVAC")
        self.assertEqual(disc._clean_name("Best Plumbing Inc."), "Best Plumbing")

    def test_is_directory_blocks_yelp(self):
        disc = BusinessDiscovery()
        self.assertTrue(disc._is_directory("https://www.yelp.com/biz/some-place"))
        self.assertTrue(disc._is_directory("https://www.angi.com/company/some-id"))
        self.assertFalse(disc._is_directory("https://acehvac.com"))

    def test_domain_extraction(self):
        disc = BusinessDiscovery()
        self.assertEqual(disc._domain("https://www.acehvac.com/services"), "acehvac.com")
        self.assertEqual(disc._domain("http://example.com"), "example.com")

    def test_deduplication_by_domain(self):
        disc = BusinessDiscovery()
        raw = [
            {"name": "A", "website": "https://acehvac.com"},
            {"name": "A2", "website": "https://acehvac.com/page"},
            {"name": "B", "website": "https://bestplumbing.com"},
        ]
        deduped = []
        seen = set()
        for r in raw:
            d = disc._domain(r["website"])
            if d and d not in seen:
                seen.add(d)
                deduped.append(r)
        self.assertEqual(len(deduped), 2)


class TestWebsiteScraper(unittest.TestCase):
    """Unit tests for the WebsiteScraper."""

    def test_scrape_returns_structure_even_on_failure(self):
        scraper = WebsiteScraper(timeout=5)
        # Deliberately bad URL should not crash
        result = scraper.scrape("http://localhost:59999/nonexistent")
        self.assertIn("load_time_ms", result)
        self.assertIn("is_mobile_friendly", result)
        self.assertIn("has_booking_form", result)
        self.assertIn("cta_count", result)

    def test_analyze_soup_mobile_friendly(self):
        from bs4 import BeautifulSoup
        scraper = WebsiteScraper()
        html = '<html><head><meta name="viewport" content="width=device-width"></head><body>Book Now</body></html>'
        soup = BeautifulSoup(html, "lxml")
        out = scraper._analyze_soup(soup, "https://example.com")
        self.assertTrue(out["is_mobile_friendly"])
        self.assertTrue(out["has_booking_form"])
        self.assertGreaterEqual(out["cta_count"], 1)

    def test_extract_schema_org_localbusiness(self):
        from bs4 import BeautifulSoup
        scraper = WebsiteScraper()
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "LocalBusiness", "name": "Test Co", "aggregateRating": {"ratingValue": 4.5, "reviewCount": 42}}
        </script>
        </head></html>
        '''
        soup = BeautifulSoup(html, "lxml")
        schemas = scraper._extract_schema_org(soup)
        self.assertEqual(schemas["local_business"]["name"], "Test Co")

    def test_extract_phones(self):
        from bs4 import BeautifulSoup
        scraper = WebsiteScraper()
        html = '<html><body>Call us at (512) 555-1234 or 512.555.5678</body></html>'
        soup = BeautifulSoup(html, "lxml")
        phones = scraper._extract_phones(soup)
        self.assertEqual(len(phones), 2)


class TestReviewScraper(unittest.TestCase):
    """Unit tests for the ReviewScraper."""

    def test_empty_scrape_is_simulated(self):
        scraper = ReviewScraper(timeout=5)
        result = scraper.scrape("Fake Biz", website="http://localhost:59999/nope")
        self.assertTrue(result["simulated"])
        self.assertEqual(result["reviews"], [])

    def test_schema_review_extraction(self):
        from bs4 import BeautifulSoup
        scraper = ReviewScraper()
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "LocalBusiness", "aggregateRating": {"ratingValue": 4.2, "reviewCount": 10},
         "review": [{"reviewBody": "Great!", "reviewRating": {"ratingValue": 5}, "datePublished": "2024-01-01"}]}
        </script>
        </head></html>
        '''
        with patch.object(scraper.session, 'get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            result = scraper.scrape("Test", website="https://example.com")
            self.assertFalse(result["simulated"])
            self.assertEqual(result["aggregate_rating"], 4.2)
            self.assertEqual(result["review_count"], 10)
            self.assertEqual(len(result["reviews"]), 1)


class TestGBPExtractor(unittest.TestCase):
    """Unit tests for the GBPExtractor."""

    def test_extract_returns_structure(self):
        gbp = GBPExtractor(timeout=5)
        result = gbp.extract("Fake Biz", "Austin, TX", website="")
        self.assertIn("rating", result)
        self.assertIn("review_count", result)
        self.assertIn("categories", result)
        self.assertTrue(result["simulated"])

    def test_schema_from_website_parses_rating(self):
        from bs4 import BeautifulSoup
        gbp = GBPExtractor()
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "HVACBusiness", "aggregateRating": {"ratingValue": 4.8, "reviewCount": 99}}
        </script>
        </head></html>
        '''
        with patch.object(gbp.session, 'get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            schema = gbp._schema_from_website("https://example.com")
            self.assertEqual(schema["rating"], 4.8)
            self.assertEqual(schema["review_count"], 99)


class TestScoutAgentIntegration(unittest.TestCase):
    """Integration-style tests for ScoutAgent orchestration."""

    def test_enrich_composes_all_modules(self):
        scout = ScoutAgent(timeout=5)
        # Use a deliberately bad URL so modules return empty-but-structured data
        result = scout._enrich("Fake Biz", "Nowhere, NV", "http://localhost:59999/nope")
        self.assertIn("gbp", result)
        self.assertIn("website", result)
        self.assertIn("reviews", result)
        # GBP should be simulated because the URL is bad
        self.assertTrue(result["gbp"]["simulated"])

    def test_run_once_no_pending_returns_none(self):
        scout = ScoutAgent(timeout=5)
        with patch("agents.scout.claim_next_snapshot", return_value=None):
            self.assertIsNone(scout.run_once())


if __name__ == "__main__":
    unittest.main()
