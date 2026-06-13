"""Tests for the Outreach Agent."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.outreach import (
    ABTestFramework,
    HEADLINE_TEMPLATES,
    OutreachAgent,
    OUTREACH_STATUSES,
    SUBJECT_VARIANTS,
    _safe_filename,
    main,
    run_outreach_pipeline,
)


class TestABTestFramework(unittest.TestCase):
    """Test A/B test framework for subject lines."""

    def test_random_variant_selection(self):
        ab = ABTestFramework()
        self.assertIn(ab.selected, SUBJECT_VARIANTS.keys())

    def test_specific_variant_a(self):
        ab = ABTestFramework(variant="a")
        self.assertEqual(ab.selected, "a")
        subject, variant = ab.get_subject("Test Biz", "Austin")
        self.assertEqual(variant, "a")
        self.assertIn("Quick question", subject)

    def test_specific_variant_b(self):
        ab = ABTestFramework(variant="b")
        subject, variant = ab.get_subject("Test Biz", "Austin")
        self.assertIn("losing leads", subject)

    def test_specific_variant_c(self):
        ab = ABTestFramework(variant="c")
        subject, variant = ab.get_subject("Test Biz", "Austin")
        self.assertIn("ranking report", subject)

    def test_invalid_variant_defaults_to_random(self):
        ab = ABTestFramework(variant="z")
        self.assertIn(ab.selected, SUBJECT_VARIANTS.keys())

    def test_body_template_variation(self):
        ab_short = ABTestFramework(variant="c")
        self.assertIn("I just ran a Business Health Snapshot", ab_short.get_body_template())

        ab_long = ABTestFramework(variant="a")
        self.assertIn("I was looking at the local service rankings", ab_long.get_body_template())


class TestOutreachAgentGeneration(unittest.TestCase):
    """Test outreach message generation logic."""

    def setUp(self):
        self.agent = OutreachAgent(dry_run=True)

    def test_infer_niche_hvac(self):
        self.assertEqual(self.agent._infer_niche("Ace HVAC Services"), "HVAC")

    def test_infer_niche_plumbing(self):
        self.assertEqual(self.agent._infer_niche("Best Plumbing Co"), "Plumbing")

    def test_infer_niche_default(self):
        self.assertEqual(self.agent._infer_niche("Generic Business"), "Home Services")

    def test_extract_owner_name(self):
        self.assertEqual(self.agent._extract_owner_name("Anything"), "there")

    def test_pick_insight_with_matching_gap(self):
        gaps = ["Missing GBP rating data", "No booking link on Google Business Profile"]
        insight = self.agent._pick_insight(gaps, "visibility")
        self.assertIn("GBP rating data", insight)

    def test_pick_insight_fallback(self):
        gaps = ["Random gap one", "Random gap two"]
        insight = self.agent._pick_insight(gaps, "trust")
        self.assertTrue(insight.startswith("Random gap one"))

    def test_pick_insight_empty_gaps(self):
        insight = self.agent._pick_insight([], "trust")
        self.assertIn("Google Business Profile is incomplete", insight)

    def test_generate_email_returns_tuple(self):
        insights = {
            "benchmark_comparison": {
                "weakest_pillar": "trust",
                "strongest_pillar": "conversion",
            },
            "gaps": ["Low review volume"],
        }
        scoring = {"total_health_score": 25}
        subject, body = self.agent._generate_email(
            business_name="Test Biz",
            location="Austin, TX",
            insights=insights,
            scoring=scoring,
        )
        self.assertIsInstance(subject, str)
        self.assertIsInstance(body, str)
        self.assertIn("Austin", subject)
        self.assertIn("Test Biz", body)

    def test_generate_email_includes_roadmap(self):
        insights = {
            "benchmark_comparison": {
                "weakest_pillar": "trust",
                "strongest_pillar": "conversion",
            },
            "gaps": ["Low review volume"],
        }
        scoring = {"total_health_score": 25}
        roadmap = [
            {"action": "Complete Google Business Profile", "priority_score": 95},
            {"action": "Launch Review Campaign", "priority_score": 90},
        ]
        subject, body = self.agent._generate_email(
            business_name="Test Biz",
            location="Austin, TX",
            insights=insights,
            scoring=scoring,
            roadmap=roadmap,
        )
        self.assertIn("Top Priority Actions", body)
        self.assertIn("Complete Google Business Profile", body)

    def test_generate_sms(self):
        insights = {
            "benchmark_comparison": {
                "strongest_pillar": "conversion",
            },
        }
        sms = self.agent._generate_sms(
            business_name="Test Biz",
            location="Austin, TX",
            insights=insights,
            scoring={},
        )
        self.assertIn("Austin", sms)
        self.assertIn("Test Biz", sms)
        self.assertIn("Alex from LocalPulse", sms)

    def test_safe_filename(self):
        self.assertEqual(_safe_filename("O'Brien's HVAC"), "o_brien_s_hvac")


class TestOutreachAgentDryRun(unittest.TestCase):
    """Test dry-run behavior."""

    @patch("agents.outreach.list_snapshots")
    def test_dry_run_reads_without_claiming(self, mock_list):
        mock_list.return_value = [
            {
                "id": "snap-123",
                "business_name": "Test Biz",
                "location": "Austin, TX",
                "status": "ready_for_outreach",
                "data": {
                    "business_info": {"name": "Test Biz", "location": "Austin, TX"},
                    "analyzer_insights": {
                        "benchmark_comparison": {
                            "weakest_pillar": "trust",
                            "strongest_pillar": "conversion",
                        },
                        "gaps": ["Low review volume"],
                    },
                    "scoring_output": {"total_health_score": 25},
                },
            }
        ]
        agent = OutreachAgent(dry_run=True)
        result = agent.run_once()
        self.assertEqual(result, "snap-123")

    @patch("agents.outreach.claim_next_snapshot")
    def test_live_run_claims_snapshot(self, mock_claim):
        mock_claim.return_value = {
            "id": "snap-456",
            "business_name": "Live Biz",
            "location": "Denver, CO",
            "status": "ready_for_outreach",
            "data": {
                "business_info": {"name": "Live Biz", "location": "Denver, CO"},
                "analyzer_insights": {
                    "benchmark_comparison": {
                        "weakest_pillar": "visibility",
                        "strongest_pillar": "trust",
                    },
                    "gaps": ["No GBP categories set"],
                },
                "scoring_output": {"total_health_score": 15},
            },
        }
        with patch("agents.outreach.create_outreach") as mock_create, \
             patch("agents.outreach.update_snapshot_status") as mock_update:
            mock_create.return_value = "outreach-123"
            agent = OutreachAgent(dry_run=False)
            result = agent.run_once()
            self.assertEqual(result, "snap-456")
            mock_claim.assert_called_once_with("ready_for_outreach", "outreach_in_progress")
            self.assertEqual(mock_create.call_count, 2)  # email + sms
            mock_update.assert_called_once_with("snap-456", "outreach_done")


class TestOutreachPipeline(unittest.TestCase):
    """Test the batch pipeline runner."""

    @patch("agents.outreach.list_snapshots")
    def test_pipeline_processes_multiple(self, mock_list):
        mock_list.return_value = [
            {
                "id": f"snap-{i}",
                "business_name": f"Biz {i}",
                "location": "Austin, TX",
                "status": "ready_for_outreach",
                "data": {
                    "business_info": {"name": f"Biz {i}", "location": "Austin, TX"},
                    "analyzer_insights": {
                        "benchmark_comparison": {
                            "weakest_pillar": "trust",
                            "strongest_pillar": "conversion",
                        },
                        "gaps": ["Low review volume"],
                    },
                    "scoring_output": {"total_health_score": 25},
                },
            }
            for i in range(3)
        ]
        count = run_outreach_pipeline(max_iterations=5, dry_run=True)
        self.assertEqual(count, 3)

    def test_pipeline_no_work_returns_zero(self):
        with patch("agents.outreach.list_snapshots", return_value=[]):
            count = run_outreach_pipeline(max_iterations=5, dry_run=True)
            self.assertEqual(count, 0)


class TestCLI(unittest.TestCase):
    """Test CLI argument parsing and dispatch."""

    @patch("agents.outreach.run_outreach_pipeline")
    def test_cli_run(self, mock_run):
        mock_run.return_value = 2
        result = main(["run", "--batch", "5"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once_with(max_iterations=5, dry_run=False, variant=None)

    @patch("agents.outreach.run_outreach_pipeline")
    def test_cli_run_dry_run(self, mock_run):
        mock_run.return_value = 0
        result = main(["run", "--dry-run"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once_with(max_iterations=10, dry_run=True, variant=None)

    @patch("agents.outreach.run_outreach_pipeline")
    def test_cli_run_variant(self, mock_run):
        mock_run.return_value = 1
        result = main(["run", "--variant", "b"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once_with(max_iterations=10, dry_run=False, variant="b")

    @patch("agents.outreach.list_outreach")
    def test_cli_list(self, mock_list):
        mock_list.return_value = [
            {"id": "o1", "channel": "email", "status": "drafted", "subject": "Test subject"},
        ]
        result = main(["list"])
        self.assertEqual(result, 0)
        mock_list.assert_called_once_with(status=None)

    @patch("agents.outreach.list_outreach")
    def test_cli_list_with_status_filter(self, mock_list):
        mock_list.return_value = []
        result = main(["list", "--status", "sent"])
        self.assertEqual(result, 0)
        mock_list.assert_called_once_with(status="sent")

    @patch("agents.outreach.update_outreach_status")
    def test_cli_status_update(self, mock_update):
        result = main(["status", "o1", "sent"])
        self.assertEqual(result, 0)
        mock_update.assert_called_once_with("o1", "sent")

    def test_cli_no_command_prints_help(self):
        result = main([])
        self.assertEqual(result, 1)


class TestOutreachStatuses(unittest.TestCase):
    """Test valid outreach status lifecycle values."""

    def test_statuses_defined(self):
        self.assertIn("drafted", OUTREACH_STATUSES)
        self.assertIn("sent", OUTREACH_STATUSES)
        self.assertIn("opened", OUTREACH_STATUSES)
        self.assertIn("replied", OUTREACH_STATUSES)
        self.assertIn("converted", OUTREACH_STATUSES)
        self.assertIn("bounced", OUTREACH_STATUSES)


class TestHeadlineTemplates(unittest.TestCase):
    """Test lead magnet headline formatting."""

    def test_headlines_format_correctly(self):
        for tmpl in HEADLINE_TEMPLATES:
            result = tmpl.format(business_name="Test Co", city="Austin")
            self.assertIn("Test Co", result)
            self.assertIn("Austin", result)


if __name__ == "__main__":
    unittest.main()
