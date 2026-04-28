"""
Form Filler
===========
Provides helpers for filling out web application forms using Playwright.
Simulates human-like typing with randomised delays and natural mouse movement.
Handles text inputs, text areas, dropdowns, file uploads, and checkboxes.
"""

import asyncio
import random
from pathlib import Path
from typing import Any

from playwright.async_api import Page, Locator

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class FormFiller:
    """
    High-level form-filling helper built on Playwright.

    All typing operations use randomised per-keystroke delays to simulate
    a human typist and reduce the chance of bot-detection heuristics
    triggering on key-event timing patterns.
    """

    def __init__(self, page: Page, config: Config) -> None:
        self._page = page
        self._config = config

    # ── Public API ────────────────────────────────────────────────

    async def fill_text(self, selector: str, value: str) -> bool:
        """
        Type a value into a text input with human-like delays.

        Args:
            selector: CSS / XPath selector for the input element.
            value: Text to type.

        Returns:
            True on success, False if element not found or typing failed.
        """
        try:
            el = await self._find(selector)
            if el is None:
                return False
            await el.click()
            await self._human_type(el, value)
            return True
        except Exception as exc:
            logger.debug(f"fill_text failed for '{selector}': {exc}")
            return False

    async def fill_textarea(self, selector: str, value: str) -> bool:
        """
        Type a multi-line value into a textarea.

        Args:
            selector: Selector for the textarea element.
            value: Text to type.

        Returns:
            True on success, False otherwise.
        """
        return await self.fill_text(selector, value)

    async def select_option(self, selector: str, label_or_value: str) -> bool:
        """
        Select a <select> dropdown option by visible label or value attribute.

        Args:
            selector: Selector for the <select> element.
            label_or_value: The option's visible text or value attribute.

        Returns:
            True on success, False otherwise.
        """
        try:
            el = await self._find(selector)
            if el is None:
                return False
            await el.select_option(label=label_or_value)
            return True
        except Exception:
            try:
                # Fallback: try matching by value
                el = await self._find(selector)
                if el:
                    await el.select_option(value=label_or_value)
                    return True
            except Exception as exc:
                logger.debug(f"select_option failed for '{selector}': {exc}")
        return False

    async def check_checkbox(self, selector: str, check: bool = True) -> bool:
        """
        Set a checkbox to the desired state.

        Args:
            selector: Selector for the checkbox element.
            check: True to check, False to uncheck.

        Returns:
            True on success, False otherwise.
        """
        try:
            el = await self._find(selector)
            if el is None:
                return False
            is_checked = await el.is_checked()
            if is_checked != check:
                await el.click()
            return True
        except Exception as exc:
            logger.debug(f"check_checkbox failed for '{selector}': {exc}")
            return False

    async def upload_file(self, selector: str, file_path: str) -> bool:
        """
        Trigger a file upload input with the given local file.

        Args:
            selector: Selector for the file <input> element.
            file_path: Absolute path to the file to upload.

        Returns:
            True on success, False otherwise.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Upload file not found: {file_path}")
            return False
        try:
            el = await self._find(selector)
            if el is None:
                return False
            await el.set_input_files(str(path))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return True
        except Exception as exc:
            logger.debug(f"upload_file failed for '{selector}': {exc}")
            return False

    async def click_button(self, selector: str) -> bool:
        """
        Click a button or any clickable element.

        Args:
            selector: CSS selector for the target element.

        Returns:
            True on success, False otherwise.
        """
        try:
            el = await self._find(selector)
            if el is None:
                return False
            await el.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.2, 0.7))
            await el.click()
            return True
        except Exception as exc:
            logger.debug(f"click_button failed for '{selector}': {exc}")
            return False

    async def fill_form_fields(
        self,
        field_map: dict[str, Any],
        resume_path: str,
    ) -> dict[str, bool]:
        """
        Fill multiple form fields from a mapping of field_name → value.

        Known field names (detected by heuristic label / name attribute matching):
            - first_name, last_name, full_name, email, phone
            - linkedin, github, portfolio, location
            - cover_letter, resume_file

        Args:
            field_map: Mapping of semantic field name → value string.
            resume_path: Path to the resume file for upload.

        Returns:
            Dict of field_name → success boolean.
        """
        results: dict[str, bool] = {}

        # Common input selectors for each semantic field
        field_selectors: dict[str, list[str]] = {
            "first_name": [
                "input[name*='first'][type='text']",
                "input[placeholder*='First']",
                "#first_name", "#firstName",
            ],
            "last_name": [
                "input[name*='last'][type='text']",
                "input[placeholder*='Last']",
                "#last_name", "#lastName",
            ],
            "full_name": [
                "input[name*='name'][type='text']",
                "input[placeholder*='Full name']",
                "input[placeholder*='Your name']",
                "#name", "#fullName",
            ],
            "email": [
                "input[type='email']",
                "input[name*='email']",
                "input[placeholder*='email' i]",
            ],
            "phone": [
                "input[type='tel']",
                "input[name*='phone']",
                "input[placeholder*='phone' i]",
            ],
            "linkedin": [
                "input[name*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
            ],
            "github": [
                "input[name*='github' i]",
                "input[placeholder*='github' i]",
            ],
            "portfolio": [
                "input[name*='portfolio' i]",
                "input[name*='website' i]",
                "input[placeholder*='portfolio' i]",
                "input[placeholder*='website' i]",
            ],
            "location": [
                "input[name*='location' i]",
                "input[name*='city' i]",
                "input[placeholder*='location' i]",
                "input[placeholder*='city' i]",
            ],
            "cover_letter": [
                "textarea[name*='cover' i]",
                "textarea[placeholder*='cover' i]",
                "textarea[name*='message' i]",
                "textarea[aria-label*='cover' i]",
                "#coverLetter", "#cover_letter",
            ],
            "resume_file": [
                "input[type='file'][name*='resume' i]",
                "input[type='file'][name*='cv' i]",
                "input[type='file']",
            ],
        }

        for field_name, value in field_map.items():
            if not value:
                continue

            selectors = field_selectors.get(field_name, [])
            if not selectors:
                continue

            success = False
            for selector in selectors:
                if field_name == "resume_file":
                    success = await self.upload_file(selector, resume_path)
                elif field_name == "cover_letter":
                    success = await self.fill_textarea(selector, str(value))
                else:
                    success = await self.fill_text(selector, str(value))

                if success:
                    await asyncio.sleep(random.uniform(0.3, 0.9))
                    break

            results[field_name] = success
            if not success:
                logger.debug(f"Could not fill field: {field_name}")

        return results

    # ── Internal helpers ──────────────────────────────────────────

    async def _find(self, selector: str, timeout: int = 5000) -> Locator | None:
        """
        Find an element on the page, returning None if not visible.

        Args:
            selector: CSS selector.
            timeout: Wait timeout in milliseconds.

        Returns:
            Locator if found and visible, else None.
        """
        try:
            locator = self._page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception:
            return None

    async def _human_type(self, el: Locator, text: str) -> None:
        """
        Type text with per-character random delays to simulate a human typist.

        Args:
            el: Playwright Locator for the target input.
            text: Text to type.
        """
        await el.fill("")  # Clear existing content first

        min_delay = self._config.TYPING_DELAY_MIN
        max_delay = self._config.TYPING_DELAY_MAX

        for char in text:
            await el.type(char, delay=random.randint(min_delay, max_delay))

        # Small post-typing pause
        await asyncio.sleep(random.uniform(0.1, 0.4))
