"""
Helper Utilities
================
Shared utility functions and the DataStore class for persisting jobs
and application records to CSV files.
"""

import csv
import hashlib
import json
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Data Store ───────────────────────────────────────────────────────────────


class DataStore:
    """
    Manages persistent storage of scraped jobs and application records
    using CSV files with a simple hash-based deduplication scheme.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._jobs_path = Path(config.JOBS_CSV)
        self._apps_path = Path(config.APPLICATIONS_CSV)

        self._ensure_jobs_csv()
        self._ensure_applications_csv()

        # In-memory set of job hashes for fast dedup
        self._known_hashes: set[str] = self._load_known_hashes()

    # ── Jobs ─────────────────────────────────────────────────────

    def filter_new_jobs(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Return only jobs that have not been seen before.

        Args:
            jobs: Raw list of job dicts from the scraper.

        Returns:
            Subset of jobs whose hash is not in the known set.
        """
        new_jobs = []
        for job in jobs:
            h = job_hash(job)
            if h not in self._known_hashes:
                job["id"] = h
                new_jobs.append(job)
        return new_jobs

    def save_job(self, job: dict[str, Any]) -> None:
        """
        Persist a job record to jobs.csv.

        Args:
            job: Job dictionary (must include 'id' key).
        """
        h = job.get("id", job_hash(job))
        if h in self._known_hashes:
            return  # Already saved

        row = {
            "id": h,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "url": job.get("url", ""),
            "source": job.get("source", ""),
            "match_score": job.get("match_score", ""),
            "description_snippet": job.get("description", "")[:300],
            "scraped_at": datetime.utcnow().isoformat(),
        }

        with open(self._jobs_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            writer.writerow(row)

        self._known_hashes.add(h)
        logger.debug(f"Saved job: {row['title']} @ {row['company']}")

    # ── Applications ─────────────────────────────────────────────

    def save_application(
        self,
        job: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """
        Persist an application attempt to applications.csv.

        Args:
            job: The job that was applied to.
            result: Result dict from ApplyBot (status, error, etc.).

        Returns:
            The new application record ID.
        """
        record_id = str(uuid.uuid4())
        row = {
            "id": record_id,
            "job_id": job.get("id", job_hash(job)),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
            "match_score": job.get("match_score", ""),
            "status": result.get("status", "unknown"),
            "error": result.get("error", ""),
            "applied_at": datetime.utcnow().isoformat(),
            "retry_count": result.get("retry_count", 0),
            "job_snapshot": json.dumps(
                {k: v for k, v in job.items() if k != "cover_letter"}
            ),
        }

        with open(self._apps_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            writer.writerow(row)

        return record_id

    def update_application(
        self,
        record_id: str,
        result: dict[str, Any],
    ) -> None:
        """
        Rewrite the application record identified by record_id with new result.

        Args:
            record_id: UUID of the application to update.
            result: New result dict.
        """
        rows: list[dict[str, Any]] = []
        with open(self._apps_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row["id"] == record_id:
                    row["status"] = result.get("status", row["status"])
                    row["error"] = result.get("error", "")
                    row["retry_count"] = int(row.get("retry_count", 0)) + 1
                    row["applied_at"] = datetime.utcnow().isoformat()
                rows.append(row)

        if rows:
            with open(self._apps_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

    def get_failed_applications(self) -> list[dict[str, Any]]:
        """
        Return all application records whose status is 'failed'.

        Returns:
            List of dicts with keys 'id' and 'job'.
        """
        failed: list[dict[str, Any]] = []
        if not self._apps_path.exists():
            return failed

        with open(self._apps_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("status") == "failed":
                    try:
                        job = json.loads(row.get("job_snapshot", "{}"))
                    except json.JSONDecodeError:
                        job = {}
                    failed.append({"id": row["id"], "job": job})

        return failed

    # ── Private helpers ───────────────────────────────────────────

    def _ensure_jobs_csv(self) -> None:
        if not self._jobs_path.exists():
            with open(self._jobs_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "id", "title", "company", "location",
                        "url", "source", "match_score",
                        "description_snippet", "scraped_at",
                    ],
                )
                writer.writeheader()

    def _ensure_applications_csv(self) -> None:
        if not self._apps_path.exists():
            with open(self._apps_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "id", "job_id", "title", "company", "url",
                        "match_score", "status", "error",
                        "applied_at", "retry_count", "job_snapshot",
                    ],
                )
                writer.writeheader()

    def _load_known_hashes(self) -> set[str]:
        hashes: set[str] = set()
        if not self._jobs_path.exists():
            return hashes
        with open(self._jobs_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("id"):
                    hashes.add(row["id"])
        return hashes


# ── Standalone helpers ────────────────────────────────────────────────────────


def job_hash(job: dict[str, Any]) -> str:
    """
    Create a stable hash from job title + company + URL for deduplication.

    Args:
        job: Job dictionary.

    Returns:
        Short hex digest string.
    """
    key = f"{job.get('title', '')}|{job.get('company', '')}|{job.get('url', '')}".lower()
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def human_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    """
    Sleep for a random duration to simulate human behaviour.

    Args:
        min_s: Minimum sleep in seconds.
        max_s: Maximum sleep in seconds.
    """
    duration = random.uniform(min_s, max_s)
    time.sleep(duration)


def keyword_match(text: str, keywords: list[str]) -> bool:
    """
    Return True if any keyword from the list appears in text (case-insensitive).

    Args:
        text: Text to search.
        keywords: List of keyword strings.

    Returns:
        True if at least one keyword is found.
    """
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def exclude_match(text: str, exclude_keywords: list[str]) -> bool:
    """
    Return True if any exclusion keyword appears in text.

    Args:
        text: Text to check.
        exclude_keywords: Keywords that disqualify a job.

    Returns:
        True if the job should be excluded.
    """
    return keyword_match(text, exclude_keywords)


def truncate(text: str, max_len: int = 500) -> str:
    """
    Truncate text to max_len characters, appending '…' if shortened.

    Args:
        text: Input string.
        max_len: Maximum length.

    Returns:
        Possibly truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
