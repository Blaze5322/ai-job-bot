"""
Apply Bot
=========
Automates the job application submission process using Playwright.
Handles: navigation, form detection, CAPTCHA-safe fallback,
cover letter injection, resume upload, and submission.
"""

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import Config
from automation.form_filler import FormFiller
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Captcha signals ───────────────────────────────────────────────────────────

_CAPTCHA_INDICATORS = [
    "captcha",
    "recaptcha",
    "hcaptcha",
    "challenge",
    "cloudflare",
    "are you human",
    "prove you're human",
    "security check",
    "bot detection",
]


class ApplyBot:
    """
    Playwright-powered automation bot that submits job applications.

    Supports headless and visible modes, human-like typing, CAPTCHA
    skip logic (does NOT attempt to bypass — simply flags the job),
    and dry-run mode for testing without actual submission.

    Usage (async context manager):
        async with ApplyBot(config, headless=True) as bot:
            result = await bot.apply(job, resume_data)
    """

    def __init__(
        self,
        config: Config,
        headless: bool = True,
        dry_run: bool = False,
    ) -> None:
        self._config = config
        self._headless = headless
        self._dry_run = dry_run
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pw: Any = None

    # ── Async context manager ─────────────────────────────────────

    async def __aenter__(self) -> "ApplyBot":
        self._pw = await async_playwright().start()
        self._browser = await self._launch_browser()
        self._context = await self._create_context()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    # ── Public API ────────────────────────────────────────────────

    async def apply(
        self,
        job: dict[str, Any],
        resume: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Attempt to apply for a single job with retry logic.

        Args:
            job: Job dict including url, title, company, cover_letter.
            resume: Parsed resume dict.

        Returns:
            Result dict with keys: status, error, retry_count, screenshot.
        """
        url = job.get("url", "")
        title = job.get("title", "?")
        company = job.get("company", "?")

        logger.info(f"Applying to: {title} @ {company}")

        for attempt in range(1, self._config.MAX_RETRIES + 1):
            page = await self._context.new_page()  # type: ignore[union-attr]
            try:
                result = await self._attempt_apply(page, job, resume)
                result["retry_count"] = attempt - 1
                return result
            except Exception as exc:
                logger.warning(f"Apply attempt {attempt} failed: {exc}")
                if attempt == self._config.MAX_RETRIES:
                    screenshot = await self._take_screenshot(page, job)
                    return {
                        "status": "failed",
                        "error": str(exc),
                        "retry_count": attempt,
                        "screenshot": screenshot,
                    }
                # Exponential back-off between retries
                await asyncio.sleep(2 ** attempt + random.uniform(0, 2))
            finally:
                await page.close()

        return {"status": "failed", "error": "Max retries reached", "retry_count": self._config.MAX_RETRIES}

    # ── Private: application flow ─────────────────────────────────

    async def _attempt_apply(
        self,
        page: Page,
        job: dict[str, Any],
        resume: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a single application attempt on the given page.

        Args:
            page: Playwright Page.
            job:  Job dict.
            resume: Parsed resume dict.

        Returns:
            Result dict.
        """
        url = job.get("url", "")

        # Navigate to job posting
        await page.goto(url, wait_until="domcontentloaded", timeout=self._config.SCRAPER_TIMEOUT)
        await self._random_delay(1000, 2500)

        # ── CAPTCHA check ─────────────────────────────────────────
        if await self._has_captcha(page):
            logger.warning(f"CAPTCHA detected on {url} — skipping (safe fallback).")
            return {
                "status": "skipped_captcha",
                "error": "CAPTCHA encountered — manual review required",
                "screenshot": await self._take_screenshot(page, job),
            }

        # ── Find and click the apply button ───────────────────────
        apply_clicked = await self._click_apply_button(page)
        if not apply_clicked:
            return {
                "status": "skipped_no_button",
                "error": "Could not find an Apply button on this page.",
                "screenshot": await self._take_screenshot(page, job),
            }

        await self._random_delay(1500, 3000)

        # ── Check for CAPTCHA again after navigation ──────────────
        if await self._has_captcha(page):
            logger.warning("CAPTCHA appeared after clicking Apply — skipping.")
            return {
                "status": "skipped_captcha",
                "error": "CAPTCHA encountered after Apply click",
                "screenshot": await self._take_screenshot(page, job),
            }

        # ── Build the field map from resume + config ───────────────
        field_map = self._build_field_map(resume, job)

        # ── Fill the form ─────────────────────────────────────────
        filler = FormFiller(page, self._config)
        fill_results = await filler.fill_form_fields(
            field_map=field_map,
            resume_path=self._config.RESUME_PATH,
        )

        filled_count = sum(1 for v in fill_results.values() if v)
        logger.debug(f"Form fill: {filled_count}/{len(fill_results)} fields successful.")

        # ── Dry-run: stop before submission ───────────────────────
        if self._dry_run:
            logger.info("[DRY RUN] Skipping form submission.")
            return {
                "status": "dry_run",
                "error": "",
                "fill_results": fill_results,
            }

        # ── Submit ────────────────────────────────────────────────
        submitted = await self._submit_form(page)
        if not submitted:
            return {
                "status": "failed",
                "error": "Could not locate submit button.",
                "screenshot": await self._take_screenshot(page, job),
            }

        await self._random_delay(2000, 4000)

        # Verify submission (look for confirmation signals)
        confirmed = await self._check_confirmation(page)
        if confirmed:
            logger.info(f"✓ Application submitted: {job.get('title')} @ {job.get('company')}")
            return {"status": "applied", "error": ""}
        else:
            return {
                "status": "submitted_unconfirmed",
                "error": "Submitted but could not confirm success.",
                "screenshot": await self._take_screenshot(page, job),
            }

    # ── Private: UI helpers ───────────────────────────────────────

    async def _click_apply_button(self, page: Page) -> bool:
        """
        Find and click an 'Apply' button using common patterns.

        Args:
            page: Playwright Page.

        Returns:
            True if a button was found and clicked.
        """
        apply_selectors = [
            "a:has-text('Apply Now')",
            "a:has-text('Apply')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
            "button:has-text('Easy Apply')",
            "[data-testid='apply-button']",
            "[aria-label*='Apply' i]",
            ".apply-button",
            "#applyButton",
        ]

        for selector in apply_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    await el.click()
                    return True
            except Exception:
                continue

        return False

    async def _submit_form(self, page: Page) -> bool:
        """
        Click the submit / final-apply button on the application form.

        Args:
            page: Playwright Page.

        Returns:
            True if submission click succeeded.
        """
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Submit Application')",
            "button:has-text('Send Application')",
            "button:has-text('Apply')",
            "[data-testid='submit-button']",
        ]

        for selector in submit_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                    await el.click()
                    return True
            except Exception:
                continue

        return False

    async def _check_confirmation(self, page: Page) -> bool:
        """
        Check whether the page shows a success / confirmation message.

        Args:
            page: Playwright Page.

        Returns:
            True if a success indicator is found.
        """
        confirmation_signals = [
            "text=Application submitted",
            "text=Thank you for applying",
            "text=Successfully applied",
            "text=Application received",
            "text=We've received your application",
            "[class*='success']",
            "[class*='confirmation']",
            "[aria-live*='success' i]",
        ]

        for signal in confirmation_signals:
            try:
                el = page.locator(signal).first
                if await el.is_visible(timeout=3000):
                    return True
            except Exception:
                continue

        # Fallback: check URL changed to a confirmation path
        current_url = page.url
        confirmation_paths = [
            "confirmation", "success", "thank-you",
            "submitted", "applied", "complete",
        ]
        return any(p in current_url.lower() for p in confirmation_paths)

    async def _has_captcha(self, page: Page) -> bool:
        """
        Detect common CAPTCHA indicators on the current page.

        This is a SKIP signal only — the bot does NOT attempt to bypass.

        Args:
            page: Playwright Page.

        Returns:
            True if a CAPTCHA is detected.
        """
        try:
            content = (await page.content()).lower()
            for indicator in _CAPTCHA_INDICATORS:
                if indicator in content:
                    return True
        except Exception:
            pass
        return False

    async def _take_screenshot(
        self,
        page: Page,
        job: dict[str, Any],
    ) -> str:
        """
        Save a screenshot for debugging failed applications.

        Args:
            page: Playwright Page.
            job:  Job dict (used to name the file).

        Returns:
            Path to the saved screenshot, or "" on failure.
        """
        import re
        from pathlib import Path
        from datetime import datetime

        screenshots_dir = Path("logs/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^\w]", "_", f"{job.get('company', 'unknown')}_{job.get('title', 'job')}")[:50]
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = screenshots_dir / f"{safe_name}_{ts}.png"

        try:
            await page.screenshot(path=str(path), full_page=True)
            logger.debug(f"Screenshot saved: {path}")
            return str(path)
        except Exception as exc:
            logger.debug(f"Screenshot failed: {exc}")
            return ""

    # ── Browser setup ─────────────────────────────────────────────

    async def _launch_browser(self) -> Browser:
        """
        Launch a Chromium browser with stealth and fingerprint-reduction flags.

        Returns:
            Browser instance.
        """
        return await self._pw.chromium.launch(
            headless=self._headless,
            slow_mo=50 if not self._headless else 0,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--start-maximized",
            ],
        )

    async def _create_context(self) -> BrowserContext:
        """
        Create a browser context that mimics a real user session.

        Returns:
            BrowserContext instance.
        """
        context = await self._browser.new_context(  # type: ignore[union-attr]
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return context

    @staticmethod
    async def _random_delay(min_ms: int = 500, max_ms: int = 2000) -> None:
        """Async random delay to simulate human pacing."""
        await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    def _build_field_map(
        self,
        resume: dict[str, Any],
        job: dict[str, Any],
    ) -> dict[str, str]:
        """
        Build the mapping of form field names → values from resume + config.

        Prefers data extracted from the resume; falls back to env config.

        Args:
            resume: Parsed resume dict.
            job:    Job dict (provides cover_letter).

        Returns:
            Dict of semantic field name → value string.
        """
        name = resume.get("name") or self._config.APPLICANT_NAME or ""
        # Attempt to split into first / last
        name_parts = name.strip().split(" ", 1)
        first = name_parts[0] if name_parts else ""
        last = name_parts[1] if len(name_parts) > 1 else ""

        return {
            "first_name": first,
            "last_name": last,
            "full_name": name,
            "email": resume.get("email") or self._config.APPLICANT_EMAIL or "",
            "phone": resume.get("phone") or self._config.APPLICANT_PHONE or "",
            "linkedin": resume.get("linkedin") or self._config.APPLICANT_LINKEDIN or "",
            "github": resume.get("github") or self._config.APPLICANT_GITHUB or "",
            "portfolio": self._config.APPLICANT_PORTFOLIO or "",
            "location": self._config.APPLICANT_LOCATION or "",
            "cover_letter": job.get("cover_letter", ""),
            "resume_file": self._config.RESUME_PATH,
        }
