"""Tests for the Landing Page Flask app."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.app import app


class TestLandingPage(unittest.TestCase):
    """Tests for the landing page endpoints."""

    def setUp(self):
        self.client = app.test_client()

    def test_index_page_loads(self):
        """The root route should serve the landing page HTML."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn("LocalPulse", html)
        self.assertIn("Business Health Snapshot", html)
        self.assertIn("Request Your Free Snapshot", html)

    def test_health_endpoint(self):
        """The health check should return ok."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["status"], "ok")

    def test_request_report_missing_fields(self):
        """Missing required fields should return 400."""
        resp = self.client.post(
            "/api/request-report",
            data=json.dumps({"business_name": "Test Co"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data["success"])
        self.assertIn("Missing required fields", data["error"])

    def test_request_report_invalid_email(self):
        """Invalid email should return 400."""
        resp = self.client.post(
            "/api/request-report",
            data=json.dumps({
                "business_name": "Test Co",
                "email": "not-an-email",
                "city": "Austin",
                "state": "TX",
                "niche": "HVAC",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertFalse(data["success"])
        self.assertIn("Invalid email", data["error"])

    def test_request_report_creates_snapshot(self):
        """Valid submission should create a snapshot and return success."""
        resp = self.client.post(
            "/api/request-report",
            data=json.dumps({
                "business_name": "Test HVAC Co",
                "email": "owner@testhvac.com",
                "city": "Austin",
                "state": "TX",
                "niche": "HVAC",
                "website": "https://testhvac.com",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["success"])
        self.assertIn("snapshot_id", data)
        self.assertIn("Test HVAC Co", data["message"])

        # Verify snapshot exists via status endpoint
        snap_id = data["snapshot_id"]
        status_resp = self.client.get(f"/api/status/{snap_id}")
        self.assertEqual(status_resp.status_code, 200)
        status_data = json.loads(status_resp.data)
        self.assertTrue(status_data["success"])
        self.assertEqual(status_data["business_name"], "Test HVAC Co")
        self.assertEqual(status_data["status"], "pending")

    def test_snapshot_status_not_found(self):
        """Status endpoint for unknown snapshot should return 404."""
        resp = self.client.get("/api/status/nonexistent-id")
        self.assertEqual(resp.status_code, 404)
        data = json.loads(resp.data)
        self.assertFalse(data["success"])


if __name__ == "__main__":
    unittest.main()
