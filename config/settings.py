"""Application settings and configuration for LocalPulse AI."""

import json
import os
from pathlib import Path

# ── Project Paths ──────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DOCS_DIR = ROOT_DIR / "docs"
AGENTS_DIR = ROOT_DIR / "agents"

# ── Scoring Weights (from the Strategist's architecture) ───────────────────
# Visibility: Local search ranking, citation consistency, GBP completeness
# Trust: Average rating, review volume, review recency, response rate
# Conversion: Website speed, mobile UX, booking flow availability, CTA prominence
SCORING_WEIGHTS = {
    "visibility": 0.30,
    "trust": 0.40,
    "conversion": 0.30,
}

# ── Pipeline State Machine ─────────────────────────────────────────────────
VALID_STATUS_TRANSITIONS = {
    "pending":            ["scout_done"],
    "scout_done":         ["analyzer_done"],
    "analyzer_done":      ["scoring_done"],
    "scoring_done":       ["completed"],
    "completed":          ["ready_for_outreach"],
    "ready_for_outreach": [],
    "failed":             [],
}

# ── Defaults ───────────────────────────────────────────────────────────────
DEFAULT_SCOUT_TIMEOUT_SECONDS = 30
