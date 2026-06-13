"""Outreach Agent — Lead Engagement

Responsibility: Convert completed Business Health Snapshots into personalized
outreach sequences (email + SMS) using the Insight-First approach.

Features:
  - Poll for snapshots with status 'ready_for_outreach'
  - Generate personalized email using specific gaps from the snapshot
  - Generate SMS follow-up
  - A/B test framework for subject lines and hooks
  - Save outreach records to the database with status tracking
  - Log drafted messages to /home/team/shared/outreach_logs/ for owner review
  - CLI with batch, dry-run, and list modes
"""
import argparse
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.database import (
    claim_next_snapshot,
    create_outreach,
    get_snapshot,
    list_outreach,
    list_snapshots,
    update_outreach_status,
    update_snapshot_status,
)
from core.email_service import send_snapshot_report

logger = logging.getLogger(__name__)

# Default logs directory
LOGS_DIR = Path("/home/team/shared/outreach_logs")

# ─── A/B Test Subject Line Variants ───────────────────────────────────────────
SUBJECT_VARIANTS = {
    "a": "Quick question about your visibility in {city}",
    "b": "{business_name} is losing leads in {city} — here's the data",
    "c": "Your {city} ranking report: 3 gaps \u0026 3 fixes",
}

# ─── Email Body Templates ─────────────────────────────────────────────────────
EMAIL_TEMPLATE = """Hi {owner_name},

I was looking at the local service rankings for {niche} in {city} today and noticed {business_name} is currently sitting on the verge of the "Google Map Pack" for several high-volume keywords.

I ran a quick Business Health Snapshot for you and identified three specific gaps that are likely leaking leads to your competitors.

Key Findings:
- Your {strongest_pillar} is the strongest area, but your {weakest_pillar} signals are currently critical.
- Specifically, {specific_insight}
- Your overall Health Score is {health_score}/100 — placing you in the {percentile}.

I've put together a 1-page roadmap of how to fix these 3 items. Would you be open to a 10-minute "no-pitch" call later this week to walk through the data?

Best,

Alex
LocalPulse AI
"""

EMAIL_TEMPLATE_SHORT = """Hi {owner_name},

I just ran a Business Health Snapshot for {business_name} in {city}. 

The headline: your {weakest_pillar} score is critically low ({health_score}/100 overall), and you're likely losing {city} leads to competitors every day.

Top gap: {specific_insight}

I have a 1-page fix-it roadmap. Worth a 10-minute no-pitch call this week?

Alex
LocalPulse AI
"""

SMS_TEMPLATE = (
    "Hi {owner_name}, this is Alex from LocalPulse. I just emailed you a Health Snapshot for "
    "{business_name}. You're actually outperforming most of {city} on {strongest_pillar}, "
    "but there's a small technical fix on your Google profile that could boost your calls by 20%. "
    "Do you have 5 mins to chat tomorrow?"
)

HEADLINE_TEMPLATES = [
    '"{business_name} Health Snapshot: 3 Gaps \u0026 3 Fixes in {city}."',
    '"Local Ranking Report: {business_name} vs. the competition in {city}."',
]

# Valid outreach statuses for lifecycle tracking
OUTREACH_STATUSES = ["drafted", "sent", "opened", "replied", "converted", "bounced"]


class ABTestFramework:
    """Simple A/B test framework for subject lines and email hooks."""

    def __init__(self, variant: Optional[str] = None):
        """Initialize with a specific variant or random selection."""
        self.variants = list(SUBJECT_VARIANTS.keys())
        self.selected = variant if variant in self.variants else random.choice(self.variants)

    def get_subject(self, business_name: str, city: str) -> tuple[str, str]:
        """Return (subject_line, variant_key) for the selected variant."""
        template = SUBJECT_VARIANTS[self.selected]
        return template.format(business_name=business_name, city=city), self.selected

    def get_body_template(self) -> str:
        """Return the email body template. Variant 'c' uses the shorter hook."""
        if self.selected == "c":
            return EMAIL_TEMPLATE_SHORT
        return EMAIL_TEMPLATE


class OutreachAgent:
    """Outreach agent generates personalized email and SMS sequences."""

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        ab_variant: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.logs_dir = logs_dir or LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.ab = ABTestFramework(variant=ab_variant)
        self.dry_run = dry_run
        self._dry_run_seen: set[str] = set()

    def run_once(self) -> Optional[str]:
        """Poll for a ready_for_outreach snapshot and generate outreach.

        Returns the processed snapshot ID or None if no work.
        """
        if self.dry_run:
            # In dry-run, iterate through snapshots without claiming
            snapshots = list_snapshots(status="ready_for_outreach")
            if not snapshots:
                return None
            # Find first unseen snapshot
            for snap in snapshots:
                if snap["id"] not in self._dry_run_seen:
                    snapshot = snap
                    break
            else:
                return None
            self._dry_run_seen.add(snapshot["id"])
        else:
            snapshot = claim_next_snapshot("ready_for_outreach", "outreach_in_progress")
            if snapshot is None:
                logger.debug("No ready_for_outreach snapshots to process")
                return None

        snap_id = snapshot["id"]
        data = snapshot.get("data", {}) or {}
        business_info = data.get("business_info", {})
        insights = data.get("analyzer_insights", {})
        scoring = data.get("scoring_output", {})
        roadmap = data.get("growth_roadmap", [])
        name = business_info.get("name", snapshot["business_name"])
        location = business_info.get("location", snapshot["location"])

        logger.info(f"Outreach drafting for: {name}")

        try:
            email_subject, email_body = self._generate_email(
                business_name=name,
                location=location,
                insights=insights,
                scoring=scoring,
                roadmap=roadmap,
            )
            sms_body = self._generate_sms(
                business_name=name,
                location=location,
                insights=insights,
                scoring=scoring,
            )

            if not self.dry_run:
                # Persist to database
                email_outreach_id = create_outreach(
                    snapshot_id=snap_id,
                    channel="email",
                    subject=email_subject,
                    body=email_body,
                    status="drafted",
                )
                sms_outreach_id = create_outreach(
                    snapshot_id=snap_id,
                    channel="sms",
                    subject="",
                    body=sms_body,
                    status="drafted",
                )

                # Log to file for owner review
                self._log_to_file(
                    snap_id=snap_id,
                    business_name=name,
                    email_subject=email_subject,
                    email_body=email_body,
                    sms_body=sms_body,
                    variant=self.ab.selected,
                )

                # Mark snapshot as outreach_done
                update_snapshot_status(snap_id, "outreach_done")

                # Auto-trigger snapshot report email delivery
                requester_email = data.get("requester_email", "")
                if requester_email:
                    try:
                        send_snapshot_report(
                            to_email=requester_email,
                            snapshot_data=snapshot,
                        )
                        logger.info(f"Snapshot report sent to {requester_email}")
                    except Exception as e:
                        logger.warning(f"Snapshot report email failed for {requester_email}: {e}")

                logger.info(
                    f"Outreach complete for {name}: email_id={email_outreach_id}, sms_id={sms_outreach_id}"
                )
            else:
                logger.info(
                    f"[DRY RUN] Would draft outreach for {name} (variant={self.ab.selected})"
                )
                self._log_to_file(
                    snap_id=snap_id,
                    business_name=name,
                    email_subject=email_subject,
                    email_body=email_body,
                    sms_body=sms_body,
                    variant=self.ab.selected,
                    dry_run=True,
                )

            return snap_id

        except Exception as e:
            logger.error(f"Outreach failed for {name}: {e}")
            if not self.dry_run:
                update_snapshot_status(snap_id, "outreach_failed")
            return None

    def run_batch(self, max_count: int = 10) -> int:
        """Process up to max_count snapshots. Returns number processed."""
        processed = 0
        for _ in range(max_count):
            result = self.run_once()
            if result is None:
                break
            processed += 1
        return processed

    def _generate_email(
        self,
        business_name: str,
        location: str,
        insights: dict[str, Any],
        scoring: dict[str, Any],
        roadmap: list[dict[str, Any]] = None,
    ) -> tuple[str, str]:
        """Generate a personalized Insight-First email."""
        city = location.split(",")[0].strip() if "," in location else location
        niche = self._infer_niche(business_name)

        benchmark = insights.get("benchmark_comparison", {})
        weakest = benchmark.get("weakest_pillar", "visibility")
        strongest = benchmark.get("strongest_pillar", "conversion")
        health_score = scoring.get("total_health_score", "?")
        percentile = benchmark.get("trust", {}).get("percentile_estimate", "bottom 25%")

        gaps = insights.get("gaps", [])
        specific_insight = self._pick_insight(gaps, weakest)

        owner_name = self._extract_owner_name(business_name)

        subject, _ = self.ab.get_subject(business_name, city)
        body_template = self.ab.get_body_template()

        # Add top 3 roadmap actions if available
        roadmap_text = ""
        if roadmap and len(roadmap) > 0:
            top_actions = roadmap[:3]
            roadmap_text = "\n\nTop Priority Actions:\n"
            for i, action in enumerate(top_actions, 1):
                roadmap_text += f"{i}. {action.get('action', 'Action item')}\n"

        body = body_template.format(
            owner_name=owner_name,
            business_name=business_name,
            city=city,
            niche=niche,
            strongest_pillar=strongest.title(),
            weakest_pillar=weakest.title(),
            specific_insight=specific_insight,
            health_score=health_score,
            percentile=percentile,
        )

        if roadmap_text:
            body += roadmap_text

        return subject, body

    def _generate_sms(
        self,
        business_name: str,
        location: str,
        insights: dict[str, Any],
        scoring: dict[str, Any],
    ) -> str:
        """Generate a personalized SMS follow-up."""
        city = location.split(",")[0].strip() if "," in location else location
        benchmark = insights.get("benchmark_comparison", {})
        strongest = benchmark.get("strongest_pillar", "conversion")
        owner_name = self._extract_owner_name(business_name)

        return SMS_TEMPLATE.format(
            owner_name=owner_name,
            business_name=business_name,
            city=city,
            strongest_pillar=strongest.title(),
        )

    def _pick_insight(self, gaps: list[str], weakest_pillar: str) -> str:
        """Select the most compelling specific insight from gaps."""
        if not gaps:
            return (
                "your Google Business Profile is incomplete, which typically causes "
                "a 30% drop in local search visibility."
            )

        pillar_keywords = {
            "trust": ["review", "rating", "trust", "response"],
            "visibility": ["gbp", "google business", "category", "profile", "seo", "local"],
            "conversion": ["mobile", "booking", "cta", "website", "load time", "phone"],
        }
        keywords = pillar_keywords.get(weakest_pillar.lower(), [])

        for gap in gaps:
            gap_lower = gap.lower()
            if any(kw in gap_lower for kw in keywords):
                return gap + ", which is likely costing you leads every day."

        return gaps[0] + ", which is likely costing you leads every day."

    def _infer_niche(self, business_name: str) -> str:
        """Infer service niche from business name."""
        name_lower = business_name.lower()
        keywords = {
            "hvac": "HVAC",
            "plumbing": "Plumbing",
            "electric": "Electrical",
            "roof": "Roofing",
            "garage": "Garage Doors",
            "pest": "Pest Control",
        }
        for kw, niche in keywords.items():
            if kw in name_lower:
                return niche
        return "Home Services"

    def _extract_owner_name(self, business_name: str) -> str:
        """Generate a plausible first name for the owner."""
        return "there"

    def _log_to_file(
        self,
        snap_id: str,
        business_name: str,
        email_subject: str,
        email_body: str,
        sms_body: str,
        variant: str = "a",
        dry_run: bool = False,
    ) -> None:
        """Write the drafted outreach sequence to a file for owner review."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = "DRYRUN_" if dry_run else ""
        filename = f"{prefix}{timestamp}_{snap_id[:8]}_{_safe_filename(business_name)}.txt"
        filepath = self.logs_dir / filename

        status_line = "DRY RUN (not saved to DB)" if dry_run else "DRAFT (awaiting owner approval before send)"

        content = f"""================================================================================
LOCALPULSE AI — OUTREACH DRAFT
Business: {business_name}
Snapshot ID: {snap_id}
A/B Variant: {variant}
Generated: {datetime.now(timezone.utc).isoformat()}
Status: {status_line}
================================================================================

--- EMAIL ---
Subject: {email_subject}

{email_body}

--- SMS FOLLOW-UP ---
{sms_body}

--- LEAD MAGNET HEADLINES ---
{chr(10).join(HEADLINE_TEMPLATES).format(business_name=business_name, city="your city")}

================================================================================
NOTE: This is a simulated outreach message. No email API is connected yet.
================================================================================
"""
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Outreach draft logged to {filepath}")


def _safe_filename(name: str) -> str:
    """Create a filesystem-safe filename fragment from a business name."""
    return "".join(c if c.isalnum() else "_" for c in name).lower()


def run_outreach_pipeline(max_iterations: int = 10, dry_run: bool = False, variant: Optional[str] = None) -> int:
    """Run the outreach agent in a loop.

    Returns the number of snapshots processed.
    """
    agent = OutreachAgent(dry_run=dry_run, ab_variant=variant)
    return agent.run_batch(max_iterations)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outreach",
        description="LocalPulse AI Outreach Agent — generate personalized outreach sequences",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run command
    run_parser = subparsers.add_parser("run", help="Run the outreach pipeline")
    run_parser.add_argument("--batch", type=int, default=10, help="Max snapshots to process")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate without writing to DB")
    run_parser.add_argument("--variant", choices=["a", "b", "c"], default=None, help="A/B test variant")
    run_parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    # list command
    list_parser = subparsers.add_parser("list", help="List drafted outreach messages")
    list_parser.add_argument("--status", default=None, help="Filter by status")

    # status command
    status_parser = subparsers.add_parser("status", help="Update outreach status")
    status_parser.add_argument("outreach_id", help="Outreach record ID")
    status_parser.add_argument("new_status", choices=OUTREACH_STATUSES, help="New status")

    return parser


def main(args: Optional[list[str]] = None) -> int:
    parser = build_cli()
    parsed = parser.parse_args(args)

    if parsed.command is None:
        parser.print_help()
        return 1

    if parsed.command == "run":
        level = logging.DEBUG if parsed.verbose else logging.INFO
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
        count = run_outreach_pipeline(
            max_iterations=parsed.batch,
            dry_run=parsed.dry_run,
            variant=parsed.variant,
        )
        mode = "dry-run" if parsed.dry_run else "live"
        print(f"Processed {count} snapshots ({mode} mode)")
        return 0

    if parsed.command == "list":
        records = list_outreach(status=parsed.status)
        if not records:
            print("No outreach records found.")
            return 0
        print(f"{'ID':<36} {'Channel':<8} {'Status':<12} {'Subject'}")
        print("-" * 80)
        for r in records:
            subj = (r.get("subject") or "")[:40]
            print(f"{r['id']:<36} {r['channel']:<8} {r['status']:<12} {subj}")
        return 0

    if parsed.command == "status":
        update_outreach_status(parsed.outreach_id, parsed.new_status)
        print(f"Updated {parsed.outreach_id} -> {parsed.new_status}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
