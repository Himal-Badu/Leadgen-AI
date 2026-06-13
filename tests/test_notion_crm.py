"""Tests for the Notion CRM module.

All Notion API calls are mocked so tests run without a real token.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.notion_crm import (
    ALL_DBS,
    DB_CUSTOMERS,
    DB_LEADS,
    DB_OUTREACH,
    DB_PIPELINE,
    DB_REVENUE,
    NotionCRM,
)


class TestNotionCRMInit(unittest.TestCase):
    def test_requires_token(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                NotionCRM()
            self.assertIn("NOTION_TOKEN", str(ctx.exception))

    def test_accepts_token_from_env(self):
        with patch.dict("os.environ", {"NOTION_TOKEN": "test-token", "NOTION_PAGE_ID": "page-123"}):
            crm = NotionCRM()
            self.assertEqual(crm.token, "test-token")
            self.assertEqual(crm.page_id, "page-123")

    def test_accepts_token_from_constructor(self):
        crm = NotionCRM(token=" ctor-token", page_id="page-456")
        self.assertEqual(crm.token, " ctor-token")
        self.assertEqual(crm.page_id, "page-456")


class TestDatabaseSetup(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake-token", page_id="root-page")
        # Mock the underlying client
        self.crm.client = MagicMock()

    def test_setup_creates_all_databases(self):
        self.crm.client.blocks.children.list.return_value = {"results": []}
        self.crm.client.databases.create.side_effect = [
            {"id": f"db-{i}"} for i in range(len(ALL_DBS))
        ]

        result = self.crm.setup_databases()

        self.assertEqual(len(result), len(ALL_DBS))
        self.assertEqual(self.crm.client.databases.create.call_count, len(ALL_DBS))
        for name in ALL_DBS:
            self.assertIn(name, result)

    def test_setup_is_idempotent(self):
        """Running setup twice should not create duplicates."""
        # Pretend all DBs already exist
        self.crm.client.blocks.children.list.return_value = {
            "results": [
                {"id": f"db-{name}", "type": "child_database", "child_database": {"title": name}}
                for name in ALL_DBS
            ]
        }

        result = self.crm.setup_databases()

        self.assertEqual(len(result), len(ALL_DBS))
        self.crm.client.databases.create.assert_not_called()

    def test_leads_schema_has_expected_properties(self):
        schema = self.crm._db_schema(DB_LEADS)
        self.assertIn("Name", schema)
        self.assertIn("Business Name", schema)
        self.assertIn("City", schema)
        self.assertIn("Niche", schema)
        self.assertIn("Health Score", schema)
        self.assertIn("Status", schema)
        self.assertIn("Snapshot ID", schema)

    def test_pipeline_schema_has_relation_to_leads(self):
        self.crm._db_cache[DB_LEADS] = "db-leads"
        schema = self.crm._db_schema(DB_PIPELINE)
        self.assertIn("Lead", schema)
        self.assertEqual(schema["Lead"]["relation"]["database_id"], "db-leads")
        self.assertIn("Trust Score", schema)
        self.assertIn("Visibility Score", schema)
        self.assertIn("Conversion Score", schema)

    def test_outreach_schema_has_relation_to_leads(self):
        self.crm._db_cache[DB_LEADS] = "db-leads"
        schema = self.crm._db_schema(DB_OUTREACH)
        self.assertIn("Lead", schema)
        self.assertIn("Channel", schema)
        self.assertIn("Subject", schema)
        self.assertIn("Body", schema)

    def test_customers_schema_has_subscription_fields(self):
        self.crm._db_cache[DB_LEADS] = "db-leads"
        schema = self.crm._db_schema(DB_CUSTOMERS)
        self.assertIn("Subscription Tier", schema)
        self.assertIn("Stripe Customer ID", schema)
        self.assertIn("MRR", schema)
        self.assertIn("Status", schema)

    def test_revenue_schema_has_aggregation_fields(self):
        schema = self.crm._db_schema(DB_REVENUE)
        self.assertIn("Month", schema)
        self.assertIn("New Customers", schema)
        self.assertIn("Churned", schema)
        self.assertIn("MRR", schema)
        self.assertIn("ARR", schema)


class TestSyncLeads(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake", page_id="root")
        self.crm.client = MagicMock()
        self.crm._db_cache[DB_LEADS] = "db-leads"

    @patch("core.notion_crm.list_snapshots")
    def test_sync_leads_creates_pages(self, mock_list):
        mock_list.return_value = [
            {
                "id": "snap-1",
                "business_name": "Ace HVAC",
                "location": "Austin, TX",
                "website": "https://ace.com",
                "status": "pending",
                "created_at": "2024-01-15T10:00:00Z",
                "data": {
                    "business_info": {"name": "Ace HVAC", "website": "https://ace.com"},
                    "niche": "HVAC",
                    "scoring_output": {"total_health_score": 65},
                },
            }
        ]
        self.crm.client.databases.query.return_value = {"results": []}
        self.crm.client.pages.create.return_value = {"id": "page-1"}

        count = self.crm.sync_leads()

        self.assertEqual(count, 1)
        self.crm.client.pages.create.assert_called_once()
        props = self.crm.client.pages.create.call_args[1]["properties"]
        self.assertEqual(props["Business Name"]["rich_text"][0]["text"]["content"], "Ace HVAC")
        self.assertEqual(props["City"]["rich_text"][0]["text"]["content"], "Austin")
        self.assertEqual(props["State"]["rich_text"][0]["text"]["content"], "TX")
        self.assertEqual(props["Health Score"]["number"], 65)

    @patch("core.notion_crm.list_snapshots")
    def test_sync_leads_updates_existing(self, mock_list):
        mock_list.return_value = [
            {
                "id": "snap-1",
                "business_name": "Ace HVAC",
                "location": "Austin, TX",
                "website": "",
                "status": "scout_done",
                "created_at": "2024-01-15T10:00:00Z",
                "data": {},
            }
        ]
        self.crm.client.databases.query.return_value = {
            "results": [{"id": "existing-page"}]
        }

        count = self.crm.sync_leads()

        self.assertEqual(count, 1)
        self.crm.client.pages.update.assert_called_once_with(
            page_id="existing-page", properties=unittest.mock.ANY
        )

    @patch("core.notion_crm.list_snapshots")
    def test_sync_leads_no_database_warns(self, mock_list):
        self.crm._db_cache = {}
        count = self.crm.sync_leads()
        self.assertEqual(count, 0)


class TestSyncPipeline(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake", page_id="root")
        self.crm.client = MagicMock()
        self.crm._db_cache[DB_LEADS] = "db-leads"
        self.crm._db_cache[DB_PIPELINE] = "db-pipe"

    @patch("core.notion_crm.list_snapshots")
    def test_sync_pipeline_with_scoring(self, mock_list):
        mock_list.return_value = [
            {
                "id": "snap-2",
                "business_name": "Best Plumbing",
                "location": "Denver, CO",
                "status": "scoring_done",
                "updated_at": "2024-01-16T12:00:00Z",
                "data": {
                    "analyzer_insights": {"gaps": ["Slow website", "No reviews"]},
                    "scoring_output": {
                        "total_health_score": 45,
                        "breakdown": {"trust": 30, "visibility": 50, "conversion": 20},
                    },
                    "growth_roadmap": [{"action": "Fix mobile"}, {"action": "Get reviews"}],
                },
            }
        ]
        self.crm.client.databases.query.side_effect = [
            {"results": [{"id": "lead-page-2"}]},  # find lead
            {"results": []},  # pipeline query
        ]
        self.crm.client.pages.create.return_value = {"id": "pipe-page"}

        count = self.crm.sync_pipeline()

        self.assertEqual(count, 1)
        props = self.crm.client.pages.create.call_args[1]["properties"]
        self.assertEqual(props["Health Score"]["number"], 45)
        self.assertEqual(props["Trust Score"]["number"], 30)
        self.assertEqual(props["Visibility Score"]["number"], 50)
        self.assertEqual(props["Conversion Score"]["number"], 20)
        self.assertEqual(props["Roadmap Count"]["number"], 2)


class TestSyncOutreach(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake", page_id="root")
        self.crm.client = MagicMock()
        self.crm._db_cache[DB_LEADS] = "db-leads"
        self.crm._db_cache[DB_OUTREACH] = "db-out"

    @patch("core.notion_crm.list_outreach")
    def test_sync_outreach_records(self, mock_list):
        mock_list.return_value = [
            {
                "id": "out-1",
                "snapshot_id": "snap-1",
                "channel": "email",
                "status": "drafted",
                "subject": "Quick question",
                "body": "Hi there...",
                "created_at": "2024-01-17T09:00:00Z",
            }
        ]
        self.crm.client.databases.query.side_effect = [
            {"results": [{"id": "lead-page-1"}]},  # find lead
            {"results": []},  # outreach query
        ]
        self.crm.client.pages.create.return_value = {"id": "out-page"}

        count = self.crm.sync_outreach()

        self.assertEqual(count, 1)
        props = self.crm.client.pages.create.call_args[1]["properties"]
        self.assertEqual(props["Channel"]["select"]["name"], "email")
        self.assertEqual(props["Status"]["select"]["name"], "drafted")


class TestSyncCustomers(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake", page_id="root")
        self.crm.client = MagicMock()
        self.crm._db_cache[DB_LEADS] = "db-leads"
        self.crm._db_cache[DB_CUSTOMERS] = "db-cust"

    @patch("core.notion_crm.list_snapshots")
    def test_sync_customers_with_subscriptions(self, mock_list):
        mock_list.return_value = [
            {
                "id": "snap-3",
                "business_name": "Pro Roofing",
                "location": "Miami, FL",
                "status": "ready_for_outreach",
                "created_at": "2024-01-10T08:00:00Z",
                "data": {
                    "subscription": {
                        "tier": "Pro",
                        "stripe_customer_id": "cus_abc123",
                        "mrr": 79,
                        "status": "active",
                        "start_date": "2024-01-10",
                    }
                },
            },
            {
                "id": "snap-4",
                "business_name": "No Sub Co",
                "location": "Phoenix, AZ",
                "status": "pending",
                "created_at": "2024-01-11T08:00:00Z",
                "data": {},
            },
        ]
        self.crm.client.databases.query.side_effect = [
            {"results": [{"id": "lead-page-3"}]},  # find lead for snap-3
            {"results": []},  # customer query
        ]
        self.crm.client.pages.create.return_value = {"id": "cust-page"}

        count = self.crm.sync_customers()

        self.assertEqual(count, 1)  # Only snap-3 has subscription
        props = self.crm.client.pages.create.call_args[1]["properties"]
        self.assertEqual(props["Subscription Tier"]["select"]["name"], "Pro")
        self.assertEqual(props["MRR"]["number"], 79)
        self.assertEqual(props["Stripe Customer ID"]["rich_text"][0]["text"]["content"], "cus_abc123")


class TestSyncRevenue(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake", page_id="root")
        self.crm.client = MagicMock()
        self.crm._db_cache[DB_REVENUE] = "db-rev"

    @patch("core.notion_crm.list_snapshots")
    def test_sync_revenue_aggregates_by_month(self, mock_list):
        mock_list.return_value = [
            {
                "id": "snap-5",
                "business_name": "A",
                "location": "Dallas, TX",
                "created_at": "2024-01-01T00:00:00Z",
                "data": {
                    "niche": "HVAC",
                    "subscription": {"tier": "Starter", "mrr": 29, "status": "active", "start_date": "2024-01-05"},
                },
            },
            {
                "id": "snap-6",
                "business_name": "B",
                "location": "Dallas, TX",
                "created_at": "2024-01-02T00:00:00Z",
                "data": {
                    "niche": "HVAC",
                    "subscription": {"tier": "Pro", "mrr": 79, "status": "active", "start_date": "2024-01-10"},
                },
            },
            {
                "id": "snap-7",
                "business_name": "C",
                "location": "Houston, TX",
                "created_at": "2024-02-01T00:00:00Z",
                "data": {
                    "niche": "Plumbing",
                    "subscription": {"tier": "Starter", "mrr": 29, "status": "cancelled", "start_date": "2024-02-01"},
                },
            },
        ]
        self.crm.client.databases.query.return_value = {"results": []}
        self.crm.client.pages.create.return_value = {"id": "rev-page"}

        count = self.crm.sync_revenue()

        self.assertEqual(count, 2)  # Jan and Feb
        calls = self.crm.client.pages.create.call_args_list
        # Jan: 2 new customers, $108 MRR, HVAC top niche, Dallas top city
        jan_props = calls[0][1]["properties"]
        self.assertEqual(jan_props["New Customers"]["number"], 2)
        self.assertEqual(jan_props["MRR"]["number"], 108)
        self.assertEqual(jan_props["ARR"]["number"], 1296)
        self.assertEqual(jan_props["Top Niche"]["rich_text"][0]["text"]["content"], "HVAC")
        self.assertEqual(jan_props["Top City"]["rich_text"][0]["text"]["content"], "Dallas")

        # Feb: 1 new, 1 churned, $29 MRR
        feb_props = calls[1][1]["properties"]
        self.assertEqual(feb_props["New Customers"]["number"], 1)
        self.assertEqual(feb_props["Churned"]["number"], 1)
        self.assertEqual(feb_props["Top Niche"]["rich_text"][0]["text"]["content"], "Plumbing")


class TestHelpers(unittest.TestCase):
    def test_parse_location(self):
        self.assertEqual(NotionCRM._parse_location("Austin, TX"), ("Austin", "TX"))
        self.assertEqual(NotionCRM._parse_location("New York, NY"), ("New York", "NY"))
        self.assertEqual(NotionCRM._parse_location("London"), ("London", ""))

    def test_agent_for_status(self):
        self.assertEqual(NotionCRM._agent_for_status("pending"), "Scout")
        self.assertEqual(NotionCRM._agent_for_status("analyzer_done"), "Scorer")
        self.assertEqual(NotionCRM._agent_for_status("ready_for_outreach"), "Outreach")
        self.assertEqual(NotionCRM._agent_for_status("unknown"), "Scout")


class TestUpsertLogic(unittest.TestCase):
    def setUp(self):
        self.crm = NotionCRM(token="fake", page_id="root")
        self.crm.client = MagicMock()

    def test_upsert_creates_when_not_found(self):
        self.crm.client.databases.query.return_value = {"results": []}
        self.crm.client.pages.create.return_value = {"id": "new-page"}

        page_id = self.crm._upsert_page(
            db_id="db-1",
            unique_key={"property": "Snapshot ID", "rich_text": {"equals": "snap-x"}},
            properties={"Name": {"title": [{"text": {"content": "Test"}}]}},
        )

        self.assertEqual(page_id, "new-page")
        self.crm.client.pages.create.assert_called_once()
        self.crm.client.pages.update.assert_not_called()

    def test_upsert_updates_when_found(self):
        self.crm.client.databases.query.return_value = {"results": [{"id": "old-page"}]}

        page_id = self.crm._upsert_page(
            db_id="db-1",
            unique_key={"property": "Snapshot ID", "rich_text": {"equals": "snap-x"}},
            properties={"Name": {"title": [{"text": {"content": "Test"}}]}},
        )

        self.assertEqual(page_id, "old-page")
        self.crm.client.pages.update.assert_called_once()
        self.crm.client.pages.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
