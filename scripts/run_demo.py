#!/usr/bin/env python3
"""LocalPulse AI — Demo Mode

Runs the full pipeline on a simulated HVAC business in Austin, TX
without any real API calls. Outputs a complete Business Health Snapshot
to the terminal and optionally saves an HTML report to disk.

Usage:
    python scripts/run_demo.py
    python scripts/run_demo.py --save-report ./demo_report.html
    python scripts/run_demo.py --verbose
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.analyzer import AnalyzerAgent
from agents.builder import BuilderAgent
from agents.outreach import OutreachAgent
from agents.scorer import ScoringAgent
from agents.strategist import StrategistAgent
from core.database import (
    create_snapshot,
    get_snapshot,
    update_snapshot_data,
    update_snapshot_status,
)
from core.email_service import send_snapshot_report
from core.report_renderer import render_snapshot_report

logger = logging.getLogger(__name__)

DEMO_BUSINESS = {
    "name": "Austin Pro HVAC",
    "location": "Austin, TX",
    "website": "https://austinprohvac.example.com",
    "phone": "(512) 555-0199",
    "niche": "HVAC",
    "owner_email": "demo@localpulse.ai",
}


# ── Mock Scout Data ───────────────────────────────────────────────────────────

def generate_mock_scout_data() -> dict[str, Any]:
    """Generate realistic mock data for the Scout phase."""
    return {
        "gbp": {
            "name": DEMO_BUSINESS["name"],
            "address": "7421 N Lamar Blvd, Austin, TX 78752",
            "phone": DEMO_BUSINESS["phone"],
            "rating": 3.8,
            "review_count": 34,
            "categories": ["HVAC Contractor"],
            "photos_count": 8,
            "posts_count": 2,
            "has_booking_link": False,
            "has_qa": True,
            "hours_complete": False,
            "service_area": "Austin, Round Rock, Cedar Park",
        },
        "website": {
            "url": DEMO_BUSINESS["website"],
            "load_time_ms": 6200,
            "is_mobile_friendly": False,
            "has_ssl": True,
            "phone_numbers": [DEMO_BUSINESS["phone"]],
            "has_booking_form": False,
            "has_contact_form": True,
            "cta_count": 1,
            "schema_org": {
                "has_localbusiness": True,
                "has_service": False,
                "has_review": False,
            },
            "page_count": 6,
            "has_blog": False,
        },
        "reviews": {
            "average_rating": 3.8,
            "review_count": 34,
            "recent_reviews": 3,
            "response_rate": 0.12,
            "reviews": [
                {
                    "rating": 5,
                    "text": "Great service, fixed my AC in under an hour!",
                    "author": "Sarah M.",
                    "date": "2024-05-15",
                    "responded": False,
                },
                {
                    "rating": 2,
                    "text": "Took two days to show up. Disappointed.",
                    "author": "Mike R.",
                    "date": "2024-04-28",
                    "responded": False,
                },
                {
                    "rating": 4,
                    "text": "Professional crew, fair pricing.",
                    "author": "Jenny L.",
                    "date": "2024-06-01",
                    "responded": True,
                },
            ],
        },
        "competitors": [
            {
                "name": "Austin Air Experts",
                "rating": 4.7,
                "review_count": 312,
                "has_booking_link": True,
            },
            {
                "name": "Cool Breeze HVAC",
                "rating": 4.5,
                "review_count": 189,
                "has_booking_link": True,
            },
        ],
        "citations": {
            "consistent_nap": False,
            "directories_found": 4,
            "directories_total": 12,
        },
    }


# ── Terminal Reporter ─────────────────────────────────────────────────────────

def print_header(text: str, width: int = 70) -> None:
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def print_box(title: str, lines: list[str], width: int = 70) -> None:
    print(f"\n┌{'─' * (width - 2)}┐")
    print(f"│ {title:<{width - 3}}│")
    print(f"├{'─' * (width - 2)}┤")
    for line in lines:
        # Wrap long lines
        while line:
            chunk = line[:width - 4]
            line = line[width - 4:]
            print(f"│ {chunk:<{width - 4}}│")
    print(f"└{'─' * (width - 2)}┘")


def print_health_score_card(scoring: dict[str, Any]) -> None:
    total = scoring.get("total_health_score", 0)
    breakdown = scoring.get("breakdown", {})

    if total >= 80:
        color = "🟢"
        label = "EXCELLENT"
    elif total >= 60:
        color = "🟡"
        label = "GOOD"
    elif total >= 40:
        color = "🟠"
        label = "NEEDS WORK"
    else:
        color = "🔴"
        label = "CRITICAL"

    print(f"\n   {color}  HEALTH SCORE: {total}/100  —  {label}")
    print()
    for pillar, score in breakdown.items():
        bar_len = int(score / 2)
        bar = "█" * bar_len + "░" * (50 - bar_len)
        print(f"   {pillar.title():>12} │{bar}│ {score}")


def print_snapshot_report(snapshot: dict[str, Any]) -> None:
    """Pretty-print a Business Health Snapshot to the terminal."""
    data = snapshot.get("data", {}) or {}
    business_info = data.get("business_info", {})
    scout_data = data.get("scout_data", {})
    insights = data.get("analyzer_insights", {})
    scoring = data.get("scoring_output", {})
    roadmap = data.get("growth_roadmap", [])
    deliverables = data.get("draft_deliverables", {})

    name = business_info.get("name", DEMO_BUSINESS["name"])
    location = business_info.get("location", DEMO_BUSINESS["location"])

    print_header(f"LocalPulse AI — Business Health Snapshot")
    print(f"\n  Business: {name}")
    print(f"  Location: {location}")
    print(f"  Website:  {business_info.get('website', 'N/A')}")
    print(f"  Phone:    {scout_data.get('gbp', {}).get('phone', 'N/A')}")

    # Health Score
    print_header("Health Score")
    print_health_score_card(scoring)

    # Gaps
    print_header("Top Gaps Identified")
    gaps = insights.get("gaps", [])
    if gaps:
        for i, gap in enumerate(gaps[:5], 1):
            print(f"  {i}. {gap}")
    else:
        print("  No gaps identified.")

    # Benchmark
    print_header("Competitor Benchmark")
    benchmark = insights.get("benchmark_comparison", {})
    strongest = benchmark.get("strongest_pillar", "N/A")
    weakest = benchmark.get("weakest_pillar", "N/A")
    print(f"  Strongest Pillar: {strongest.title()}")
    print(f"  Weakest Pillar:   {weakest.title()}")
    competitors = scout_data.get("competitors", [])
    if competitors:
        print(f"\n  Competitor Comparison:")
        for comp in competitors:
            print(f"    • {comp['name']}: {comp['rating']}★ ({comp['review_count']} reviews)")

    # Roadmap
    print_header("3-Step Growth Roadmap")
    if roadmap:
        for i, action in enumerate(roadmap[:5], 1):
            title = action.get("action", "Action")
            details = action.get("details", "")
            impact = action.get("impact", "Medium")
            priority = action.get("priority", i)
            print(f"\n  Step {priority}: {title}")
            print(f"  Impact: {impact}")
            if details:
                print(f"  Details: {details}")
    else:
        print("  No roadmap generated.")

    # Deliverables
    items = deliverables.get("items", []) if isinstance(deliverables, dict) else []
    if items:
        print_header("Generated Deliverables")
        for item in items:
            print(f"\n  📄 {item.get('title', 'Deliverable')}")
            print(f"     Type: {item.get('type', 'N/A')}")
            desc = item.get("description", "")
            if desc:
                print(f"     {desc}")
            content = item.get("content", "")
            if isinstance(content, list) and content:
                for c in content[:3]:
                    text = c.get("text", str(c)) if isinstance(c, dict) else str(c)
                    print(f"       • {text[:100]}{'...' if len(text) > 100 else ''}")
            elif isinstance(content, str) and content:
                print(f"       {content[:120]}{'...' if len(content) > 120 else ''}")

    # Outreach
    outreach = data.get("outreach_draft", {})
    if outreach:
        print_header("Outreach Email Draft")
        print(f"\n  Subject: {outreach.get('subject', 'N/A')}")
        print(f"\n{outreach.get('body', 'N/A')}")

    print_header("End of Report")
    print("\n  💡 Tip: Run with --save-report <path> to save the HTML version.")
    print()


# ── Pipeline Runner ───────────────────────────────────────────────────────────

def run_demo_pipeline(verbose: bool = False) -> dict[str, Any]:
    """Run the full LocalPulse pipeline on a simulated business.

    Returns the final snapshot dict.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # 1. Create snapshot
    print("\n🚀  LocalPulse AI Demo Mode")
    print("   Simulating: HVAC business in Austin, TX\n")

    snap_id = create_snapshot(
        business_name=DEMO_BUSINESS["name"],
        location=DEMO_BUSINESS["location"],
        website=DEMO_BUSINESS["website"],
    )
    print(f"   [1/7] Snapshot created: {snap_id[:8]}...")

    # Inject business info + requester email
    update_snapshot_data(snap_id, "business_info", {
        "name": DEMO_BUSINESS["name"],
        "location": DEMO_BUSINESS["location"],
        "website": DEMO_BUSINESS["website"],
        "phone": DEMO_BUSINESS["phone"],
        "niche": DEMO_BUSINESS["niche"],
    })
    update_snapshot_data(snap_id, "requester_email", DEMO_BUSINESS["owner_email"])

    # 2. Inject mock scout data and advance status
    mock_scout = generate_mock_scout_data()
    update_snapshot_data(snap_id, "scout_data", mock_scout)
    update_snapshot_status(snap_id, "scout_done")
    print(f"   [2/7] Scout data injected ({len(mock_scout)} sections)")

    # 3. Analyzer
    analyzer = AnalyzerAgent()
    result = analyzer.run_once()
    if result:
        print(f"   [3/7] Analyzer complete")
    else:
        print(f"   [3/7] Analyzer skipped (no work)")

    # 4. Scorer
    scorer = ScoringAgent()
    result = scorer.run_once()
    if result:
        print(f"   [4/7] Scorer complete")
    else:
        print(f"   [4/7] Scorer skipped (no work)")

    # 5. Strategist
    strategist = StrategistAgent()
    result = strategist.run_once()
    if result:
        print(f"   [5/7] Strategist complete")
    else:
        print(f"   [5/7] Strategist skipped (no work)")

    # 6. Builder
    builder = BuilderAgent()
    result = builder.run_once()
    if result:
        print(f"   [6/7] Builder complete")
    else:
        print(f"   [6/7] Builder skipped (no work)")

    # 7. Outreach (dry-run, just generates draft)
    outreach = OutreachAgent(dry_run=True)
    result = outreach.run_once()
    if result:
        print(f"   [7/7] Outreach draft generated")
    else:
        print(f"   [7/7] Outreach skipped (no work)")

    # Fetch final snapshot
    final = get_snapshot(snap_id)
    if not final:
        raise RuntimeError("Failed to retrieve final snapshot")

    return final


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="LocalPulse AI Demo — run the full pipeline on simulated data"
    )
    parser.add_argument(
        "--save-report",
        metavar="PATH",
        help="Save the HTML report to the specified file path",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send a dry-run email preview (no actual email sent)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    try:
        snapshot = run_demo_pipeline(verbose=args.verbose)
    except Exception as e:
        logger.exception("Demo pipeline failed")
        print(f"\n❌  Demo failed: {e}", file=sys.stderr)
        return 1

    # Print terminal report
    print_snapshot_report(snapshot)

    # Save HTML report
    if args.save_report:
        html = render_snapshot_report(snapshot)
        out_path = Path(args.save_report)
        out_path.write_text(html, encoding="utf-8")
        print(f"📄  HTML report saved to: {out_path.resolve()}")

    # Dry-run email preview
    if args.send_email:
        try:
            result = send_snapshot_report(
                to_email=DEMO_BUSINESS["owner_email"],
                snapshot_data=snapshot,
                dry_run=True,
            )
            print(f"📧  Email dry-run complete (message ID: {result.get('id', 'N/A')})")
        except Exception as e:
            print(f"⚠️  Email dry-run failed: {e}")

    print(f"\n✅  Demo complete! Snapshot ID: {snapshot['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
