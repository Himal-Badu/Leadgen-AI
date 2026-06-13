#!/usr/bin/env python3
"""Standalone Notion CRM sync script.

Usage:
    python scripts/sync_notion.py --setup
    python scripts/sync_notion.py --sync
    python scripts/sync_notion.py --dry-run
    python scripts/sync_notion.py --setup --sync

Environment:
    NOTION_TOKEN    — Required. Notion integration token.
    NOTION_PAGE_ID  — Required. Root page ID for database creation.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.notion_crm import main

if __name__ == "__main__":
    main()
