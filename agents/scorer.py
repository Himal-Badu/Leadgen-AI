"""Scoring Agent — Quantification

Responsibility: Apply a weighted scoring algorithm to the analyzer insights.
Metric Categories:
  - Visibility (30%): Local search ranking, citation consistency, GBP completeness
  - Trust (40%): Average rating, review volume, review recency, response rate
  - Conversion (30%): Website speed, mobile UX, booking flow availability, CTA prominence
Output: Business Health Score (0-100) with breakdown.
"""
import logging
from typing import Any, Optional

from config.settings import SCORING_WEIGHTS
from core.database import (
    claim_next_snapshot,
    update_snapshot_data,
    update_snapshot_status,
)

logger = logging.getLogger(__name__)


class ScoringAgent:
    """Scoring agent computes the final Business Health Score from analyzer insights."""

    def run_once(self) -> Optional[str]:
        """Poll for an analyzer_done snapshot and score it.
        
        Returns the processed snapshot ID or None if no work.
        """
        snapshot = claim_next_snapshot("analyzer_done", "scoring_done")
        if snapshot is None:
            logger.debug("No analyzer_done snapshots to score")
            return None

        snap_id = snapshot["id"]
        data = snapshot.get("data", {}) or {}
        insights = data.get("analyzer_insights", {})
        name = data.get("business_info", {}).get("name", snapshot["business_name"])

        logger.info(f"Scoring: {name}")

        try:
            scoring_output = self._score(insights)
            update_snapshot_data(snap_id, "scoring_output", scoring_output)
            logger.info(
                f"Scoring complete for {name}: {scoring_output['total_health_score']}/100"
            )
            return snap_id

        except Exception as e:
            logger.error(f"Scoring failed for {name}: {e}")
            update_snapshot_status(snap_id, "failed")
            return None

    def _score(self, insights: dict[str, Any]) -> dict[str, Any]:
        """Apply weighted scoring algorithm to produce the final health score."""
        trust_raw = insights.get("trust_score_raw", 0) or 0
        visibility_raw = insights.get("visibility_score_raw", 0) or 0
        conversion_raw = insights.get("conversion_score_raw", 0) or 0

        # Compute weighted scores
        trust_weighted = int(trust_raw * SCORING_WEIGHTS["trust"])
        visibility_weighted = int(visibility_raw * SCORING_WEIGHTS["visibility"])
        conversion_weighted = int(conversion_raw * SCORING_WEIGHTS["conversion"])

        total = trust_weighted + visibility_weighted + conversion_weighted

        return {
            "total_health_score": total,
            "breakdown": {
                "visibility": visibility_weighted,
                "trust": trust_weighted,
                "conversion": conversion_weighted,
            },
        }


def run_scoring_pipeline(max_iterations: int = 10) -> int:
    """Run the scoring agent in a loop.
    
    Returns the number of snapshots processed.
    """
    scorer = ScoringAgent()
    processed = 0
    for _ in range(max_iterations):
        result = scorer.run_once()
        if result is None:
            break
        processed += 1
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = run_scoring_pipeline()
    print(f"Processed {count} snapshots")