"""
Site Handlers
=============
Concrete scrapers for individual job boards.

Each handler is an async class that receives a Playwright page and
returns a list of raw job dicts conforming to the standard schema:

  {
      "title":       str,
      "company":     str,
      "location":    str,
      "description": str,
      "url":         str,
      "source":      str,   # handler identifier
      "salary":      str,   # raw salary text or ""
      "job_type":    str,   # "full-time" | "contract" | ...
      "posted_at":   str,   # ISO date string or ""
  }
"""

import asyncio
import random
from typing import Any

from playwright.async_api import Page
from bs4 import BeautifulSoup

from utils.logger import get_logger
from utils.helpers import human_delay

logger = get_logger(__name__)


# ── Base class ────────────────────────────────────────────────────────────────


class BaseSiteHandler:
    """Abstract base class for site-specific scrapers."""

    SOURCE_ID: str = "base"

    def __init__(self, keywords: list[str], locations: list[str]) -> None:
        self.keywords = keywords
        self.locations = locations

    async def scrape(self, page: Page) -> list[dict[str, Any]]:
        """
        Scrape job listings for this site.

        Args:
            page: Playwright page instance.

        Returns:
            List of job dicts.
        """
        raise NotImplementedError

    @staticmethod
    async def _safe_text(page: Page, selector: str, default: str = "") -> str:
        """Return inner_text of first matching element, or default."""
        try:
            el = await page.query_selector(selector)
            return (await el.inner_text()).strip() if el else default
        except Exception:
            return default

    @staticmethod
    async def _random_delay(min_ms: int = 800, max_ms: int = 2500) -> None:
        """Async random delay to appear human."""
        await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


# ── LinkedIn-like handler ─────────────────────────────────────────────────────


class LinkedInMockHandler(BaseSiteHandler):
    """
    Scraper for a LinkedIn-style job board structure.

    This targets the publicly accessible search results page
    (no login required). Adjust BASE_URL to point at a real endpoint.

    NOTE: Actual LinkedIn blocks automated scraping. This handler
          models the DOM structure of LinkedIn's public search pages
          and is designed to work against a self-hosted mock or a
          legitimate LinkedIn partner API.  Substitute BASE_URL and
          selectors as needed for your authorised use case.
    """

    SOURCE_ID = "linkedin_mock"
    BASE_URL = "https://www.linkedin.com/jobs/search/"

    async def scrape(self, page: Page) -> list[dict[str, Any]]:
        """
        Scrape job listings from a LinkedIn-style results page.

        Args:
            page: Playwright page instance.

        Returns:
            List of standardised job dicts.
        """
        jobs: list[dict[str, Any]] = []

        for keyword in self.keywords[:3]:  # Limit queries per run
            for location in self.locations[:2]:
                url = (
                    f"{self.BASE_URL}"
                    f"?keywords={keyword.replace(' ', '%20')}"
                    f"&location={location.replace(' ', '%20')}"
                    f"&f_TPR=r86400"  # Past 24 hours
                )
                logger.debug(f"[linkedin_mock] Fetching: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await self._random_delay(1500, 3000)

                    # Scroll to load lazy content
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await self._random_delay(600, 1200)

                    html = await page.content()
                    batch = self._parse_linkedin_html(html, location)
                    logger.info(f"[linkedin_mock] Found {len(batch)} jobs for '{keyword}' in '{location}'")
                    jobs.extend(batch)
                    await self._random_delay(2000, 4000)

                except Exception as exc:
                    logger.warning(f"[linkedin_mock] Failed for '{keyword}': {exc}")

        return self._deduplicate(jobs)

    def _parse_linkedin_html(
        self, html: str, location: str
    ) -> list[dict[str, Any]]:
        """
        Parse LinkedIn search-results HTML into job dicts.

        Args:
            html: Raw page HTML.
            location: The searched location string.

        Returns:
            List of job dicts.
        """
        soup = BeautifulSoup(html, "lxml")
        jobs: list[dict[str, Any]] = []

        # LinkedIn's public job cards live inside <li> under this class
        cards = soup.select("li.jobs-search__results-list > div.base-card")
        if not cards:
            # Fallback selector variant
            cards = soup.select("div.job-search-card")

        for card in cards:
            try:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle")
                loc_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link")
                date_el = card.select_one("time")

                title = title_el.get_text(strip=True) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                loc = loc_el.get_text(strip=True) if loc_el else location
                url = link_el.get("href", "") if link_el else ""
                posted_at = date_el.get("datetime", "") if date_el else ""

                if not title or not url:
                    continue

                jobs.append(
                    {
                        "title": title,
                        "company": company,
                        "location": loc,
                        "description": "",  # Fetched in detail pass
                        "url": url,
                        "source": self.SOURCE_ID,
                        "salary": "",
                        "job_type": "full-time",
                        "posted_at": posted_at,
                    }
                )
            except Exception as exc:
                logger.debug(f"[linkedin_mock] Card parse error: {exc}")

        return jobs

    @staticmethod
    def _deduplicate(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for job in jobs:
            key = job["url"]
            if key not in seen:
                seen.add(key)
                unique.append(job)
        return unique


# ── Generic job board handler ─────────────────────────────────────────────────


class GenericBoardHandler(BaseSiteHandler):
    """
    Scraper for a generic HTML job board.

    Targets https://remotive.com/remote-jobs as a real, publicly accessible
    remote-job board that does not require login.  Selectors are matched to
    its current DOM structure and can be adapted to any similar board.
    """

    SOURCE_ID = "generic_board"
    BASE_URL = "https://remotive.com/remote-jobs"

    # Map human-readable category → Remotive URL path segment
    CATEGORY_MAP = {
        "Software Engineer": "software-dev",
        "Backend Engineer": "software-dev",
        "Python Developer": "software-dev",
        "Full Stack Engineer": "software-dev",
        "Data Engineer": "data",
        "DevOps Engineer": "devops-sysadmin",
        "Product Manager": "product",
    }

    async def scrape(self, page: Page) -> list[dict[str, Any]]:
        """
        Scrape remote job listings from Remotive-style board.

        Args:
            page: Playwright page instance.

        Returns:
            List of standardised job dicts.
        """
        jobs: list[dict[str, Any]] = []
        visited_categories: set[str] = set()

        for title in self.keywords[:4]:
            category = self.CATEGORY_MAP.get(title, "software-dev")
            if category in visited_categories:
                continue
            visited_categories.add(category)

            url = f"{self.BASE_URL}/{category}"
            logger.debug(f"[generic_board] Fetching: {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await self._random_delay(1200, 2500)

                # Scroll to trigger lazy-loaded cards
                for _ in range(4):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await self._random_delay(400, 800)

                html = await page.content()
                batch = self._parse_generic_html(html)
                logger.info(
                    f"[generic_board] Found {len(batch)} jobs for category '{category}'"
                )
                jobs.extend(batch)
                await self._random_delay(2000, 5000)

            except Exception as exc:
                logger.warning(f"[generic_board] Failed for '{category}': {exc}")

        return jobs

    def _parse_generic_html(self, html: str) -> list[dict[str, Any]]:
        """
        Parse HTML from a generic job board into job dicts.

        Args:
            html: Raw page HTML content.

        Returns:
            List of job dicts.
        """
        soup = BeautifulSoup(html, "lxml")
        jobs: list[dict[str, Any]] = []

        # Remotive uses <li> job cards
        cards = soup.select("li.job-list-item")

        for card in cards:
            try:
                title_el = card.select_one("h2.position")
                company_el = card.select_one("span.company_name")
                tag_els = card.select("span.job-tag")
                link_el = card.select_one("a")
                date_el = card.select_one("time")
                salary_el = card.select_one("span.salary")

                title = title_el.get_text(strip=True) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                tags = [t.get_text(strip=True) for t in tag_els]
                href = link_el.get("href", "") if link_el else ""
                # Remotive hrefs are relative
                url = f"https://remotive.com{href}" if href.startswith("/") else href
                posted_at = date_el.get("datetime", "") if date_el else ""
                salary = salary_el.get_text(strip=True) if salary_el else ""

                if not title or not url:
                    continue

                jobs.append(
                    {
                        "title": title,
                        "company": company,
                        "location": "Remote",
                        "description": " | ".join(tags),
                        "url": url,
                        "source": self.SOURCE_ID,
                        "salary": salary,
                        "job_type": "full-time",
                        "posted_at": posted_at,
                    }
                )
            except Exception as exc:
                logger.debug(f"[generic_board] Card parse error: {exc}")

        return jobs


# ── Registry ──────────────────────────────────────────────────────────────────


HANDLER_REGISTRY: dict[str, type[BaseSiteHandler]] = {
    LinkedInMockHandler.SOURCE_ID: LinkedInMockHandler,
    GenericBoardHandler.SOURCE_ID: GenericBoardHandler,
}
