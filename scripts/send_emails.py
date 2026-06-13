"""Send Emails CLI — Send snapshot reports, welcome emails, follow-ups, and upgrades.

Usage:
    python scripts/send_emails.py --snapshot-id <id>
    python scripts/send_emails.py --follow-up-day 3
    python scripts/send_emails.py --welcome test@example.com --business-name "Test Biz"
    python scripts/send_emails.py --snapshot-id <id> --dry-run
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_snapshot
from core.email_service import (
    send_follow_up,
    send_snapshot_report,
    send_upgrade_confirmation,
    send_welcome,
    run_followup_sequences,
)

logger = logging.getLogger(__name__)


def cmd_snapshot(args: argparse.Namespace) -> int:
    snapshot = get_snapshot(args.snapshot_id)
    if not snapshot:
        print(f"Snapshot not found: {args.snapshot_id}", file=sys.stderr)
        return 1

    data = snapshot.get("data", {}) or {}
    email = data.get("requester_email", "")
    if not email:
        print("No requester_email found in snapshot data.", file=sys.stderr)
        return 1

    try:
        response = send_snapshot_report(
            to_email=email,
            snapshot_data=snapshot,
            dry_run=args.dry_run,
        )
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Snapshot report sent to {email}")
        print(json.dumps(response, indent=2, default=str))
        return 0
    except Exception as e:
        print(f"Failed to send: {e}", file=sys.stderr)
        return 1


def cmd_welcome(args: argparse.Namespace) -> int:
    try:
        response = send_welcome(
            to_email=args.welcome,
            business_name=args.business_name or "your business",
            dry_run=args.dry_run,
        )
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Welcome email sent to {args.welcome}")
        print(json.dumps(response, indent=2, default=str))
        return 0
    except Exception as e:
        print(f"Failed to send: {e}", file=sys.stderr)
        return 1


def cmd_followup(args: argparse.Namespace) -> int:
    day = args.follow_up_day
    if day not in (1, 3, 7):
        print("--follow-up-day must be 1, 3, or 7", file=sys.stderr)
        return 1

    try:
        sent = run_followup_sequences(day=day, max_sends=args.max_sends, dry_run=args.dry_run)
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Sent {sent} follow-up emails for day {day}")
        return 0
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        return 1


def cmd_upgrade(args: argparse.Namespace) -> int:
    try:
        response = send_upgrade_confirmation(
            to_email=args.upgrade,
            tier=args.tier,
            stripe_customer_id=args.stripe_customer_id or "",
            dry_run=args.dry_run,
        )
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Upgrade confirmation sent to {args.upgrade}")
        print(json.dumps(response, indent=2, default=str))
        return 0
    except Exception as e:
        print(f"Failed to send: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="send_emails",
        description="LocalPulse AI Email CLI — send reports, welcomes, follow-ups, and confirmations",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")

    # Snapshot report
    parser.add_argument("--snapshot-id", help="Send snapshot report for this snapshot ID")

    # Welcome
    parser.add_argument("--welcome", help="Send welcome email to this address")
    parser.add_argument("--business-name", default="", help="Business name for welcome email")

    # Follow-up
    parser.add_argument("--follow-up-day", type=int, choices=[1, 3, 7], help="Trigger drip sequence for this day")
    parser.add_argument("--max-sends", type=int, default=10, help="Max follow-ups to send")

    # Upgrade confirmation
    parser.add_argument("--upgrade", help="Send upgrade confirmation to this address")
    parser.add_argument("--tier", choices=["starter", "pro", "autopilot"], default="starter", help="Subscription tier")
    parser.add_argument("--stripe-customer-id", default="", help="Stripe customer ID")

    return parser


def main(args: Optional[list[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    level = logging.DEBUG if parsed.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # Load env from .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    if parsed.snapshot_id:
        return cmd_snapshot(parsed)
    if parsed.welcome:
        return cmd_welcome(parsed)
    if parsed.follow_up_day is not None:
        return cmd_followup(parsed)
    if parsed.upgrade:
        return cmd_upgrade(parsed)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
