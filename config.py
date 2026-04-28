"""
Configuration Module
====================
Loads all settings from environment variables and the job_prefs.json config file.
Provides a single Config object used throughout the application.
"""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Centralised configuration.  Every value comes from either:
      - An environment variable (sensitive secrets), or
      - job_prefs.json  (user preferences), or
      - a sensible default.
    """

    # ── Anthropic ───────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    # ── Resume ──────────────────────────────────────────────────
    RESUME_PATH: str = os.getenv("RESUME_PATH", "resume.pdf")

    # ── Scraper ─────────────────────────────────────────────────
    SCRAPE_DELAY_MIN: float = float(os.getenv("SCRAPE_DELAY_MIN", "2.0"))
    SCRAPE_DELAY_MAX: float = float(os.getenv("SCRAPE_DELAY_MAX", "5.0"))
    SCRAPER_TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "30000"))  # ms

    # ── Matching ────────────────────────────────────────────────
    MIN_MATCH_SCORE: int = int(os.getenv("MIN_MATCH_SCORE", "60"))

    # ── Application bot ─────────────────────────────────────────
    TYPING_DELAY_MIN: int = int(os.getenv("TYPING_DELAY_MIN", "50"))   # ms
    TYPING_DELAY_MAX: int = int(os.getenv("TYPING_DELAY_MAX", "150"))  # ms
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

    # ── Data storage ─────────────────────────────────────────────
    DATA_DIR: str = os.getenv("DATA_DIR", "data")
    JOBS_CSV: str = os.path.join(DATA_DIR, "jobs.csv")
    APPLICATIONS_CSV: str = os.path.join(DATA_DIR, "applications.csv")

    # ── Personal info (used for form auto-fill) ──────────────────
    APPLICANT_NAME: str = os.getenv("APPLICANT_NAME", "")
    APPLICANT_EMAIL: str = os.getenv("APPLICANT_EMAIL", "")
    APPLICANT_PHONE: str = os.getenv("APPLICANT_PHONE", "")
    APPLICANT_LINKEDIN: str = os.getenv("APPLICANT_LINKEDIN", "")
    APPLICANT_GITHUB: str = os.getenv("APPLICANT_GITHUB", "")
    APPLICANT_PORTFOLIO: str = os.getenv("APPLICANT_PORTFOLIO", "")
    APPLICANT_LOCATION: str = os.getenv("APPLICANT_LOCATION", "")

    def __init__(self) -> None:
        self._prefs: dict[str, Any] = self._load_prefs()
        self._validate()

    # ── Job preferences (from JSON) ──────────────────────────────

    @property
    def JOB_TITLES(self) -> list[str]:
        return self._prefs.get("job_titles", ["Software Engineer"])

    @property
    def KEYWORDS(self) -> list[str]:
        return self._prefs.get("keywords", [])

    @property
    def EXCLUDE_KEYWORDS(self) -> list[str]:
        return self._prefs.get("exclude_keywords", [])

    @property
    def LOCATIONS(self) -> list[str]:
        return self._prefs.get("locations", ["Remote"])

    @property
    def EXPERIENCE_LEVEL(self) -> list[str]:
        return self._prefs.get("experience_level", ["mid-level"])

    @property
    def JOB_TYPES(self) -> list[str]:
        return self._prefs.get("job_types", ["full-time"])

    @property
    def SCRAPE_SOURCES(self) -> list[str]:
        return self._prefs.get("scrape_sources", ["linkedin_mock", "generic_board"])

    @property
    def MAX_SALARY(self) -> int | None:
        return self._prefs.get("max_salary", None)

    @property
    def MIN_SALARY(self) -> int | None:
        return self._prefs.get("min_salary", None)

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _load_prefs() -> dict[str, Any]:
        prefs_path = Path("job_prefs.json")
        if prefs_path.exists():
            with open(prefs_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return {}

    def _validate(self) -> None:
        if not self.ANTHROPIC_API_KEY:
            self.ANTHROPIC_API_KEY = "not-needed-using-ollama"
        Path(self.DATA_DIR).mkdir(parents=True, exist_ok=True)