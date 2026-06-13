"""Analyzer Agent — Data Processing

Responsibility: Convert raw scout data into structured insights.
Tasks:
  - Sentiment analysis of reviews
  - Identification of review gaps (e.g., "no recent reviews")
  - Detection of website features (booking forms, mobile responsiveness, local SEO)
  - GBP completeness and optimization analysis
  - Competitor benchmarking
Output: Categorized insights (Visibility, Trust, Conversion) with specific, actionable gaps.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.database import (
    claim_next_snapshot,
    update_snapshot_data,
    update_snapshot_status,
)

logger = logging.getLogger(__name__)


# ── Benchmarks & Thresholds ──────────────────────────────────────────────────

class Benchmarks:
    """Industry benchmarks for local service businesses."""

    # Review benchmarks
    REVIEW_VOLUME_EXCELLENT = 100
    REVIEW_VOLUME_GOOD = 50
    REVIEW_VOLUME_MINIMUM = 10
    REVIEW_RECENCY_DAYS = 90  # reviews within last 90 days = recent

    # Website benchmarks
    LOAD_TIME_EXCELLENT_MS = 2000
    LOAD_TIME_GOOD_MS = 4000
    LOAD_TIME_POOR_MS = 6000

    # GBP benchmarks
    GBP_PHOTOS_EXCELLENT = 50
    GBP_PHOTOS_GOOD = 20
    GBP_PHOTOS_MINIMUM = 10
    GBP_CATEGORIES_RECOMMENDED = 3

    # Score thresholds
    SCORE_EXCELLENT = 80
    SCORE_GOOD = 60
    SCORE_NEEDS_WORK = 40
    SCORE_CRITICAL = 20


# ── Analyzer Agent ───────────────────────────────────────────────────────────

class AnalyzerAgent:
    """Analyzer agent processes raw scout data into structured insights."""

    def run_once(self) -> Optional[str]:
        """Poll for a scout_done snapshot and analyze it.

        Returns the processed snapshot ID or None if no work.
        """
        snapshot = claim_next_snapshot("scout_done", "analyzer_done")
        if snapshot is None:
            logger.debug("No scout_done snapshots to analyze")
            return None

        snap_id = snapshot["id"]
        data = snapshot.get("data", {}) or {}
        business_info = data.get("business_info", {})
        scout_data = data.get("scout_data", {})
        name = business_info.get("name", snapshot["business_name"])

        logger.info(f"Analyzing: {name}")

        try:
            insights = self._analyze(scout_data)
            update_snapshot_data(snap_id, "analyzer_insights", insights)
            logger.info(f"Analysis complete for {name} (id={snap_id})")
            return snap_id

        except Exception as e:
            logger.error(f"Analysis failed for {name}: {e}")
            update_snapshot_status(snap_id, "failed")
            return None

    def _analyze(self, scout_data: dict[str, Any]) -> dict[str, Any]:
        """Transform raw scout data into structured insights."""
        gbp = scout_data.get("gbp", {})
        website = scout_data.get("website", {})
        reviews_data = scout_data.get("reviews", {})
        reviews = reviews_data.get("reviews", []) if isinstance(reviews_data, dict) else reviews_data

        gaps = []

        # ── Trust Analysis ───────────────────────────────────────────────────
        trust_analysis = self._analyze_trust(gbp, reviews)
        gaps.extend(trust_analysis["gaps"])

        # ── Visibility Analysis ──────────────────────────────────────────────
        visibility_analysis = self._analyze_visibility(gbp, website)
        gaps.extend(visibility_analysis["gaps"])

        # ── Conversion Analysis ──────────────────────────────────────────────
        conversion_analysis = self._analyze_conversion(website)
        gaps.extend(conversion_analysis["gaps"])

        # ── Sentiment Analysis ───────────────────────────────────────────────
        sentiment_summary = self._analyze_sentiment(reviews)

        # ── Competitor Benchmarking ──────────────────────────────────────────
        benchmark_comparison = self._benchmark_comparison(
            trust_analysis["score"],
            visibility_analysis["score"],
            conversion_analysis["score"],
        )

        return {
            "trust_score_raw": round(trust_analysis["score"], 1),
            "visibility_score_raw": round(visibility_analysis["score"], 1),
            "conversion_score_raw": round(conversion_analysis["score"], 1),
            "gaps": gaps,
            "sentiment_summary": sentiment_summary,
            "trust_details": trust_analysis["details"],
            "visibility_details": visibility_analysis["details"],
            "conversion_details": conversion_analysis["details"],
            "benchmark_comparison": benchmark_comparison,
        }

    # ── Trust Analysis ───────────────────────────────────────────────────────

    def _analyze_trust(
        self,
        gbp: dict[str, Any],
        reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze trust signals: rating, review volume, recency, sentiment."""
        score = 0.0
        max_score = 0.0
        gaps = []
        details: dict[str, Any] = {}

        # Rating component (max 40 points)
        rating = gbp.get("rating")
        if rating is not None:
            score += (rating / 5.0) * 40
            details["rating"] = rating
            details["rating_status"] = self._rating_status(rating)
            if rating < 4.0:
                gaps.append("Low average rating — below 4.0 stars")
        else:
            gaps.append("Missing GBP rating data")
            details["rating"] = None
            details["rating_status"] = "unknown"
        max_score += 40

        # Review volume component (max 30 points)
        review_count = gbp.get("review_count")
        if review_count is not None:
            # Log scale: 0 reviews = 0, 100+ reviews = max
            volume_score = min(review_count / Benchmarks.REVIEW_VOLUME_EXCELLENT, 1.0) * 30
            score += volume_score
            details["review_count"] = review_count
            if review_count < Benchmarks.REVIEW_VOLUME_MINIMUM:
                gaps.append(f"Low review volume — fewer than {Benchmarks.REVIEW_VOLUME_MINIMUM} reviews")
            elif review_count < Benchmarks.REVIEW_VOLUME_GOOD:
                gaps.append("Moderate review volume — aim for 50+ reviews")
        else:
            gaps.append("Missing review count data")
            details["review_count"] = None
        max_score += 30

        # Review recency component (max 20 points)
        recent_reviews = self._count_recent_reviews(reviews)
        if recent_reviews > 0:
            recency_score = min(recent_reviews / 5, 1.0) * 20
            score += recency_score
            details["recent_reviews"] = recent_reviews
            if recent_reviews < 3:
                gaps.append("No reviews in the last 30 days")
        else:
            if reviews:
                gaps.append("No recent reviews found — last review is over 90 days old")
            else:
                gaps.append("No reviews found")
            details["recent_reviews"] = 0
        max_score += 20

        # Review response component (max 10 points)
        # We can't directly measure response rate from public data,
        # but we can estimate based on review patterns
        details["estimated_response_rate"] = None
        max_score += 10

        # Normalize score
        normalized = (score / max_score * 100) if max_score > 0 else 0

        return {
            "score": normalized,
            "gaps": gaps,
            "details": details,
        }

    @staticmethod
    def _rating_status(rating: float) -> str:
        if rating >= 4.5:
            return "excellent"
        elif rating >= 4.0:
            return "good"
        elif rating >= 3.0:
            return "needs_improvement"
        return "critical"

    @staticmethod
    def _count_recent_reviews(reviews: list[dict[str, Any]], days: int = 30) -> int:
        """Count reviews within the last N days."""
        if not reviews:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = 0
        for review in reviews:
            date_str = review.get("date", "")
            if date_str:
                try:
                    # Try ISO format first
                    review_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if review_date >= cutoff:
                        recent += 1
                except (ValueError, TypeError):
                    # Try other common formats
                    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
                        try:
                            review_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                            if review_date >= cutoff:
                                recent += 1
                            break
                        except ValueError:
                            continue
        return recent

    # ── Visibility Analysis ──────────────────────────────────────────────────

    def _analyze_visibility(
        self,
        gbp: dict[str, Any],
        website: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze visibility signals: GBP completeness, categories, local SEO."""
        score = 0.0
        max_score = 0.0
        gaps = []
        details: dict[str, Any] = {}

        # GBP completeness (max 40 points)
        gbp_fields = 0
        gbp_checks = {
            "rating": gbp.get("rating") is not None,
            "review_count": gbp.get("review_count") is not None,
            "categories": bool(gbp.get("categories")),
            "has_booking_link": gbp.get("has_booking_link") is not None,
            "photos_count": gbp.get("photos_count") is not None,
        }
        for field, present in gbp_checks.items():
            if present:
                gbp_fields += 1

        completeness_score = (gbp_fields / len(gbp_checks)) * 40
        score += completeness_score
        details["gbp_completeness"] = {
            "score": completeness_score,
            "fields_present": gbp_fields,
            "fields_total": len(gbp_checks),
            "checks": gbp_checks,
        }
        if gbp_fields < 3:
            gaps.append("Incomplete Google Business Profile — fill in all fields")
        max_score += 40

        # Categories (max 25 points)
        categories = gbp.get("categories", [])
        if categories:
            cat_score = min(len(categories) / Benchmarks.GBP_CATEGORIES_RECOMMENDED, 1.0) * 25
            score += cat_score
            details["categories"] = categories
            details["category_count"] = len(categories)
            if len(categories) < Benchmarks.GBP_CATEGORIES_RECOMMENDED:
                gaps.append("Missing relevant secondary categories")
        else:
            gaps.append("No GBP categories set")
            details["categories"] = []
            details["category_count"] = 0
        max_score += 25

        # Booking link on GBP (max 15 points)
        has_booking_link = gbp.get("has_booking_link")
        if has_booking_link is True:
            score += 15
            details["has_booking_link"] = True
        else:
            if has_booking_link is False:
                gaps.append("GBP profile lacks a 'Book Online' button")
            else:
                gaps.append("No booking link on Google Business Profile")
            details["has_booking_link"] = has_booking_link
        max_score += 15

        # Photos on GBP (max 10 points)
        photos_count = gbp.get("photos_count")
        if photos_count is not None:
            photo_score = min(photos_count / Benchmarks.GBP_PHOTOS_EXCELLENT, 1.0) * 10
            score += photo_score
            details["photos_count"] = photos_count
            if photos_count < Benchmarks.GBP_PHOTOS_MINIMUM:
                gaps.append(f"Fewer than {Benchmarks.GBP_PHOTOS_MINIMUM} photos on GBP")
        else:
            details["photos_count"] = None
        max_score += 10

        # Local SEO from website (max 10 points)
        local_seo_score, local_seo_gaps = self._analyze_local_seo(website)
        score += local_seo_score
        gaps.extend(local_seo_gaps)
        details["local_seo_score"] = local_seo_score
        max_score += 10

        normalized = (score / max_score * 100) if max_score > 0 else 0

        return {
            "score": normalized,
            "gaps": gaps,
            "details": details,
        }

    def _analyze_local_seo(self, website: dict[str, Any]) -> tuple[float, list[str]]:
        """Analyze local SEO signals on the website."""
        score = 0.0
        gaps = []

        schema = website.get("schema_org", {})
        has_localbusiness_schema = "local_business" in schema

        if has_localbusiness_schema:
            score += 5
        else:
            gaps.append("Website missing LocalBusiness schema.org markup")

        # Check for city/location in page title or meta description
        title = website.get("page_title", "")
        meta_desc = website.get("meta_description", "")
        combined_text = f"{title} {meta_desc}".lower()

        # Heuristic: if we have addresses extracted, that's good for local SEO
        addresses = website.get("addresses", [])
        if addresses:
            score += 3
        else:
            gaps.append("Website or GBP description lacks city-specific mentions")

        # Check for phone numbers (NAP signal)
        phones = website.get("phone_numbers", [])
        if phones:
            score += 2
        else:
            gaps.append("No phone number detected on website")

        return score, gaps

    # ── Conversion Analysis ──────────────────────────────────────────────────

    def _analyze_conversion(self, website: dict[str, Any]) -> dict[str, Any]:
        """Analyze conversion signals: mobile UX, booking forms, CTAs, speed."""
        score = 0.0
        max_score = 0.0
        gaps = []
        details: dict[str, Any] = {}

        # Mobile friendliness (max 30 points)
        mobile = website.get("is_mobile_friendly")
        if mobile is True:
            score += 30
            details["mobile_friendly"] = True
            details["mobile_status"] = "pass"
        elif mobile is False:
            gaps.append("Website is not mobile-friendly")
            details["mobile_friendly"] = False
            details["mobile_status"] = "fail"
        else:
            gaps.append("Unable to verify mobile responsiveness")
            details["mobile_friendly"] = None
            details["mobile_status"] = "unknown"
        max_score += 30

        # Page load time (max 20 points)
        load_time = website.get("load_time_ms")
        if load_time is not None:
            details["load_time_ms"] = load_time
            if load_time <= Benchmarks.LOAD_TIME_EXCELLENT_MS:
                score += 20
                details["load_status"] = "excellent"
            elif load_time <= Benchmarks.LOAD_TIME_GOOD_MS:
                score += 15
                details["load_status"] = "good"
            elif load_time <= Benchmarks.LOAD_TIME_POOR_MS:
                score += 8
                details["load_status"] = "slow"
                gaps.append("Mobile load time > 4 seconds")
            else:
                details["load_status"] = "very_slow"
                gaps.append("Website loads very slowly — over 6 seconds")
        else:
            gaps.append("Unable to measure website load time")
            details["load_time_ms"] = None
            details["load_status"] = "unknown"
        max_score += 20

        # Booking form (max 25 points)
        has_booking = website.get("has_booking_form")
        if has_booking is True:
            score += 25
            details["has_booking_form"] = True
            details["booking_status"] = "present"
        elif has_booking is False:
            gaps.append("Website uses a static contact form instead of real-time scheduling")
            details["has_booking_form"] = False
            details["booking_status"] = "missing"
        else:
            gaps.append("Unable to detect booking form on website")
            details["has_booking_form"] = None
            details["booking_status"] = "unknown"
        max_score += 25

        # CTA count (max 15 points)
        cta_count = website.get("cta_count", 0)
        if cta_count is not None:
            cta_score = min(cta_count / 3, 1.0) * 15
            score += cta_score
            details["cta_count"] = cta_count
            if cta_count == 0:
                gaps.append("No Calls-to-Action found on website")
            elif cta_count < 2:
                gaps.append("Only one CTA found — add more throughout the page")
        else:
            gaps.append("Unable to analyze website CTAs")
            details["cta_count"] = None
        max_score += 15

        # HTTPS / Security (max 10 points)
        url = website.get("url", "")
        if url.startswith("https://"):
            score += 10
            details["https"] = True
        elif url.startswith("http://"):
            gaps.append("Website not using HTTPS — security warning may deter customers")
            details["https"] = False
        else:
            details["https"] = None
        max_score += 10

        normalized = (score / max_score * 100) if max_score > 0 else 0

        return {
            "score": normalized,
            "gaps": gaps,
            "details": details,
        }

    # ── Sentiment Analysis ───────────────────────────────────────────────────

    def _analyze_sentiment(self, reviews: list[dict[str, Any]]) -> dict[str, Any]:
        """Produce a detailed sentiment summary from review data."""
        if not reviews:
            return {
                "overall": "No reviews available for sentiment analysis",
                "polarity": None,
                "confidence": None,
                "themes": [],
            }

        scores = []
        rating_scores = []
        texts = []

        for review in reviews:
            text = review.get("text", "")
            rating = review.get("rating")
            if text.strip():
                texts.append(text)
            if rating is not None:
                rating_scores.append((rating - 3) / 2)

        # Try TextBlob for text-based sentiment
        text_sentiments = []
        try:
            from textblob import TextBlob
            for text in texts:
                if text.strip():
                    blob = TextBlob(text)
                    text_sentiments.append(blob.sentiment.polarity)
        except ImportError:
            pass

        # Combine text sentiment with rating-based sentiment
        if text_sentiments:
            scores = text_sentiments
        elif rating_scores:
            scores = rating_scores
        else:
            scores = [0]

        avg = sum(scores) / len(scores)

        if avg > 0.3:
            overall = "Positive"
        elif avg < -0.3:
            overall = "Negative"
        else:
            overall = "Mixed"

        # Extract simple themes (positive/negative keywords)
        themes = self._extract_themes(texts)

        return {
            "overall": overall,
            "polarity": round(avg, 2),
            "confidence": round(min(len(scores) / 10, 1.0), 2),
            "themes": themes,
            "review_count": len(reviews),
        }

    @staticmethod
    def _extract_themes(texts: list[str]) -> list[dict[str, str]]:
        """Extract recurring themes from review texts."""
        if not texts:
            return []

        positive_keywords = [
            "professional", "fast", "quick", "reliable", "friendly",
            "great", "excellent", "amazing", "best", "recommend",
            "affordable", "fair price", "clean", "punctual", "on time",
        ]
        negative_keywords = [
            "slow", "late", "rude", "expensive", "overpriced",
            "unprofessional", "dirty", "messy", "never again",
            "disappointing", "poor", "terrible", "worst",
        ]

        positive_hits = []
        negative_hits = []

        all_text = " ".join(texts).lower()
        for kw in positive_keywords:
            if kw in all_text:
                positive_hits.append(kw)
        for kw in negative_keywords:
            if kw in all_text:
                negative_hits.append(kw)

        themes = []
        if positive_hits:
            themes.append({"type": "positive", "words": positive_hits[:5]})
        if negative_hits:
            themes.append({"type": "negative", "words": negative_hits[:5]})

        return themes

    # ── Competitor Benchmarking ──────────────────────────────────────────────

    def _benchmark_comparison(
        self,
        trust_score: float,
        visibility_score: float,
        conversion_score: float,
    ) -> dict[str, Any]:
        """Compare scores against industry benchmarks."""
        scores = {
            "trust": trust_score,
            "visibility": visibility_score,
            "conversion": conversion_score,
        }

        comparison = {}
        for pillar, score in scores.items():
            if score >= Benchmarks.SCORE_EXCELLENT:
                status = "excellent"
                percentile = "top 10%"
            elif score >= Benchmarks.SCORE_GOOD:
                status = "good"
                percentile = "top 25%"
            elif score >= Benchmarks.SCORE_NEEDS_WORK:
                status = "average"
                percentile = "top 50%"
            elif score >= Benchmarks.SCORE_CRITICAL:
                status = "below_average"
                percentile = "bottom 50%"
            else:
                status = "critical"
                percentile = "bottom 25%"

            comparison[pillar] = {
                "score": round(score, 1),
                "status": status,
                "percentile_estimate": percentile,
                "gap_to_excellent": round(max(Benchmarks.SCORE_EXCELLENT - score, 0), 1),
            }

        # Identify weakest pillar
        comparison_scores = {k: v for k, v in comparison.items() if isinstance(v, dict) and "score" in v}
        weakest = min(comparison_scores, key=lambda k: comparison_scores[k]["score"])
        comparison["weakest_pillar"] = weakest
        comparison["strongest_pillar"] = max(comparison_scores, key=lambda k: comparison_scores[k]["score"])

        return comparison


# ── Pipeline Helpers ─────────────────────────────────────────────────────────

def run_analyzer_pipeline(max_iterations: int = 10) -> int:
    """Run the analyzer agent in a loop.

    Returns the number of snapshots processed.
    """
    analyzer = AnalyzerAgent()
    processed = 0
    for _ in range(max_iterations):
        result = analyzer.run_once()
        if result is None:
            break
        processed += 1
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = run_analyzer_pipeline()
    print(f"Processed {count} snapshots")
