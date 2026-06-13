"""Scout Agent — Data Acquisition & Lead Discovery

Responsibility:
  1. DISCOVER businesses in a target city/niche via web search.
  2. ENRICH pending snapshots by scraping public data:
     - Website (speed, mobile, CTAs, booking forms, schema.org)
     - Google Business Profile signals (via search + structured data)
     - Reviews (from website testimonials + aggregate ratings)
  3. UPDATE the shared database and advance pipeline status.

External APIs are not required; the agent uses polite HTTP scraping
with rotating user-agents and clear `simulated` flags when data is
inferred rather than directly observed.
"""

import json
import logging
import random
import re
import time
import uuid
from typing import Any, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.database import (
    claim_next_snapshot,
    create_snapshot,
    get_snapshot,
    update_snapshot_data,
    update_snapshot_status,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

BOOKING_KEYWORDS = [
    "book", "schedule", "appointment", "reserve", "quote", "contact",
    "request service", "get estimate", "free estimate", "call now",
]

CTA_KEYWORDS = [
    "get started", "call now", "book now", "free quote", "schedule",
    "request estimate", "get a quote", "contact us", "call today",
]

# ── Business Discovery ───────────────────────────────────────────────────────

class BusinessDiscovery:
    """Discover local service businesses via public search engines.

    Uses DuckDuckGo HTML search (more scraper-friendly than Google)
    and falls back to Google if needed.  Results are parsed into
    structured business records ready for snapshot creation.
    """

    def __init__(self, timeout: int = 30, delay: float = 1.5):
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        self._rotate_ua()

    def _rotate_ua(self):
        self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

    def search(self, niche: str, city: str, state: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Return a list of discovered businesses.

        Each record contains at least: name, website, location, gbp_url (optional).
        """
        query = f"{niche} {city} {state}"
        results: list[dict[str, Any]] = []

        # Try DuckDuckGo first
        ddg_results = self._search_duckduckgo(query, max_results=max_results)
        results.extend(ddg_results)

        # Deduplicate by domain
        seen_domains = set()
        deduped = []
        for r in results:
            domain = self._domain(r.get("website", ""))
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                deduped.append(r)

        return deduped[:max_results]

    def _search_duckduckgo(self, query: str, max_results: int) -> list[dict[str, Any]]:
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}
        businesses = []
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for result in soup.select(".result"):
                link_tag = result.select_one(".result__a")
                if not link_tag:
                    continue
                href = link_tag.get("href", "")
                if href.startswith("//"):
                    href = "https:" + href
                # Skip directories like Yelp, Angi, HomeAdvisor — we want direct business sites
                if self._is_directory(href):
                    continue
                title = link_tag.get_text(strip=True)
                snippet_tag = result.select_one(".result__snippet")
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                businesses.append({
                    "name": self._clean_name(title),
                    "website": href,
                    "location": "",  # populated later if possible
                    "source": "duckduckgo",
                    "snippet": snippet,
                })
                if len(businesses) >= max_results:
                    break
            time.sleep(self.delay)
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
        return businesses

    def _is_directory(self, url: str) -> bool:
        domain = self._domain(url)
        directories = {
            "yelp.com", "angi.com", "homeadvisor.com", "thumbtack.com",
            "bbb.org", "porch.com", "buildzoom.com", "houzz.com",
            "facebook.com", "linkedin.com", "yellowpages.com",
        }
        return any(d in domain for d in directories)

    @staticmethod
    def _domain(url: str) -> str:
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return ""

    @staticmethod
    def _clean_name(title: str) -> str:
        # Remove common suffixes/prefixes
        title = re.sub(r"\s*[-|]\s*.*", "", title)
        title = re.sub(r"\s+(LLC|Inc|Corp|Ltd)\.?", "", title, flags=re.IGNORECASE)
        return title.strip()


# ── Website Scraper ──────────────────────────────────────────────────────────

class WebsiteScraper:
    """Extract business signals from a company website."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

    def scrape(self, url: str) -> dict[str, Any]:
        """Return a dict of website signals."""
        result: dict[str, Any] = {
            "url": url,
            "load_time_ms": None,
            "is_mobile_friendly": None,
            "has_booking_form": None,
            "cta_count": None,
            "schema_org": {},
            "page_title": None,
            "meta_description": None,
            "phone_numbers": [],
            "addresses": [],
        }

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            start = time.time()
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            load_time = int((time.time() - start) * 1000)
            result["load_time_ms"] = load_time

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                result.update(self._analyze_soup(soup, url))
        except Exception as e:
            logger.warning(f"Website scrape failed for {url}: {e}")

        return result

    def _analyze_soup(self, soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
        out: dict[str, Any] = {}

        # Mobile friendliness
        viewport = soup.find("meta", attrs={"name": "viewport"})
        out["is_mobile_friendly"] = viewport is not None

        # Page title & meta description
        title_tag = soup.find("title")
        out["page_title"] = title_tag.get_text(strip=True) if title_tag else None
        meta_desc = soup.find("meta", attrs={"name": "description"})
        out["meta_description"] = meta_desc.get("content", "").strip() if meta_desc else ""

        # Booking / contact form detection
        all_text = soup.get_text(separator=" ", strip=True).lower()
        out["has_booking_form"] = any(kw in all_text for kw in BOOKING_KEYWORDS)

        # CTA count
        visible_texts = [t.strip().lower() for t in soup.stripped_strings]
        out["cta_count"] = sum(
            1 for text in visible_texts if any(kw in text for kw in CTA_KEYWORDS)
        )

        # Schema.org JSON-LD extraction
        out["schema_org"] = self._extract_schema_org(soup)

        # Phone numbers
        out["phone_numbers"] = self._extract_phones(soup)

        # Addresses
        out["addresses"] = self._extract_addresses(soup)

        return out

    def _extract_schema_org(self, soup: BeautifulSoup) -> dict[str, Any]:
        schemas: dict[str, Any] = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict):
                    types = [data.get("@type")]
                elif isinstance(data, list):
                    types = [d.get("@type") for d in data if isinstance(d, dict)]
                else:
                    continue
                for t in types:
                    if t in ("LocalBusiness", "HVACBusiness", "Plumber", "Electrician", "RoofingContractor", "AutoRepair", "ProfessionalService"):
                        schemas["local_business"] = data if isinstance(data, dict) else data[0]
                    elif t == "AggregateRating":
                        schemas["aggregate_rating"] = data if isinstance(data, dict) else data[0]
            except Exception:
                continue
        return schemas

    def _extract_phones(self, soup: BeautifulSoup) -> list[str]:
        text = soup.get_text()
        # North American phone pattern
        pattern = re.compile(r"\(?\b[0-9]{3}\)?[-. ]?[0-9]{3}[-. ]?[0-9]{4}\b")
        return list(set(pattern.findall(text)))

    def _extract_addresses(self, soup: BeautifulSoup) -> list[str]:
        # Very basic heuristic — look for schema address or text blocks with numbers + street words
        addrs = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict):
                    addr = data.get("address", {})
                    if isinstance(addr, dict):
                        street = addr.get("streetAddress", "")
                        city = addr.get("addressLocality", "")
                        state = addr.get("addressRegion", "")
                        if street:
                            addrs.append(f"{street}, {city}, {state}".strip(", "))
            except Exception:
                continue
        return addrs


# ── Review Scraper ───────────────────────────────────────────────────────────

class ReviewScraper:
    """Collect review-like data from public web sources.

    In production this would integrate with Google Business Profile API,
    Yelp Fusion API, etc.  For now we extract testimonials and aggregate
    ratings from the business website and mark simulated data clearly.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

    def scrape(self, name: str, website: str = "", location: str = "") -> dict[str, Any]:
        """Return review data with a `simulated` honesty flag."""
        reviews: list[dict[str, Any]] = []
        aggregate_rating: Optional[float] = None
        review_count: Optional[int] = None

        # Try to pull from website schema
        if website:
            try:
                resp = self.session.get(website, timeout=self.timeout)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    for script in soup.find_all("script", type="application/ld+json"):
                        try:
                            data = json.loads(script.string or "")
                            items = data if isinstance(data, list) else [data]
                            for item in items:
                                rating = item.get("aggregateRating", {}).get("ratingValue")
                                count = item.get("aggregateRating", {}).get("reviewCount")
                                if rating is not None:
                                    aggregate_rating = float(rating)
                                if count is not None:
                                    review_count = int(count)
                                # Individual reviews in schema
                                for rev in item.get("review", []):
                                    reviews.append({
                                        "text": rev.get("reviewBody", ""),
                                        "rating": rev.get("reviewRating", {}).get("ratingValue"),
                                        "date": rev.get("datePublished", ""),
                                        "source": "website_schema",
                                    })
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Review scrape from website failed: {e}")

        # If we have no reviews, we return an empty list but preserve the structure
        return {
            "reviews": reviews,
            "aggregate_rating": aggregate_rating,
            "review_count": review_count,
            "simulated": len(reviews) == 0 and aggregate_rating is None,
            "note": (
                "Live review data requires GBP/Yelp API integration. "
                "These values are extracted from public website markup where available."
            ),
        }


# ── GBP Signal Extractor ─────────────────────────────────────────────────────

class GBPExtractor:
    """Extract Google Business Profile signals without a paid API.

    Strategy:
      1. Search for the business name + location + "Google".
      2. Parse result snippets for rating stars / review counts.
      3. Fall back to LocalBusiness schema from the website.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

    def extract(self, name: str, location: str, website: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {
            "rating": None,
            "review_count": None,
            "categories": [],
            "has_booking_link": None,
            "photos_count": None,
            "gbp_url": None,
            "simulated": True,
            "note": "GBP data requires Google Business Profile API or manual verification.",
        }

        # Try LocalBusiness schema from website first
        if website:
            schema = self._schema_from_website(website)
            if schema:
                result["rating"] = schema.get("rating")
                result["review_count"] = schema.get("review_count")
                result["categories"] = schema.get("categories", [])
                if result["rating"] is not None or result["review_count"] is not None:
                    result["simulated"] = False
                    result["note"] = "GBP signals inferred from website schema.org markup."

        # Try a lightweight search for GBP signals
        search_data = self._search_gbp_signals(name, location)
        if search_data:
            if result["rating"] is None and search_data.get("rating") is not None:
                result["rating"] = search_data["rating"]
            if result["review_count"] is None and search_data.get("review_count") is not None:
                result["review_count"] = search_data["review_count"]
            if search_data.get("gbp_url"):
                result["gbp_url"] = search_data["gbp_url"]
            if result["rating"] is not None or result["review_count"] is not None:
                result["note"] = "GBP signals partially extracted from search results."

        return result

    def _schema_from_website(self, website: str) -> Optional[dict[str, Any]]:
        try:
            resp = self.session.get(website, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, "lxml")
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        t = item.get("@type", "")
                        if t in ("LocalBusiness", "HVACBusiness", "Plumber", "Electrician", "RoofingContractor"):
                            agg = item.get("aggregateRating", {})
                            return {
                                "rating": agg.get("ratingValue"),
                                "review_count": agg.get("reviewCount"),
                                "categories": [item.get("@type", "")] if item.get("@type") else [],
                            }
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _search_gbp_signals(self, name: str, location: str) -> Optional[dict[str, Any]]:
        query = f'"{name}" {location} google reviews'
        try:
            url = "https://html.duckduckgo.com/html/"
            resp = self.session.get(url, params={"q": query}, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, "lxml")
            for result in soup.select(".result"):
                snippet = result.select_one(".result__snippet")
                if not snippet:
                    continue
                text = snippet.get_text()
                # Look for patterns like "4.5 · 127 reviews" or "4.5 stars"
                rating_match = re.search(r"(\d\.\d)\s*stars?", text, re.IGNORECASE)
                count_match = re.search(r"([\d,]+)\s+reviews?", text, re.IGNORECASE)
                if rating_match or count_match:
                    return {
                        "rating": float(rating_match.group(1)) if rating_match else None,
                        "review_count": int(count_match.group(1).replace(",", "")) if count_match else None,
                        "gbp_url": None,
                    }
            time.sleep(1.5)
        except Exception as e:
            logger.warning(f"GBP signal search failed: {e}")
        return None


# ── Scout Agent ──────────────────────────────────────────────────────────────

class ScoutAgent:
    """Scout agent discovers businesses and enriches pending snapshots."""

    def __init__(self, timeout: int = 30, discovery_delay: float = 1.5):
        self.timeout = timeout
        self.discovery = BusinessDiscovery(timeout=timeout, delay=discovery_delay)
        self.website_scraper = WebsiteScraper(timeout=timeout)
        self.review_scraper = ReviewScraper(timeout=timeout)
        self.gbp_extractor = GBPExtractor(timeout=timeout)

    # ── Discovery Mode ───────────────────────────────────────────────────────

    def discover_and_seed(
        self,
        niche: str,
        city: str,
        state: str,
        max_results: int = 10,
    ) -> list[str]:
        """Discover businesses and create pending snapshots in the database.

        Returns list of created snapshot IDs.
        """
        logger.info(f"Discovering {niche} businesses in {city}, {state}")
        businesses = self.discovery.search(niche, city, state, max_results=max_results)
        created: list[str] = []
        for biz in businesses:
            snap_id = create_snapshot(
                business_name=biz["name"],
                location=f"{city}, {state}",
                website=biz.get("website", ""),
            )
            created.append(snap_id)
            logger.info(f"  Seeded: {biz['name']} -> {snap_id}")
        return created

    # ── Enrichment Mode ──────────────────────────────────────────────────────

    def run_once(self) -> Optional[str]:
        """Poll for a pending snapshot, enrich it, and move to scout_done.

        Returns the processed snapshot ID or None if no work available.
        """
        snapshot = claim_next_snapshot("pending", "scout_done")
        if snapshot is None:
            logger.debug("No pending snapshots to scout")
            return None

        snap_id = snapshot["id"]
        data = snapshot.get("data", {}) or {}
        business_info = data.get("business_info", {})
        name = business_info.get("name", snapshot["business_name"])
        website = business_info.get("website", snapshot.get("website", ""))
        location = business_info.get("location", snapshot["location"])

        logger.info(f"Scouting: {name} ({location})")

        try:
            scout_data = self._enrich(name, location, website)
            update_snapshot_data(snap_id, "scout_data", scout_data)
            logger.info(f"Scout complete for {name} (id={snap_id})")
            return snap_id
        except Exception as e:
            logger.error(f"Scout failed for {name}: {e}")
            update_snapshot_status(snap_id, "failed")
            return None

    def _enrich(self, name: str, location: str, website: str) -> dict[str, Any]:
        """Collect all raw data for a single business."""
        website_data = self.website_scraper.scrape(website) if website else {}
        review_data = self.review_scraper.scrape(name, website, location)
        gbp_data = self.gbp_extractor.extract(name, location, website)

        # Merge review counts if review scraper found something GBP didn't
        if gbp_data.get("review_count") is None and review_data.get("review_count") is not None:
            gbp_data["review_count"] = review_data["review_count"]
        if gbp_data.get("rating") is None and review_data.get("aggregate_rating") is not None:
            gbp_data["rating"] = review_data["aggregate_rating"]

        return {
            "gbp": gbp_data,
            "website": website_data,
            "reviews": review_data,
        }


# ── Pipeline Helpers ─────────────────────────────────────────────────────────

def run_scout_pipeline(timeout: int = 30, max_iterations: int = 10) -> int:
    """Run the scout agent in enrichment mode, processing available snapshots.

    Returns the number of snapshots processed.
    """
    scout = ScoutAgent(timeout=timeout)
    processed = 0
    for _ in range(max_iterations):
        result = scout.run_once()
        if result is None:
            break
        processed += 1
    return processed


def run_discovery(
    niche: str,
    city: str,
    state: str,
    max_results: int = 10,
    timeout: int = 30,
) -> list[str]:
    """Run the scout agent in discovery mode and seed the database.

    Returns list of created snapshot IDs.
    """
    scout = ScoutAgent(timeout=timeout)
    return scout.discover_and_seed(niche, city, state, max_results=max_results)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LocalPulse AI Scout Agent")
    subparsers = parser.add_subparsers(dest="command")

    # Discover command
    discover_parser = subparsers.add_parser("discover", help="Discover businesses and seed DB")
    discover_parser.add_argument("--niche", required=True, help="Business niche (e.g. HVAC, Plumbing)")
    discover_parser.add_argument("--city", required=True, help="City name")
    discover_parser.add_argument("--state", required=True, help="State abbreviation")
    discover_parser.add_argument("--max-results", type=int, default=10, help="Max businesses to discover")

    # Enrich command
    enrich_parser = subparsers.add_parser("enrich", help="Enrich pending snapshots")
    enrich_parser.add_argument("--max", type=int, default=10, help="Max snapshots to process")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.command == "discover":
        ids = run_discovery(args.niche, args.city, args.state, max_results=args.max_results)
        print(f"\nDiscovered and seeded {len(ids)} businesses.")
    elif args.command == "enrich":
        count = run_scout_pipeline(max_iterations=args.max)
        print(f"\nEnriched {count} snapshots.")
    else:
        parser.print_help()
