# LocalPulse AI Architecture

LocalPulse AI is built as a modular pipeline of specialized AI agents. Each agent is responsible for a specific stage of the business intelligence lifecycle, from raw data acquisition to generating actionable growth strategies.

## Agent Pipeline Flow

The following diagram illustrates the end-to-end flow of a Business Health Snapshot:

```
Landing Page → Flask API → Scout Agent → Analyzer Agent → Scorer Agent → Strategist Agent → Builder Agent → Outreach Agent → Output (Email / Notion / Stripe)
```

### 1. Data Acquisition (Scout Agent)
- **Input:** Business name and location/URL.
- **Action:** Scrapes Google Business Profile (GBP), website content, and customer reviews.
- **Output:** Raw JSON data containing the business's online footprint.

### 2. Insight Extraction (Analyzer Agent)
- **Input:** Raw data from Scout Agent.
- **Action:** Uses LLMs to extract key features, identify service gaps, and perform sentiment analysis on reviews.
- **Output:** Structured insights and competitive benchmarks.

### 3. Business Health Scoring (Scorer Agent)
- **Input:** Extracted insights.
- **Action:** Calculates a 0-100 **Business Health Score** based on four pillars:
  - **Visibility:** How easily customers find the business.
  - **Trust:** Review quality, quantity, and recency.
  - **Conversion:** Ease of booking and call-to-action effectiveness.
  - **Engagement:** Response rates and social signals.
- **Output:** Weighted score and pillar breakdown.

### 4. Growth Strategy (Strategist Agent)
- **Input:** Health Score and insights.
- **Action:** Prioritizes the most impactful "Growth Actions" (e.g., "Fix missing GBP booking link" or "Respond to 3-star reviews").
- **Output:** A prioritized growth roadmap.

### 5. Asset Generation (Builder Agent)
- **Input:** Growth roadmap.
- **Action:** Generates the actual assets needed for improvement (e.g., optimized GBP descriptions, review response drafts, or landing page copy).
- **Output:** Drafted content ready for approval.

### 6. Engagement & Delivery (Outreach Agent)
- **Input:** Generated assets and business contact info.
- **Action:** Orchestrates delivery via Email (Resend), syncs data to the Notion CRM, and handles payment flows via Stripe.
- **Output:** Completed outreach and dashboard update.

## Data Infrastructure

- **Backend:** Python + Flask
- **Database:** Turso (SQLite) for high-speed, distributed edge storage.
- **Task Management:** A state-driven pipeline where each agent updates the status of a `snapshot` until completion.
