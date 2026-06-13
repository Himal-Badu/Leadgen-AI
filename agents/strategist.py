"""Strategist Agent — Action Planning (Builder)

Responsibility: Generate a prioritized growth roadmap based on the scores and gaps.
Action Generation:
  - Low Score in Trust + High Competitor Rating -> "Launch Review Generation Campaign"
  - Missing GBP Booking Link -> "Integrate Booking Flow to GBP"
  - High Visibility but Low Conversion -> "Optimize Website CTA/Mobile UX"
Output: Prioritized growth roadmap with impact/difficulty ratings.
"""
import logging
from typing import Any, Optional

from core.database import (
    claim_next_snapshot,
    update_snapshot_data,
    update_snapshot_status,
)

logger = logging.getLogger(__name__)


class StrategistAgent:
    """Strategist agent generates a prioritized growth roadmap."""

    def run_once(self) -> Optional[str]:
        """Poll for a scoring_done snapshot and generate a roadmap.
        
        Returns the processed snapshot ID or None if no work.
        """
        snapshot = claim_next_snapshot("scoring_done", "completed")
        if snapshot is None:
            logger.debug("No scoring_done snapshots to strategize")
            return None

        snap_id = snapshot["id"]
        data = snapshot.get("data", {}) or {}
        business_info = data.get("business_info", {})
        scout_data = data.get("scout_data", {})
        insights = data.get("analyzer_insights", {})
        scoring = data.get("scoring_output", {})
        name = business_info.get("name", snapshot["business_name"])

        logger.info(f"Strategizing: {name}")

        try:
            roadmap = self._generate_roadmap(
                business_info=business_info,
                scout_data=scout_data,
                insights=insights,
                scoring=scoring,
            )
            update_snapshot_data(snap_id, "growth_roadmap", roadmap)

            total_score = scoring.get("total_health_score", "?")
            logger.info(
                f"Strategist complete for {name}: Health Score={total_score}, "
                f"Actions={len(roadmap)}"
            )
            return snap_id

        except Exception as e:
            logger.error(f"Strategist failed for {name}: {e}")
            update_snapshot_status(snap_id, "failed")
            return None

    def _generate_roadmap(
        self,
        business_info: dict[str, Any],
        scout_data: dict[str, Any],
        insights: dict[str, Any],
        scoring: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate a prioritized list of growth actions based on identified gaps."""
        roadmap = []
        gaps = insights.get("gaps", [])
        breakdown = scoring.get("breakdown", {})
        total_score = scoring.get("total_health_score", 0)

        # ── Rule-based action generation ────────────────────────────────

        # 1. Trust-related actions
        trust_score = breakdown.get("trust", 0)
        if trust_score < 20:
            roadmap.append({
                "action": "Launch Review Generation Campaign — proactively ask customers for reviews",
                "impact": "High",
                "difficulty": "Low",
                "priority_score": 90,
            })
        elif trust_score < 40:
            roadmap.append({
                "action": "Increase review volume — set up automated review request流程",
                "impact": "Medium",
                "difficulty": "Low",
                "priority_score": 70,
            })

        if any("rating" in (g or "").lower() for g in gaps):
            roadmap.append({
                "action": "Monitor and respond to all reviews to improve trust signals",
                "impact": "Medium",
                "difficulty": "Low",
                "priority_score": 65,
            })

        if any("volume" in (g or "").lower() for g in gaps):
            roadmap.append({
                "action": "Create a review generation campaign - offer small incentives for reviews",
                "impact": "High",
                "difficulty": "Medium",
                "priority_score": 80,
            })

        # 2. Visibility-related actions
        visibility_score = breakdown.get("visibility", 0)
        if visibility_score < 15:
            roadmap.append({
                "action": "Complete Google Business Profile — add all categories, hours, photos, and services",
                "impact": "High",
                "difficulty": "Low",
                "priority_score": 95,
            })

        gbp = scout_data.get("gbp", {})
        if gbp.get("has_booking_link") is False or "booking link" in str(gaps).lower():
            roadmap.append({
                "action": "Integrate booking link into Google Business Profile",
                "impact": "High",
                "difficulty": "Medium",
                "priority_score": 85,
            })

        if not gbp.get("categories"):
            roadmap.append({
                "action": "Set relevant business categories on Google Business Profile",
                "impact": "Medium",
                "difficulty": "Low",
                "priority_score": 75,
            })

        # 3. Conversion-related actions
        conversion_score = breakdown.get("conversion", 0)
        if conversion_score < 15:
            roadmap.append({
                "action": "Optimize website for mobile — ensure responsive design and fast loading",
                "impact": "High",
                "difficulty": "Medium",
                "priority_score": 88,
            })

        website = scout_data.get("website", {})
        if website.get("has_booking_form") is False:
            roadmap.append({
                "action": "Add a prominent booking/contact form to the website homepage",
                "impact": "High",
                "difficulty": "Medium",
                "priority_score": 82,
            })

        if website.get("cta_count", 0) == 0:
            roadmap.append({
                "action": "Add clear Calls-to-Action (Call Now, Get Quote, Book Service) throughout website",
                "impact": "Medium",
                "difficulty": "Low",
                "priority_score": 72,
            })

        if website.get("is_mobile_friendly") is False:
            roadmap.append({
                "action": "Implement responsive web design for mobile users",
                "impact": "High",
                "difficulty": "Medium",
                "priority_score": 85,
            })

        # 4. Cross-cutting: If visibility is good but conversion is bad
        if visibility_score > 40 and conversion_score < 25:
            roadmap.append({
                "action": "A/B test website CTAs and booking flow to convert more visitors",
                "impact": "Medium",
                "difficulty": "Medium",
                "priority_score": 78,
            })

        # 5. General improvement for low overall score
        if total_score < 30:
            roadmap.append({
                "action": "Schedule a comprehensive LocalPulse professional audit",
                "impact": "High",
                "difficulty": "High",
                "priority_score": 60,
            })

        # Sort by priority_score descending
        roadmap.sort(key=lambda a: a["priority_score"], reverse=True)

        return roadmap


def run_strategist_pipeline(max_iterations: int = 10) -> int:
    """Run the strategist agent in a loop.
    
    Returns the number of snapshots processed.
    """
    strategist = StrategistAgent()
    processed = 0
    for _ in range(max_iterations):
        result = strategist.run_once()
        if result is None:
            break
        processed += 1
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = run_strategist_pipeline()
    print(f"Processed {count} snapshots")