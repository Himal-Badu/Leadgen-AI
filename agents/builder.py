"""Builder Agent — Deliverable Generation

Responsibility: Turn the Strategist's growth roadmap into actual,
ready-to-review draft deliverables.

Deliverables generated:
  - Review reply drafts (for "respond to reviews" actions)
  - SEO meta description drafts (for "local SEO" / visibility actions)
  - CTA copy suggestions (for "conversion" / "booking" actions)
  - GBP description drafts (for "GBP completeness" actions)
  - Outreach email draft (personalized from report data)
  - Landing page headline suggestions

Output: `draft_deliverables` JSON stored in snapshot data.
Status transition: completed → ready_for_outreach
"""

import logging
from typing import Any, Optional

from core.database import (
    claim_next_snapshot,
    update_snapshot_data,
    update_snapshot_status,
)

logger = logging.getLogger(__name__)


# ── Deliverable Templates ────────────────────────────────────────────────────

REVIEW_REPLY_TEMPLATES = {
    "positive": [
        "Thank you so much for the kind words, {name}! We're thrilled you had a great experience and appreciate you taking the time to share your feedback. If you ever need us again, we're just a call away!",
        "Thanks {name}! It's customers like you that make our work so rewarding. We truly appreciate your business and your review.",
    ],
    "neutral": [
        "Thank you for your feedback, {name}. We appreciate you taking the time to share your experience and are always looking for ways to improve. If there's anything we can do better next time, please let us know!",
        "Thanks for the review, {name}. We're glad we could help and would love the opportunity to earn a 5-star experience on your next visit.",
    ],
    "negative": [
        "Hi {name}, we're truly sorry your experience didn't meet expectations. We'd like to make this right — please give us a call at {phone} so we can address your concerns directly.",
        "Thank you for bringing this to our attention, {name}. We take every review seriously and would appreciate the chance to resolve this. Please reach out to us at {phone}.",
    ],
}

CTA_COPY_TEMPLATES = [
    "📞 Call Now for a Free Estimate — Same-Day Service Available!",
    "🔧 Book Your {service} Online in 60 Seconds",
    "💰 Get Your Free Quote — No Obligation, No Hassle",
    "📅 Schedule Now & Save 10% on Your First Service Call",
]

OUTREACH_EMAIL_TEMPLATE = """Subject: Quick question about your visibility in {city}

Hi {owner_name},

I was looking at the local service rankings for {niche} in {city} today and noticed {business_name} has a Health Score of {health_score}/100.

**Key Findings:**
- Your {strongest_pillar} is strong, but your {weakest_pillar} signals are currently flagged as a priority fix.
- Specifically, {specific_gap}, which typically causes a significant drop in local leads.

I've put together a 1-page roadmap of how to fix these {action_count} items. Would you be open to a 10-minute "no-pitch" call later this week to walk through the data?

Best,
LocalPulse AI
"""

LANDING_PAGE_HEADLINES = [
    "Trusted {niche} Services in {city} — {reviews}+ Happy Customers",
    "#1 Rated {niche} in {city} — Free Estimates & Same-Day Service",
    "Your Local {niche} Experts in {city} — Call {phone} Today",
]

META_DESCRIPTION_TEMPLATE = (
    "Looking for {niche} in {city}? {business_name} offers "
    "{services} with {reviews}+ 5-star reviews. "
    "Call {phone} today for a free estimate!"
)

GBP_DESCRIPTION_TEMPLATE = (
    "{business_name} is your trusted local {niche} in {city}. "
    "We specialize in {services} and are committed to delivering "
    "fast, reliable service with transparent pricing. "
    "Call {phone} or book online today!"
)


# ── Builder Agent ────────────────────────────────────────────────────────────

class BuilderAgent:
    """Builder agent generates draft deliverables from a completed snapshot."""

    def run_once(self) -> Optional[str]:
        """Poll for a completed snapshot and generate draft deliverables.

        Returns the processed snapshot ID or None if no work.
        """
        snapshot = claim_next_snapshot("completed", "ready_for_outreach")
        if snapshot is None:
            logger.debug("No completed snapshots to build")
            return None

        snap_id = snapshot["id"]
        data = snapshot.get("data", {}) or {}
        business_info = data.get("business_info", {})
        scout_data = data.get("scout_data", {})
        insights = data.get("analyzer_insights", {})
        scoring = data.get("scoring_output", {})
        roadmap = data.get("growth_roadmap", [])
        name = business_info.get("name", snapshot["business_name"])

        logger.info(f"Building deliverables for: {name}")

        try:
            deliverables = self._generate_deliverables(
                business_info=business_info,
                scout_data=scout_data,
                insights=insights,
                scoring=scoring,
                roadmap=roadmap,
            )
            update_snapshot_data(snap_id, "draft_deliverables", deliverables)
            logger.info(
                f"Builder complete for {name}: "
                f"{len(deliverables.get('items', []))} deliverables generated"
            )
            return snap_id

        except Exception as e:
            logger.error(f"Builder failed for {name}: {e}")
            update_snapshot_status(snap_id, "failed")
            return None

    def _generate_deliverables(
        self,
        business_info: dict[str, Any],
        scout_data: dict[str, Any],
        insights: dict[str, Any],
        scoring: dict[str, Any],
        roadmap: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate all draft deliverables based on the roadmap."""
        items: list[dict[str, Any]] = []
        name = business_info.get("name", "Your Business")
        location = business_info.get("location", "your city")
        city = location.split(",")[0].strip() if "," in location else location
        website = business_info.get("website", "")

        gbp = scout_data.get("gbp", {})
        website_data = scout_data.get("website", {})
        reviews_data = scout_data.get("reviews", {})
        reviews = reviews_data.get("reviews", []) if isinstance(reviews_data, dict) else reviews_data

        gaps = insights.get("gaps", [])
        benchmark = insights.get("benchmark_comparison", {})
        weakest = benchmark.get("weakest_pillar", "conversion")
        strongest = benchmark.get("strongest_pillar", "trust")
        health_score = scoring.get("total_health_score", 0)

        # Infer niche from categories or gaps
        niche = self._infer_niche(gbp, gaps)
        services = self._infer_services(niche)

        # Extract phone from website or use placeholder
        phones = website_data.get("phone_numbers", [])
        phone = phones[0] if phones else "(555) 123-4567"

        # Count reviews
        review_count = gbp.get("review_count") or (reviews_data.get("review_count") if isinstance(reviews_data, dict) else 0) or 0

        # ── Generate review reply drafts ───────────────────────────────────
        review_replies = self._generate_review_replies(name, reviews, phone)
        if review_replies:
            items.append({
                "type": "review_replies",
                "title": "Draft Review Replies",
                "description": "Ready-to-use responses for your recent reviews.",
                "content": review_replies,
            })

        # ── Generate SEO meta description ──────────────────────────────────
        if any("seo" in (g or "").lower() or "local" in (g or "").lower() or "visibility" in (g or "").lower() for g in gaps):
            meta_desc = META_DESCRIPTION_TEMPLATE.format(
                niche=niche,
                city=city,
                business_name=name,
                services=services,
                reviews=review_count if review_count else "100+",
                phone=phone,
            )
            items.append({
                "type": "seo_meta_description",
                "title": "Suggested Meta Description",
                "description": "Optimized for local search visibility.",
                "content": meta_desc,
            })

        # ── Generate GBP description ───────────────────────────────────────
        if any("gbp" in (g or "").lower() or "google business" in (g or "").lower() for g in gaps):
            gbp_desc = GBP_DESCRIPTION_TEMPLATE.format(
                business_name=name,
                niche=niche,
                city=city,
                services=services,
                phone=phone,
            )
            items.append({
                "type": "gbp_description",
                "title": "Suggested GBP Description",
                "description": "Optimized for Google Business Profile.",
                "content": gbp_desc,
            })

        # ── Generate CTA copy suggestions ──────────────────────────────────
        if any("cta" in (g or "").lower() or "booking" in (g or "").lower() or "conversion" in (g or "").lower() for g in gaps):
            cta_copies = [t.format(service=services.split(" and ")[0]) for t in CTA_COPY_TEMPLATES]
            items.append({
                "type": "cta_copy",
                "title": "Suggested Call-to-Action Copy",
                "description": "High-conversion CTAs for your website and ads.",
                "content": cta_copies,
            })

        # ── Generate landing page headlines ────────────────────────────────
        if any("conversion" in (g or "").lower() or "website" in (g or "").lower() for g in gaps):
            headlines = [
                h.format(niche=niche, city=city, reviews=review_count if review_count else "100+", phone=phone)
                for h in LANDING_PAGE_HEADLINES
            ]
            items.append({
                "type": "landing_page_headlines",
                "title": "Suggested Landing Page Headlines",
                "description": "Headlines optimized for local search and conversions.",
                "content": headlines,
            })

        # ── Generate outreach email draft ──────────────────────────────────
        # Find a specific gap for the email hook
        specific_gap = gaps[0] if gaps else "your online presence could be stronger"
        email = OUTREACH_EMAIL_TEMPLATE.format(
            city=city,
            niche=niche,
            owner_name="there",
            business_name=name,
            health_score=health_score,
            strongest_pillar=strongest.title(),
            weakest_pillar=weakest.title(),
            specific_gap=specific_gap,
            action_count=len(roadmap),
        )
        items.append({
            "type": "outreach_email",
            "title": "Personalized Outreach Email Draft",
            "description": "Ready-to-send email based on your Business Health Snapshot.",
            "content": email,
        })

        # ── Generate action-specific copy ──────────────────────────────────
        for action in roadmap[:3]:  # Top 3 actions
            action_text = action.get("action", "").lower()
            if "review" in action_text:
                items.append({
                    "type": "action_tip",
                    "title": "Tip: Review Generation",
                    "description": "How to ask for reviews without feeling pushy.",
                    "content": (
                        f"Send a follow-up text within 24 hours of service completion: "
                        f"'Hi [Name], thanks for choosing {name}! If you were happy with our work, "
                        f"would you mind leaving us a quick review? It helps other {city} homeowners find us. "
                        f"[Link to GBP reviews]'"
                    ),
                })
            elif "mobile" in action_text:
                items.append({
                    "type": "action_tip",
                    "title": "Tip: Mobile Optimization",
                    "description": "Quick wins for mobile UX.",
                    "content": (
                        "1. Add a sticky 'Call Now' button at the bottom of the mobile screen.\n"
                        "2. Reduce image sizes to under 200KB each.\n"
                        "3. Use a single-column layout on all mobile pages.\n"
                        "4. Test your site on multiple devices using Chrome DevTools."
                    ),
                })
            elif "booking" in action_text:
                items.append({
                    "type": "action_tip",
                    "title": "Tip: Booking Flow",
                    "description": "How to add instant booking to your site.",
                    "content": (
                        "Consider integrating Calendly, Housecall Pro, or Jobber. "
                        "Place the booking widget above the fold on your homepage and "
                        "add a 'Book Online' button to your Google Business Profile."
                    ),
                })
            elif "category" in action_text:
                items.append({
                    "type": "action_tip",
                    "title": "Tip: GBP Categories",
                    "description": "Best practices for GBP category selection.",
                    "content": (
                        f"Set your primary category to '{niche} Contractor' and add "
                        f"secondary categories like '{services} Service', 'Emergency Service', "
                        f"and 'Home Improvement'. Review competitors in {city} for ideas."
                    ),
                })

        return {
            "business_name": name,
            "city": city,
            "generated_count": len(items),
            "items": items,
        }

    @staticmethod
    def _generate_review_replies(
        business_name: str,
        reviews: list[dict[str, Any]],
        phone: str,
    ) -> list[dict[str, Any]]:
        """Generate draft replies for available reviews."""
        if not reviews:
            return []

        replies = []
        for review in reviews[:3]:  # Max 3 review replies
            text = review.get("text", "")
            rating = review.get("rating", 3)
            reviewer_name = review.get("author", "there")

            if rating >= 4:
                sentiment = "positive"
            elif rating >= 3:
                sentiment = "neutral"
            else:
                sentiment = "negative"

            template = REVIEW_REPLY_TEMPLATES[sentiment][0]
            reply = template.format(name=reviewer_name, phone=phone)

            replies.append({
                "original_review": text,
                "rating": rating,
                "draft_reply": reply,
                "sentiment": sentiment,
            })

        return replies

    @staticmethod
    def _infer_niche(gbp: dict[str, Any], gaps: list[str]) -> str:
        """Infer business niche from categories or gap text."""
        categories = gbp.get("categories", [])
        if categories:
            primary = categories[0]
            # Strip "Contractor", "Business", etc.
            return primary.replace(" Contractor", "").replace(" Business", "").lower()

        gap_text = " ".join(gaps).lower()
        for niche in ["hvac", "plumbing", "electrical", "roofing", "garage door", "pest control"]:
            if niche in gap_text:
                return niche
        return "home services"

    @staticmethod
    def _infer_services(niche: str) -> str:
        """Map niche to typical services."""
        mapping = {
            "hvac": "heating and cooling",
            "plumbing": "plumbing repair and installation",
            "electrical": "electrical repair and installation",
            "roofing": "roof repair and replacement",
            "garage door": "garage door repair and installation",
            "pest control": "pest control and extermination",
            "home services": "home repair and maintenance",
        }
        return mapping.get(niche, "home repair and maintenance")


# ── Pipeline Helpers ─────────────────────────────────────────────────────────

def run_builder_pipeline(max_iterations: int = 10) -> int:
    """Run the builder agent in a loop.

    Returns the number of snapshots processed.
    """
    builder = BuilderAgent()
    processed = 0
    for _ in range(max_iterations):
        result = builder.run_once()
        if result is None:
            break
        processed += 1
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = run_builder_pipeline()
    print(f"Processed {count} snapshots")
