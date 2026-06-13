"""Tests for the LocalPulse AI pipeline."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import _esc, create_snapshot, list_snapshots


class TestDatabaseCore(unittest.TestCase):
    """Test core database helper functions."""

    def test_esc_handles_single_quotes(self):
        self.assertEqual(_esc("O'Brien"), "O''Brien")

    def test_esc_handles_normal_strings(self):
        self.assertEqual(_esc("hello"), "hello")


class TestSchemaValidation(unittest.TestCase):
    """Test pipeline payload schema validation."""

    def setUp(self):
        self.valid_payload = {
            "business_info": {
                "name": "Test Business",
                "location": "Austin, TX",
            }
        }

    def test_valid_payload_passes(self):
        from core.schema import validate_payload
        errors = validate_payload(self.valid_payload)
        self.assertEqual(errors, [])

    def test_missing_business_info_fails(self):
        from core.schema import validate_payload
        errors = validate_payload({})
        self.assertTrue(len(errors) > 0)


class TestAnalyzer(unittest.TestCase):
    """Test the Analyzer agent's analysis logic."""

    def setUp(self):
        from agents.analyzer import AnalyzerAgent
        self.analyzer = AnalyzerAgent()

    def test_empty_scout_data_produces_gaps(self):
        insights = self.analyzer._analyze({"gbp": {}, "website": {}, "reviews": []})
        self.assertIn("trust_score_raw", insights)
        self.assertIn("gaps", insights)
        self.assertTrue(len(insights["gaps"]) > 0)

    def test_complete_data_produces_scores(self):
        scout_data = {
            "gbp": {
                "rating": 4.5,
                "review_count": 50,
                "categories": ["HVAC Contractor", "Air Conditioning"],
                "has_booking_link": True,
                "photos_count": 20,
            },
            "website": {
                "is_mobile_friendly": True,
                "has_booking_form": True,
                "cta_count": 3,
            },
            "reviews": [
                {"text": "Great service!", "rating": 5, "date": "2024-01-15"},
                {"text": "Very professional", "rating": 4, "date": "2024-02-01"},
            ],
        }
        insights = self.analyzer._analyze(scout_data)
        self.assertGreater(insights["trust_score_raw"], 50)
        self.assertGreater(insights["visibility_score_raw"], 50)
        self.assertGreater(insights["conversion_score_raw"], 50)


class TestScorer(unittest.TestCase):
    """Test the Scoring agent's scoring algorithm."""

    def setUp(self):
        from agents.scorer import ScoringAgent
        self.scorer = ScoringAgent()

    def test_zero_insights_scores_zero(self):
        score = self.scorer._score({})
        self.assertEqual(score["total_health_score"], 0)

    def test_perfect_insights_scores_high(self):
        insights = {
            "trust_score_raw": 100,
            "visibility_score_raw": 100,
            "conversion_score_raw": 100,
        }
        score = self.scorer._score(insights)
        self.assertGreater(score["total_health_score"], 50)

    def test_breakdown_contains_all_three_categories(self):
        score = self.scorer._score({"trust_score_raw": 80, "visibility_score_raw": 60, "conversion_score_raw": 70})
        self.assertIn("visibility", score["breakdown"])
        self.assertIn("trust", score["breakdown"])
        self.assertIn("conversion", score["breakdown"])


class TestStrategist(unittest.TestCase):
    """Test the Strategist agent's roadmap generation."""

    def setUp(self):
        from agents.strategist import StrategistAgent
        self.strategist = StrategistAgent()

    def test_low_trust_generates_review_action(self):
        roadmap = self.strategist._generate_roadmap(
            business_info={"name": "Test", "location": "TX"},
            scout_data={},
            insights={"gaps": ["Low review volume"]},
            scoring={"total_health_score": 20, "breakdown": {"trust": 10, "visibility": 30, "conversion": 25}},
        )
        actions_text = str([a["action"] for a in roadmap])
        self.assertIn("review", actions_text.lower())

    def test_roadmap_is_sorted_by_priority(self):
        roadmap = self.strategist._generate_roadmap(
            business_info={"name": "Test", "location": "TX"},
            scout_data={
                "gbp": {"has_booking_link": False},
                "website": {"is_mobile_friendly": False, "has_booking_form": False, "cta_count": 0},
            },
            insights={"gaps": ["No booking link on Google Business Profile", "No recent reviews found", "No Calls-to-Action found on website"]},
            scoring={"total_health_score": 15, "breakdown": {"trust": 10, "visibility": 8, "conversion": 5}},
        )
        if len(roadmap) >= 2:
            self.assertGreaterEqual(roadmap[0]["priority_score"], roadmap[1]["priority_score"])


if __name__ == "__main__":
    unittest.main()
