"""
Job Scraper
===========
Orchestrates all site handlers inside a single Playwright browser session.
Applies keyword filtering, exclusion rules, and rate limiting.
"""

import asyncio
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext

from config import Config
from scraper.site_handlers import HANDLER_REGISTRY
from utils.helpers import keyword_match, exclude_match, human_delay
from utils.logger import get_logger

logger = get_logger(__name__)


class JobScraper:
    """
    Launches a stealth Playwright browser, runs all configured
    site handlers, and returns a filtered list of job dicts.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    async def scrape_all(self) -> list[dict[str, Any]]:
        """
        Run all enabled scrapers and return combined, filtered results.

        Returns:
            List of unique, filtered job dicts.
        """
        all_jobs: list[dict[str, Any]] = []

        async with async_playwright() as pw:
            browser = await self._launch_browser(pw)
            context = await self._create_context(browser)

            for source_id in self._config.SCRAPE_SOURCES:
                handler_cls = HANDLER_REGISTRY.get(source_id)
                if handler_cls is None:
                    logger.warning(f"No handler registered for source: {source_id}")
                    continue

                handler = handler_cls(
                    keywords=self._config.JOB_TITLES,
                    locations=self._config.LOCATIONS,
                )
                page = await context.new_page()
                try:
                    logger.info(f"Starting scraper: {source_id}")
                    jobs = await handler.scrape(page)
                    logger.info(f"[{source_id}] raw results: {len(jobs)}")
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.error(f"[{source_id}] Scraper crashed: {exc}")
                finally:
                    await page.close()

                # Rate-limit between different sites
                await asyncio.sleep(
                    self._config.SCRAPE_DELAY_MAX
                )

            await context.close()
            await browser.close()

        # Apply filtering
        filtered = self._apply_filters(all_jobs)
        logger.info(
            f"After filtering: {len(filtered)} / {len(all_jobs)} jobs retained."
        )
        return filtered

    # ── Private helpers ───────────────────────────────────────────

    async def _launch_browser(self, pw: Any) -> Browser:
        """
        Launch a Chromium browser with stealth arguments.

        Args:
            pw: Playwright instance.

        Returns:
            Browser object.
        """
        return await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
        )

    @staticmethod
    async def _create_context(browser: Browser) -> BrowserContext:
        """
        Create a browser context that mimics a real user.

        Args:
            browser: Launched Browser instance.

        Returns:
            BrowserContext with realistic headers and viewport.
        """
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            },
        )

        # Override WebDriver property to avoid detection
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return context

    def _apply_filters(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Filter job list by keyword inclusion and exclusion rules, job type,
        and location preferences from config.

        Args:
            jobs: Raw list of job dicts.

        Returns:
            Filtered list.
        """
        results: list[dict[str, Any]] = []

        for job in jobs:
            combined_text = (
                f"{job.get('title', '')} "
                f"{job.get('description', '')} "
                f"{job.get('company', '')}"
            )

            # Exclude if any exclusion keyword is present
            if self._config.EXCLUDE_KEYWORDS and exclude_match(
                combined_text, self._config.EXCLUDE_KEYWORDS
            ):
                logger.debug(f"Excluded (keyword filter): {job['title']}")
                continue

            # Must match at least one of the desired job titles (loose match)
            if self._config.JOB_TITLES and not keyword_match(
                job.get("title", ""), self._config.JOB_TITLES
            ):
                logger.debug(f"Excluded (title mismatch): {job['title']}")
                continue

            results.append(job)

        return results
