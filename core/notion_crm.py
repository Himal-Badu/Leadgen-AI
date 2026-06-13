"""Notion CRM Integration — Owner Dashboard Sync

Syncs LocalPulse AI data from the Turso DB to a structured Notion workspace.
Notion is the read-only owner dashboard; Turso remains the source of truth.

Requires environment variable:
    NOTION_TOKEN    — Notion integration token
    NOTION_PAGE_ID  — Root page ID where databases will be created

Usage:
    from core.notion_crm import NotionCRM
    crm = NotionCRM()
    crm.setup_databases()          # Create all 5 databases idempotently
    crm.sync_all()                 # Full sync from Turso to Notion
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from notion_client import Client

from core.database import list_outreach, list_snapshots

logger = logging.getLogger(__name__)

# ── Database Names ───────────────────────────────────────────────────────────
DB_LEADS = "Leads"
DB_PIPELINE = "Pipeline"
DB_OUTREACH = "Outreach"
DB_CUSTOMERS = "Customers"
DB_REVENUE = "Revenue Tracker"
ALL_DBS = [DB_LEADS, DB_PIPELINE, DB_OUTREACH, DB_CUSTOMERS, DB_REVENUE]


class NotionCRM:
    """Syncs LocalPulse data to Notion databases."""

    def __init__(
        self,
        token: Optional[str] = None,
        page_id: Optional[str] = None,
    ):
        self.token = token or os.environ.get("NOTION_TOKEN", "")
        self.page_id = page_id or os.environ.get("NOTION_PAGE_ID", "")
        if not self.token:
            raise RuntimeError(
                "NOTION_TOKEN is required. Set it as an env var or pass to constructor."
            )
        self.client = Client(auth=self.token)
        self._db_cache: dict[str, str] = {}  # name -> database_id

    # ── Database Setup ────────────────────────────────────────────────────────

    def setup_databases(self) -> dict[str, str]:
        """Create all 5 CRM databases idempotently.

        Returns a dict mapping database name to its Notion ID.
        """
        # Discover existing databases on the root page
        existing = self._discover_existing_dbs()
        self._db_cache.update(existing)

        created: dict[str, str] = {}
        for name in ALL_DBS:
            if name in self._db_cache:
                logger.info(f"Database '{name}' already exists: {self._db_cache[name]}")
                continue
            db_id = self._create_database(name)
            self._db_cache[name] = db_id
            created[name] = db_id
            logger.info(f"Created database '{name}': {db_id}")

        return self._db_cache

    def _discover_existing_dbs(self) -> dict[str, str]:
        """Find existing CRM databases on the root page."""
        found: dict[str, str] = {}
        if not self.page_id:
            return found
        try:
            children = self.client.blocks.children.list(block_id=self.page_id)
            for child in children.get("results", []):
                if child.get("type") == "child_database":
                    title = child.get("child_database", {}).get("title", "")
                    if title in ALL_DBS:
                        found[title] = child["id"]
        except Exception as e:
            logger.warning(f"Could not discover existing databases: {e}")
        return found

    def _create_database(self, name: str) -> str:
        """Create a single Notion database with appropriate schema."""
        schema = self._db_schema(name)
        payload = {
            "parent": {"page_id": self.page_id} if self.page_id else {"type": "page_id", "page_id": self.page_id},
            "title": [{"type": "text", "text": {"content": name}}],
            "properties": schema,
        }
        # Fix parent format
        payload["parent"] = {"type": "page_id", "page_id": self.page_id}

        resp = self.client.databases.create(**payload)
        return resp["id"]

    def _db_schema(self, name: str) -> dict[str, Any]:
        """Return the property schema for a given database name."""
        base = {
            "Name": {"title": {}},
        }

        if name == DB_LEADS:
            return {
                **base,
                "Business Name": {"rich_text": {}},
                "Website": {"url": {}},
                "City": {"rich_text": {}},
                "State": {"rich_text": {}},
                "Niche": {"select": {"options": []}},
                "Health Score": {"number": {"format": "number"}},
                "Source": {"select": {"options": [{"name": "Landing Page", "color": "blue"}, {"name": "Manual", "color": "gray"}, {"name": "Scout", "color": "green"}] }},
                "Status": {"select": {"options": [{"name": "pending", "color": "yellow"}, {"name": "scout_done", "color": "blue"}, {"name": "analyzer_done", "color": "purple"}, {"name": "scoring_done", "color": "orange"}, {"name": "completed", "color": "green"}, {"name": "ready_for_outreach", "color": "pink"}, {"name": "outreach_done", "color": "brown"}] }},
                "Date Discovered": {"date": {}},
                "Snapshot ID": {"rich_text": {}},
            }

        if name == DB_PIPELINE:
            return {
                **base,
                "Lead": {"relation": {"database_id": self._db_id(DB_LEADS), "single_property": {}}},
                "Status": {"select": {"options": [{"name": "pending", "color": "yellow"}, {"name": "scout_done", "color": "blue"}, {"name": "analyzer_done", "color": "purple"}, {"name": "scoring_done", "color": "orange"}, {"name": "completed", "color": "green"}, {"name": "ready_for_outreach", "color": "pink"}, {"name": "outreach_done", "color": "brown"}] }},
                "Health Score": {"number": {"format": "number"}},
                "Trust Score": {"number": {"format": "number"}},
                "Visibility Score": {"number": {"format": "number"}},
                "Conversion Score": {"number": {"format": "number"}},
                "Gaps": {"rich_text": {}},
                "Roadmap Count": {"number": {"format": "number"}},
                "Assigned Agent": {"select": {"options": [{"name": "Scout", "color": "blue"}, {"name": "Analyzer", "color": "purple"}, {"name": "Scorer", "color": "orange"}, {"name": "Strategist", "color": "green"}, {"name": "Builder", "color": "pink"}, {"name": "Outreach", "color": "brown"}] }},
                "Last Updated": {"date": {}},
                "Snapshot ID": {"rich_text": {}},
            }

        if name == DB_OUTREACH:
            return {
                **base,
                "Lead": {"relation": {"database_id": self._db_id(DB_LEADS), "single_property": {}}},
                "Channel": {"select": {"options": [{"name": "email", "color": "blue"}, {"name": "sms", "color": "green"}, {"name": "call", "color": "yellow"}] }},
                "Subject": {"rich_text": {}},
                "Body": {"rich_text": {}},
                "Status": {"select": {"options": [{"name": "drafted", "color": "gray"}, {"name": "sent", "color": "blue"}, {"name": "opened", "color": "yellow"}, {"name": "replied", "color": "green"}, {"name": "converted", "color": "purple"}, {"name": "bounced", "color": "red"}] }},
                "Sent Date": {"date": {}},
                "Opened": {"checkbox": {}},
                "Replied": {"checkbox": {}},
                "Converted": {"checkbox": {}},
                "Snapshot ID": {"rich_text": {}},
            }

        if name == DB_CUSTOMERS:
            return {
                **base,
                "Lead": {"relation": {"database_id": self._db_id(DB_LEADS), "single_property": {}}},
                "Subscription Tier": {"select": {"options": [{"name": "Starter", "color": "blue"}, {"name": "Pro", "color": "purple"}, {"name": "Autopilot", "color": "green"}] }},
                "Stripe Customer ID": {"rich_text": {}},
                "MRR": {"number": {"format": "dollar"}},
                "Start Date": {"date": {}},
                "Status": {"select": {"options": [{"name": "active", "color": "green"}, {"name": "cancelled", "color": "red"}, {"name": "paused", "color": "yellow"}] }},
                "Snapshot ID": {"rich_text": {}},
            }

        if name == DB_REVENUE:
            return {
                **base,
                "Month": {"title": {}},
                "New Customers": {"number": {"format": "number"}},
                "Churned": {"number": {"format": "number"}},
                "MRR": {"number": {"format": "dollar"}},
                "ARR": {"number": {"format": "dollar"}},
                "Top Niche": {"rich_text": {}},
                "Top City": {"rich_text": {}},
            }

        return base

    def _db_id(self, name: str) -> str:
        """Return cached database ID, or empty string if not yet created."""
        return self._db_cache.get(name, "")

    # ── Sync Operations ───────────────────────────────────────────────────────

    def sync_all(self) -> dict[str, int]:
        """Sync everything from Turso to Notion.

        Returns counts per database.
        """
        counts = {}
        counts[DB_LEADS] = self.sync_leads()
        counts[DB_PIPELINE] = self.sync_pipeline()
        counts[DB_OUTREACH] = self.sync_outreach()
        counts[DB_CUSTOMERS] = self.sync_customers()
        counts[DB_REVENUE] = self.sync_revenue()
        return counts

    def sync_leads(self) -> int:
        """Sync all snapshots as leads. Returns count synced."""
        db_id = self._db_id(DB_LEADS)
        if not db_id:
            logger.warning("Leads database not set up. Run setup_databases() first.")
            return 0

        snapshots = list_snapshots()
        synced = 0
        for snap in snapshots:
            data = snap.get("data", {}) or {}
            business_info = data.get("business_info", {})
            scoring = data.get("scoring_output", {})
            location = business_info.get("location", snap.get("location", ""))
            city, state = self._parse_location(location)

            self._upsert_page(
                db_id=db_id,
                unique_key={"property": "Snapshot ID", "rich_text": {"equals": snap["id"]}},
                properties={
                    "Name": {"title": [{"text": {"content": snap["business_name"]}}]},
                    "Business Name": {"rich_text": [{"text": {"content": snap["business_name"]}}]},
                    "Website": {"url": business_info.get("website", snap.get("website", "")) or ""},
                    "City": {"rich_text": [{"text": {"content": city}}]},
                    "State": {"rich_text": [{"text": {"content": state}}]},
                    "Niche": {"select": {"name": data.get("niche", "Other") or "Other"}},
                    "Health Score": {"number": scoring.get("total_health_score", 0) or 0},
                    "Source": {"select": {"name": "Landing Page" if data.get("requester_email") else "Manual"}},
                    "Status": {"select": {"name": snap["status"]}},
                    "Date Discovered": {"date": {"start": snap["created_at"][:10]}},
                    "Snapshot ID": {"rich_text": [{"text": {"content": snap["id"]}}]},
                },
            )
            synced += 1
        logger.info(f"Synced {synced} leads")
        return synced

    def sync_pipeline(self) -> int:
        """Sync pipeline stages from snapshots with processed data."""
        db_id = self._db_id(DB_PIPELINE)
        leads_id = self._db_id(DB_LEADS)
        if not db_id or not leads_id:
            logger.warning("Pipeline/Leads database not set up.")
            return 0

        snapshots = list_snapshots()
        synced = 0
        for snap in snapshots:
            data = snap.get("data", {}) or {}
            insights = data.get("analyzer_insights", {})
            scoring = data.get("scoring_output", {})
            roadmap = data.get("growth_roadmap", [])
            breakdown = scoring.get("breakdown", {})

            # Find linked lead page
            lead_page = self._find_page_by_snapshot(leads_id, snap["id"])
            lead_relation = []
            if lead_page:
                lead_relation = [{"id": lead_page}]

            self._upsert_page(
                db_id=db_id,
                unique_key={"property": "Snapshot ID", "rich_text": {"equals": snap["id"]}},
                properties={
                    "Name": {"title": [{"text": {"content": snap["business_name"]}}]},
                    "Lead": {"relation": lead_relation},
                    "Status": {"select": {"name": snap["status"]}},
                    "Health Score": {"number": scoring.get("total_health_score", 0) or 0},
                    "Trust Score": {"number": breakdown.get("trust", 0) or 0},
                    "Visibility Score": {"number": breakdown.get("visibility", 0) or 0},
                    "Conversion Score": {"number": breakdown.get("conversion", 0) or 0},
                    "Gaps": {"rich_text": [{"text": {"content": ", ".join(insights.get("gaps", [])[:5])}}]},
                    "Roadmap Count": {"number": len(roadmap)},
                    "Assigned Agent": {"select": {"name": self._agent_for_status(snap["status"])}},
                    "Last Updated": {"date": {"start": snap["updated_at"][:10]}},
                    "Snapshot ID": {"rich_text": [{"text": {"content": snap["id"]}}]},
                },
            )
            synced += 1
        logger.info(f"Synced {synced} pipeline entries")
        return synced

    def sync_outreach(self) -> int:
        """Sync outreach records."""
        db_id = self._db_id(DB_OUTREACH)
        leads_id = self._db_id(DB_LEADS)
        if not db_id or not leads_id:
            logger.warning("Outreach/Leads database not set up.")
            return 0

        records = list_outreach()
        synced = 0
        for rec in records:
            lead_page = self._find_page_by_snapshot(leads_id, rec["snapshot_id"])
            lead_relation = [{"id": lead_page}] if lead_page else []

            self._upsert_page(
                db_id=db_id,
                unique_key={"property": "Snapshot ID", "rich_text": {"equals": rec["id"]}},
                properties={
                    "Name": {"title": [{"text": {"content": rec.get("subject", "Outreach") or "Outreach"}}]},
                    "Lead": {"relation": lead_relation},
                    "Channel": {"select": {"name": rec["channel"]}},
                    "Subject": {"rich_text": [{"text": {"content": rec.get("subject", "")}}]},
                    "Body": {"rich_text": [{"text": {"content": rec["body"][:500]}}]},
                    "Status": {"select": {"name": rec["status"]}},
                    "Sent Date": {"date": {"start": rec["created_at"][:10]}} if rec.get("created_at") else {},
                    "Snapshot ID": {"rich_text": [{"text": {"content": rec["id"]}}]},
                },
            )
            synced += 1
        logger.info(f"Synced {synced} outreach records")
        return synced

    def sync_customers(self) -> int:
        """Sync customer records (from snapshots with subscription data)."""
        db_id = self._db_id(DB_CUSTOMERS)
        leads_id = self._db_id(DB_LEADS)
        if not db_id or not leads_id:
            logger.warning("Customers/Leads database not set up.")
            return 0

        snapshots = list_snapshots()
        synced = 0
        for snap in snapshots:
            data = snap.get("data", {}) or {}
            sub = data.get("subscription", {})
            if not sub:
                continue

            lead_page = self._find_page_by_snapshot(leads_id, snap["id"])
            lead_relation = [{"id": lead_page}] if lead_page else []

            self._upsert_page(
                db_id=db_id,
                unique_key={"property": "Snapshot ID", "rich_text": {"equals": snap["id"]}},
                properties={
                    "Name": {"title": [{"text": {"content": snap["business_name"]}}]},
                    "Lead": {"relation": lead_relation},
                    "Subscription Tier": {"select": {"name": sub.get("tier", "Starter")}},
                    "Stripe Customer ID": {"rich_text": [{"text": {"content": sub.get("stripe_customer_id", "")}}]},
                    "MRR": {"number": sub.get("mrr", 0) or 0},
                    "Start Date": {"date": {"start": sub.get("start_date", snap["created_at"][:10])}} if sub.get("start_date") or snap.get("created_at") else {},
                    "Status": {"select": {"name": sub.get("status", "active")}},
                    "Snapshot ID": {"rich_text": [{"text": {"content": snap["id"]}}]},
                },
            )
            synced += 1
        logger.info(f"Synced {synced} customers")
        return synced

    def sync_revenue(self) -> int:
        """Sync revenue tracker (aggregated from customer data)."""
        db_id = self._db_id(DB_REVENUE)
        if not db_id:
            logger.warning("Revenue database not set up.")
            return 0

        # Aggregate by month from all snapshots with subscriptions
        snapshots = list_snapshots()
        monthly: dict[str, dict[str, Any]] = {}
        for snap in snapshots:
            data = snap.get("data", {}) or {}
            sub = data.get("subscription", {})
            if not sub:
                continue
            month = sub.get("start_date", snap["created_at"][:7])[:7]  # YYYY-MM
            if month not in monthly:
                monthly[month] = {
                    "new": 0,
                    "churned": 0,
                    "mrr": 0,
                    "niches": {},
                    "cities": {},
                }
            monthly[month]["new"] += 1
            monthly[month]["mrr"] += sub.get("mrr", 0) or 0
            if sub.get("status") == "cancelled":
                monthly[month]["churned"] += 1

            # Track top niche/city
            niche = data.get("niche", "Other")
            location = data.get("business_info", {}).get("location", snap.get("location", ""))
            city, _ = self._parse_location(location)
            monthly[month]["niches"][niche] = monthly[month]["niches"].get(niche, 0) + 1
            monthly[month]["cities"][city] = monthly[month]["cities"].get(city, 0) + 1

        synced = 0
        for month, agg in monthly.items():
            top_niche = max(agg["niches"], key=agg["niches"].get) if agg["niches"] else ""
            top_city = max(agg["cities"], key=agg["cities"].get) if agg["cities"] else ""
            arr = agg["mrr"] * 12

            self._upsert_page(
                db_id=db_id,
                unique_key={"property": "Month", "title": {"equals": month}},
                properties={
                    "Month": {"title": [{"text": {"content": month}}]},
                    "New Customers": {"number": agg["new"]},
                    "Churned": {"number": agg["churned"]},
                    "MRR": {"number": agg["mrr"]},
                    "ARR": {"number": arr},
                    "Top Niche": {"rich_text": [{"text": {"content": top_niche}}]},
                    "Top City": {"rich_text": [{"text": {"content": top_city}}]},
                },
            )
            synced += 1
        logger.info(f"Synced {synced} revenue entries")
        return synced

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _upsert_page(
        self,
        db_id: str,
        unique_key: dict[str, Any],
        properties: dict[str, Any],
    ) -> str:
        """Upsert a page in a database: update if exists, create if not."""
        existing = self._query_page(db_id, unique_key)
        if existing:
            # Update
            page_id = existing["id"]
            # Remove empty relation if no target
            clean_props = {k: v for k, v in properties.items() if v}
            self.client.pages.update(page_id=page_id, properties=clean_props)
            return page_id
        else:
            # Create
            resp = self.client.pages.create(
                parent={"database_id": db_id},
                properties=properties,
            )
            return resp["id"]

    def _query_page(self, db_id: str, filter_dict: dict[str, Any]) -> Optional[dict]:
        """Query a database for a single page matching the filter."""
        try:
            results = self.client.databases.query(
                database_id=db_id,
                filter=filter_dict,
                page_size=1,
            )
            items = results.get("results", [])
            return items[0] if items else None
        except Exception as e:
            logger.warning(f"Query failed: {e}")
            return None

    def _find_page_by_snapshot(self, db_id: str, snapshot_id: str) -> Optional[str]:
        """Find a page in a database by its Snapshot ID. Returns page ID or None."""
        page = self._query_page(
            db_id,
            {"property": "Snapshot ID", "rich_text": {"equals": snapshot_id}},
        )
        return page["id"] if page else None

    @staticmethod
    def _parse_location(location: str) -> tuple[str, str]:
        """Split 'City, ST' into (city, state)."""
        if "," in location:
            parts = location.split(",", 1)
            return parts[0].strip(), parts[1].strip()
        return location.strip(), ""

    @staticmethod
    def _agent_for_status(status: str) -> str:
        """Map pipeline status to assigned agent."""
        mapping = {
            "pending": "Scout",
            "scout_done": "Analyzer",
            "analyzer_done": "Scorer",
            "scoring_done": "Strategist",
            "completed": "Builder",
            "ready_for_outreach": "Outreach",
            "outreach_done": "Outreach",
        }
        return mapping.get(status, "Scout")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LocalPulse AI Notion CRM Sync")
    parser.add_argument("--setup", action="store_true", help="Create databases")
    parser.add_argument("--sync", action="store_true", help="Run full sync")
    parser.add_argument("--sync-leads", action="store_true", help="Sync leads only")
    parser.add_argument("--sync-pipeline", action="store_true", help="Sync pipeline only")
    parser.add_argument("--sync-outreach", action="store_true", help="Sync outreach only")
    parser.add_argument("--dry-run", action="store_true", help="List what would be synced")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    crm = NotionCRM()

    if args.setup:
        db_map = crm.setup_databases()
        print("Databases:")
        for name, db_id in db_map.items():
            print(f"  {name}: {db_id}")

    if args.dry_run:
        snapshots = list_snapshots()
        print(f"Would sync {len(snapshots)} snapshots")
        outreach = list_outreach()
        print(f"Would sync {len(outreach)} outreach records")
        return

    if args.sync:
        counts = crm.sync_all()
        print("Sync complete:")
        for name, count in counts.items():
            print(f"  {name}: {count}")

    if args.sync_leads:
        print(f"Synced leads: {crm.sync_leads()}")
    if args.sync_pipeline:
        print(f"Synced pipeline: {crm.sync_pipeline()}")
    if args.sync_outreach:
        print(f"Synced outreach: {crm.sync_outreach()}")


if __name__ == "__main__":
    main()
