"""Tests for the Builder Agent."""

import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.builder import BuilderAgent


class TestBuilderDeliverables(unittest.TestCase):
    """Tests for deliverable generation logic."""

    def setUp(self):
        self.builder = BuilderAgent()

    def test_review_replies_generated(self):
        reviews = [
            {"text": "Great service!", "rating": 5, "author": "John"},
            {"text": "Okay job", "rating": 3, "author": "Jane"},
            {"text": "Terrible", "rating": 1, "author": "Bob"},
        ]
        replies = self.builder._generate_review_replies("Test Co", reviews, "555-1234")
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]["sentiment"], "positive")
        self.assertEqual(replies[1]["sentiment"], "neutral")
        self.assertEqual(replies[2]["sentiment"], "negative")
        # The reply should contain the reviewer's name
        self.assertIn("John", replies[0]["draft_reply"])
        self.assertIn("Jane", replies[1]["draft_reply"])
        self.assertIn("555-1234", replies[2]["draft_reply"])

    def test_no_reviews_returns_empty(self):
        replies = self.builder._generate_review_replies("Test Co", [], "555-1234")
        self.assertEqual(replies, [])

    def test_infer_niche_from_categories(self):
        niche = self.builder._infer_niche({"categories": ["HVAC Contractor"]}, [])
        self.assertEqual(niche, "hvac")

    def test_infer_niche_from_gaps(self):
        niche = self.builder._infer_niche({}, ["plumbing issue"])
        self.assertEqual(niche, "plumbing")

    def test_infer_niche_default(self):
        niche = self.builder._infer_niche({}, ["some random gap"])
        self.assertEqual(niche, "home services")

    def test_infer_services(self):
        self.assertEqual(self.builder._infer_services("hvac"), "heating and cooling")
        self.assertEqual(self.builder._infer_services("plumbing"), "plumbing repair and installation")
        self.assertEqual(self.builder._infer_services("unknown"), "home repair and maintenance")


class TestBuilderIntegration(unittest.TestCase):
    """Integration tests for full deliverable generation."""

    def setUp(self):
        self.builder = BuilderAgent()

    def test_full_generation_with_all_gaps(self):
        business_info = {"name": "Ace HVAC", "location": "Austin, TX", "website": "https://acehvac.com"}
        scout_data = {
            "gbp": {
                "rating": 4.2,
                "review_count": 15,
                "categories": ["HVAC Contractor"],
                "has_booking_link": False,
            },
            "website": {
                "is_mobile_friendly": False,
                "load_time_ms": 7000,
                "has_booking_form": False,
                "cta_count": 0,
                "url": "http://acehvac.com",
                "phone_numbers": ["512-555-1234"],
            },
            "reviews": {
                "reviews": [
                    {"text": "Great service!", "rating": 5},
                ],
                "aggregate_rating": 4.2,
                "review_count": 15,
            },
        }
        insights = {
            "gaps": [
                "Website is not mobile-friendly",
                "Website loads very slowly",
                "No booking link on Google Business Profile",
                "No Calls-to-Action found on website",
                "Website missing LocalBusiness schema.org markup",
            ],
            "benchmark_comparison": {
                "trust": {"score": 60},
                "visibility": {"score": 40},
                "conversion": {"score": 20},
                "weakest_pillar": "conversion",
                "strongest_pillar": "trust",
            },
        }
        scoring = {"total_health_score": 35, "breakdown": {"trust": 24, "visibility": 12, "conversion": 6}}
        roadmap = [
            {"action": "Optimize website for mobile", "impact": "High", "difficulty": "Medium", "priority_score": 88},
            {"action": "Integrate booking link into Google Business Profile", "impact": "High", "difficulty": "Medium", "priority_score": 85},
            {"action": "Add clear Calls-to-Action", "impact": "Medium", "difficulty": "Low", "priority_score": 72},
        ]

        deliverables = self.builder._generate_deliverables(
            business_info, scout_data, insights, scoring, roadmap
        )

        self.assertEqual(deliverables["business_name"], "Ace HVAC")
        self.assertEqual(deliverables["city"], "Austin")
        self.assertGreater(deliverables["generated_count"], 0)

        # Check specific deliverable types
        types = [item["type"] for item in deliverables["items"]]
        self.assertIn("review_replies", types)
        self.assertIn("seo_meta_description", types)
        self.assertIn("gbp_description", types)
        self.assertIn("cta_copy", types)
        self.assertIn("landing_page_headlines", types)
        self.assertIn("outreach_email", types)

        # Verify outreach email content
        email_item = next(i for i in deliverables["items"] if i["type"] == "outreach_email")
        self.assertIn("Ace HVAC", email_item["content"])
        self.assertIn("Austin", email_item["content"])
        self.assertIn("35/100", email_item["content"])

        # Verify meta description
        meta_item = next(i for i in deliverables["items"] if i["type"] == "seo_meta_description")
        self.assertIn("Ace HVAC", meta_item["content"])
        self.assertIn("Austin", meta_item["content"])

    def test_generation_with_no_gaps(self):
        business_info = {"name": "Best Plumbing", "location": "Denver, CO"}
        scout_data = {"gbp": {}, "website": {}, "reviews": {}}
        insights = {"gaps": [], "benchmark_comparison": {"weakest_pillar": "trust", "strongest_pillar": "trust"}}
        scoring = {"total_health_score": 85}
        roadmap = []

        deliverables = self.builder._generate_deliverables(
            business_info, scout_data, insights, scoring, roadmap
        )

        # Should still generate at least the outreach email
        self.assertGreaterEqual(deliverables["generated_count"], 1)
        types = [item["type"] for item in deliverables["items"]]
        self.assertIn("outreach_email", types)

    def test_run_once_no_completed_returns_none(self):
        with patch("agents.builder.claim_next_snapshot", return_value=None):
            self.assertIsNone(self.builder.run_once())


if __name__ == "__main__":
    unittest.main()
