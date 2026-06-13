#!/usr/bin/env python3
"""Seed the database with demo businesses for testing the pipeline.

Usage:
    python scripts/seed_demo.py    
"""
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import create_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEMO_BUSINESSES = [
    {
        "name": "Ace HVAC Services",
        "location": "Austin, TX",
        "website": "https://example-hvac-austin.com",
    },
    {
        "name": "Best Plumbing Co",
        "location": "Denver, CO",
        "website": "https://example-plumbing-denver.com",
    },
    {
        "name": "City Electricians",
        "location": "Portland, OR",
        "website": "https://example-electric-portland.com",
    },
    {
        "name": "Premier Roofing",
        "location": "Phoenix, AZ",
        "website": "https://example-roofing-phoenix.com",
    },
    {
        "name": "Garage Door Pros",
        "location": "Chicago, IL",
        "website": "https://example-garage-chicago.com",
    },
]


def seed_demo_data() -> list[str]:
    """Insert demo businesses as pending snapshots.
    
    Returns list of created snapshot IDs.
    """
    created = []
    for biz in DEMO_BUSINESSES:
        snap_id = create_snapshot(
            business_name=biz["name"],
            location=biz["location"],
            website=biz["website"],
        )
        created.append(snap_id)
        logger.info(f"Created snapshot: {snap_id} — {biz['name']} ({biz['location']})")
    return created


def main():
    confirm = input(f"This will create {len(DEMO_BUSINESSES)} demo snapshots. Continue? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    ids = seed_demo_data()
    print(f"\nCreated {len(ids)} snapshots.")
    print(f"Run 'python scripts/run_pipeline.py' to process them.")


if __name__ == "__main__":
    main()
