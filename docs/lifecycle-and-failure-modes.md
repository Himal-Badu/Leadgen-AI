# Customer Lifecycle & Failure-Mode Specification

This document defines the end-to-end customer journey for LocalPulse AI and specifies how the system should handle failures at each stage to ensure production stability.

---

## 1. Customer Lifecycle Phases

### Phase 1: Awareness & Hook (The "Aha!" Moment)
*   **User Action:** Enters business name and website on landing page.
*   **System Action:** Creates a `snapshot` record, triggers the **Scout Agent**.
*   **Outcome:** User sees "Analyzing your business..." progress bar.

### Phase 2: Report Generation (The Value Delivery)
*   **User Action:** Waits for results.
*   **System Action:** Pipeline runs (Scout → Analyzer → Scorer → Strategist).
*   **Outcome:** A restricted "Business Health Snapshot" is displayed.

### Phase 3: Conversion (Monetization)
*   **User Action:** Clicks "Get Full Roadmap" or "Fix Gaps Now".
*   **System Action:** Redirects to Stripe Checkout.
*   **Outcome:** Successful payment updates snapshot status to `paid`.

### Phase 4: Full Asset Generation (Product Execution)
*   **User Action:** Accesses the full dashboard.
*   **System Action:** **Builder Agent** creates responses, SEO edits, and copy. **Outreach Agent** prepares email drafts.
*   **Outcome:** Business owner approves/deploys fixes.

### Phase 5: Retention & Continuous Monitoring (LTV)
*   **User Action:** Subscribes to "Autopilot" or "Pro" monitoring.
*   **System Action:** Weekly pipeline runs to track score changes.
*   **Outcome:** Monthly growth report delivered via email.

---

## 2. Failure-Mode Analysis & Hardening

| Lifecycle Phase | Point of Failure | Failure Impact | Mitigation / Recovery Strategy |
| :--- | :--- | :--- | :--- |
| **Phase 1: Entry** | Duplicate Request | Wasted API costs, messy DB. | Debounce frontend; `create_snapshot()` in `core/database.py` should check for existing snapshot for that URL/Domain in the last 24h before inserting. |
| **Phase 1: Entry** | Invalid/Fake URL | Scout Agent fails later. | Validate URL format and reachability (HEAD request) before accepting the form. |
| **Phase 2: Pipeline** | Scraper Blocked (Scout) | No data for analysis. | Implement proxy rotation; fallback to basic metadata; set `status='failed_scout'`. |
| **Phase 2: Pipeline** | LLM Hallucination (Analyzer) | Nonsensical growth tips. | Use JSON schema validation in `core/schema.py`; Implement a "Sanity Check" agent to verify tips. |
| **Phase 2: Pipeline** | Pipeline Timeout | User leaves page. | Move pipeline to background worker; `claim_next_snapshot()` in `core/database.py` ensures atomic processing. |
| **Phase 3: Checkout** | Payment Failed | User doesn't get full data. | Webhook listener for `payment_intent.payment_failed` in `core/stripe_payments.py` to trigger automated "Complete setup" email. |
| **Phase 3: Checkout** | Webhook Delay | Paid but report still locked. | Implement "Check Payment Status" button on UI to manually poll Stripe API via `core/stripe_payments.py` as a fallback. |
| **Phase 4: Builder** | Poor Quality Asset | Owner loses trust. | Provide "Regenerate" button for specific assets in the dashboard; `builder.py` should support selective re-runs. |
| **Phase 5: Retention** | Credit Card Expired | Subscription churn. | Pre-emptive email 7 days before expiration via `core/email_service.py`. |

---

## 3. Global Hardening Requirements

1.  **State Persistence:** Every agent transition must be logged in `snapshots.status` via `update_snapshot_status()` (e.g., `scout_started`, `scout_failed`, `scout_completed`).
2.  **Idempotency:** `claim_next_snapshot()` handles concurrency. Re-running a failed pipeline step should overwrite the relevant data key via `update_snapshot_data()`, not create new records.
3.  **Circuit Breakers:** If an agent fails 5 times in an hour, pause the queue and alert the team via `email_service.py`.
4.  **Graceful Degradation:** If `Scorer` fails, show raw insights but skip the 0-100 score rather than crashing the whole report page.
5.  **Audit Trail:** Store raw LLM prompts and responses for every `snapshot` in a dedicated `logs` table (to be created) for debugging.
