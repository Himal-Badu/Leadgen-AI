# LocalPulse AI — Business Intelligence for Local Service Companies

AI-built MVP that turns fragmented online data into actionable growth roadmaps.

## 🤖 AI-Built MVP Case Study

**"I gave AI one instruction: build a local lead-gen SaaS from scratch."**

This repository is the MVP it produced: customer research, product strategy, landing page, pricing tiers, backend API, 5-agent pipeline, Stripe checkout, Notion CRM, email automation, and a comprehensive test suite.

I acted as the founder/director. AI acted as the entire product and engineering team. Every line of code, every architectural decision, and every word of copy was generated or directed by AI to satisfy a high-level business vision.

**This is what AI-native founding looks like.**

## 🏗 Architecture

LocalPulse AI operates as a coordinated swarm of specialized agents:

```text
Landing Page → Flask API → Scout Agent → Analyzer Agent → Scorer Agent → Strategist Agent → Builder Agent → Outreach Agent → Email / Notion CRM / Stripe
```

For a detailed breakdown of the data flow and agent responsibilities, see [docs/architecture.md](docs/architecture.md).

## 🛠 Tech Stack

- **Backend:** Python + Flask
- **Database:** Turso (SQLite at the edge)
- **Payments:** Stripe
- **CRM:** Notion API
- **Email:** Resend
- **AI Pipeline:** 5+ Specialized LLM Agents
- **Testing:** Pytest

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Demo Mode (Simulated Data)
See the product in action immediately without needing real-world scrapers or API keys.
```bash
python scripts/run_demo.py --save-report
```

### 3. Run Production Pipeline
```bash
# Monitor the task queue and process snapshots
python scripts/run_pipeline.py --watch
```

## 📂 Project Structure

```text
localpulse-ai/
├── agents/           # Specialized AI Agent modules
│   ├── scout.py      # Data acquisition
│   ├── analyzer.py   # Insight extraction
│   ├── scorer.py     # Health score calculation
│   ├── strategist.py # Growth roadmap generation
│   ├── builder.py    # Asset/Copy generation
│   └── outreach.py   # Delivery & CRM sync
├── core/             # Shared logic (DB, Email, Auth)
├── config/           # Environment & Pipeline settings
├── docs/             # Technical documentation
├── landing-page/     # React/Vite marketing site
├── scripts/          # CLI tools and pipeline runners
├── tests/            # Full test suite
└── requirements.txt  # Python dependencies
```

## ✅ Tests

All core logic is covered by automated tests.
```bash
pytest
```

## 📄 License

MIT
