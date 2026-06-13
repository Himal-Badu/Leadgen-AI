# LocalPulse AI — Business Intelligence Agent

Transform fragmented online data (reviews, Google Business Profiles, competitor rankings, booking flows) into a unified **Business Health Score** and a prioritized growth roadmap.

## Architecture

The system operates as a pipeline of specialized agents:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
│  Scout   │ →  │ Analyzer │ →  │  Scorer  │ →  │ Strategist │
│  Agent   │    │  Agent   │    │  Agent   │    │   Agent    │
└──────────┘    └──────────┘    └──────────┘    └────────────┘
   data            insights       score +          growth
 acquisition      extraction     breakdown        roadmap
```

## Agent Pipeline

| Agent | Status | Responsibility |
|-------|--------|---------------|
| **Scout** | `pending` → `scout_done` | Collects raw data (GBP, website, reviews) |
| **Analyzer** | `scout_done` → `analyzer_done` | Extracts insights (sentiment, gaps, features) |
| **Scorer** | `analyzer_done` → `scoring_done` | Calculates 0-100 Health Score with breakdown |
| **Strategist** | `scoring_done` → `completed` | Generates prioritized growth roadmap |

## Database

Uses the shared **team-db** SQLite database (synced via Turso). The main table is `snapshots`, which tracks each business health report through the pipeline.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Seed demo data
python scripts/seed_demo.py

# Run the full pipeline
python scripts/run_pipeline.py
```

## Project Structure

```
localpulse-ai/
├── agents/          # Agent modules (Scout, Analyzer, Scorer, Strategist)
├── core/            # Shared core (database, schema validation)
├── config/          # Configuration and settings
├── docs/            # Documentation
├── scripts/         # Pipeline runners and utilities
├── tests/           # Unit tests
└── requirements.txt # Python dependencies
```
