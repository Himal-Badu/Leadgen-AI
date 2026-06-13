"""Tests for the Analyzer Agent."""

import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.analyzer import AnalyzerAgent, Benchmarks


class TestAnalyzerTrust(unittest.TestCase):
    """Tests for trust analysis."""

    def setUp(self):
        self.analyzer = AnalyzerAgent()

    def test_excellent_rating(self):
        result = self.analyzer._analyze_trust(
            {"rating": 4.8, "review_count": 120},
            [],
        )
        # (4.8/5)*40 + min(120/100,1)*30 + 0 + 0 = 38.4 + 30 = 68.4
        self.assertGreater(result["score"], 65)
        self.assertEqual(result["details"]["rating_status"], "excellent")

    def test_low_rating_gap(self):
        result = self.analyzer._analyze_trust(
            {"rating": 3.5, "review_count": 5},
            [],
        )
        self.assertLess(result["score"], 60)
        gaps_text = " ".join(result["gaps"]).lower()
        self.assertIn("low average rating", gaps_text)
        self.assertIn("low review volume", gaps_text)

    def test_missing_rating_and_reviews(self):
        result = self.analyzer._analyze_trust({}, [])
        self.assertEqual(result["score"], 0)
        self.assertTrue(len(result["gaps"]) >= 2)

    def test_recent_reviews_boost_score(self):
        recent = [
            {"text": "Great!", "rating": 5, "date": datetime.now(timezone.utc).isoformat()},
            {"text": "Good", "rating": 4, "date": datetime.now(timezone.utc).isoformat()},
        ]
        result = self.analyzer._analyze_trust(
            {"rating": 4.5, "review_count": 50},
            recent,
        )
        self.assertGreater(result["score"], 50)
        self.assertEqual(result["details"]["recent_reviews"], 2)


class TestAnalyzerVisibility(unittest.TestCase):
    """Tests for visibility analysis."""

    def setUp(self):
        self.analyzer = AnalyzerAgent()

    def test_complete_gbp_high_score(self):
        result = self.analyzer._analyze_visibility(
            {
                "rating": 4.5,
                "review_count": 100,
                "categories": ["HVAC Contractor", "Air Conditioning", "Heating"],
                "has_booking_link": True,
                "photos_count": 60,
            },
            {"schema_org": {"local_business": {}}, "addresses": ["123 Main St"], "phone_numbers": ["555-1234"]},
        )
        self.assertGreater(result["score"], 70)
        self.assertEqual(result["details"]["gbp_completeness"]["fields_present"], 5)

    def test_incomplete_gbp_gaps(self):
        result = self.analyzer._analyze_visibility(
            {"categories": [], "has_booking_link": False},
            {"schema_org": {}, "addresses": [], "phone_numbers": []},
        )
        self.assertLess(result["score"], 50)
        gaps_text = " ".join(result["gaps"]).lower()
        self.assertIn("incomplete google business profile", gaps_text)
        self.assertIn("no gbp categories", gaps_text)

    def test_local_seo_from_website(self):
        result = self.analyzer._analyze_visibility(
            {"rating": 4.0, "review_count": 20, "categories": ["Plumber"], "has_booking_link": True, "photos_count": 15},
            {
                "schema_org": {"local_business": {"name": "Test"}},
                "addresses": ["Austin, TX"],
                "phone_numbers": ["512-555-1234"],
            },
        )
        self.assertGreaterEqual(result["details"]["local_seo_score"], 5)


class TestAnalyzerConversion(unittest.TestCase):
    """Tests for conversion analysis."""

    def setUp(self):
        self.analyzer = AnalyzerAgent()

    def test_perfect_website(self):
        result = self.analyzer._analyze_conversion({
            "is_mobile_friendly": True,
            "load_time_ms": 1500,
            "has_booking_form": True,
            "cta_count": 5,
            "url": "https://example.com",
        })
        self.assertGreater(result["score"], 85)
        self.assertEqual(result["details"]["load_status"], "excellent")
        self.assertEqual(result["details"]["mobile_status"], "pass")

    def test_slow_mobile_site_gaps(self):
        result = self.analyzer._analyze_conversion({
            "is_mobile_friendly": False,
            "load_time_ms": 7000,
            "has_booking_form": False,
            "cta_count": 0,
            "url": "http://example.com",
        })
        self.assertLess(result["score"], 40)
        gaps_text = " ".join(result["gaps"]).lower()
        self.assertIn("mobile", gaps_text)
        self.assertIn("load", gaps_text)
        self.assertIn("scheduling", gaps_text)
        self.assertIn("https", gaps_text)

    def test_load_time_thresholds(self):
        thresholds = [
            (1500, "excellent"),
            (3500, "good"),
            (5000, "slow"),
            (8000, "very_slow"),
        ]
        for load_time, expected_status in thresholds:
            result = self.analyzer._analyze_conversion({
                "is_mobile_friendly": True,
                "load_time_ms": load_time,
                "has_booking_form": True,
                "cta_count": 3,
                "url": "https://example.com",
            })
            self.assertEqual(result["details"]["load_status"], expected_status)


class TestAnalyzerSentiment(unittest.TestCase):
    """Tests for sentiment analysis."""

    def setUp(self):
        self.analyzer = AnalyzerAgent()

    def test_no_reviews(self):
        result = self.analyzer._analyze_sentiment([])
        self.assertEqual(result["overall"], "No reviews available for sentiment analysis")

    def test_positive_reviews(self):
        reviews = [
            {"text": "Great service, very professional!", "rating": 5},
            {"text": "Amazing work, highly recommend!", "rating": 5},
        ]
        result = self.analyzer._analyze_sentiment(reviews)
        self.assertEqual(result["overall"], "Positive")
        self.assertGreater(result["polarity"], 0)

    def test_negative_reviews(self):
        reviews = [
            {"text": "Terrible service, rude staff", "rating": 1},
            {"text": "Worst experience ever", "rating": 1},
        ]
        result = self.analyzer._analyze_sentiment(reviews)
        self.assertEqual(result["overall"], "Negative")
        self.assertLess(result["polarity"], 0)

    def test_mixed_reviews(self):
        reviews = [
            {"text": "Great service", "rating": 5},
            {"text": "Terrible experience", "rating": 1},
        ]
        result = self.analyzer._analyze_sentiment(reviews)
        self.assertEqual(result["overall"], "Mixed")

    def test_theme_extraction(self):
        texts = ["Very professional and clean work", "Rude and expensive"]
        themes = self.analyzer._extract_themes(texts)
        self.assertEqual(len(themes), 2)
        theme_types = [t["type"] for t in themes]
        self.assertIn("positive", theme_types)
        self.assertIn("negative", theme_types)


class TestAnalyzerBenchmarks(unittest.TestCase):
    """Tests for benchmark comparison."""

    def setUp(self):
        self.analyzer = AnalyzerAgent()

    def test_excellent_scores(self):
        result = self.analyzer._benchmark_comparison(85, 90, 88)
        self.assertEqual(result["trust"]["status"], "excellent")
        self.assertEqual(result["visibility"]["status"], "excellent")
        self.assertEqual(result["conversion"]["status"], "excellent")

    def test_critical_scores(self):
        result = self.analyzer._benchmark_comparison(15, 10, 5)
        self.assertEqual(result["trust"]["status"], "critical")
        self.assertEqual(result["conversion"]["status"], "critical")
        self.assertEqual(result["weakest_pillar"], "conversion")

    def test_mixed_scores(self):
        result = self.analyzer._benchmark_comparison(75, 45, 30)
        self.assertEqual(result["trust"]["status"], "good")
        self.assertEqual(result["visibility"]["status"], "average")
        self.assertEqual(result["conversion"]["status"], "below_average")
        self.assertEqual(result["strongest_pillar"], "trust")
        self.assertEqual(result["weakest_pillar"], "conversion")


class TestAnalyzerIntegration(unittest.TestCase):
    """Integration tests for the full analyzer."""

    def setUp(self):
        self.analyzer = AnalyzerAgent()

    def test_empty_scout_data_produces_gaps(self):
        insights = self.analyzer._analyze({"gbp": {}, "website": {}, "reviews": []})
        self.assertIn("trust_score_raw", insights)
        self.assertIn("gaps", insights)
        self.assertTrue(len(insights["gaps"]) > 0)
        self.assertIn("benchmark_comparison", insights)

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
                "load_time_ms": 2000,
                "url": "https://example.com",
                "schema_org": {"local_business": {}},
                "addresses": ["Austin, TX"],
                "phone_numbers": ["512-555-1234"],
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
        self.assertEqual(insights["sentiment_summary"]["overall"], "Positive")
        self.assertIn("trust_details", insights)
        self.assertIn("visibility_details", insights)
        self.assertIn("conversion_details", insights)

    def test_reviews_dict_format(self):
        """Test that analyzer handles the new reviews dict format from scout."""
        scout_data = {
            "gbp": {"rating": 4.0, "review_count": 10},
            "website": {"is_mobile_friendly": True, "has_booking_form": False, "cta_count": 0, "url": "https://example.com"},
            "reviews": {
                "reviews": [
                    {"text": "Okay service", "rating": 3, "date": "2024-01-01"},
                ],
                "aggregate_rating": 3.5,
                "review_count": 10,
                "simulated": False,
            },
        }
        insights = self.analyzer._analyze(scout_data)
        self.assertIn("trust_score_raw", insights)
        self.assertIn("gaps", insights)


if __name__ == "__main__":
    unittest.main()
