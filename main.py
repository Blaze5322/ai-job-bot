"""
AI Job Application Bot - Main Entry Point
==========================================
Orchestrates the full pipeline: scraping, matching, and applying.
"""

import asyncio
import argparse
import sys
from pathlib import Path

from config import Config
from utils.logger import get_logger
from utils.resume_parser import ResumeParser
from scraper.job_scraper import JobScraper
from ai.matcher import JobMatcher
from ai.cover_letter import CoverLetterGenerator
from utils.helpers import DataStore

logger = get_logger(__name__)


async def run_pipeline(
    resume_path: str,
    mode: str = "headless",
    batch_size: int = 5,
    dry_run: bool = False,
) -> None:
    """
    Run the full job application pipeline.

    Args:
        resume_path: Path to the resume file (PDF or DOCX).
        mode: Browser mode - 'headless' or 'visible'.
        batch_size: Number of applications to process per run.
        dry_run: If True, skip actual form submission.
    """
    logger.info("=" * 60)
    logger.info("AI Job Application Bot starting...")
    logger.info("=" * 60)

    config = Config()
    data_store = DataStore(config)

    # ── Step 1: Parse Resume ────────────────────────────────────
    logger.info("Step 1/5 — Parsing resume...")
    parser = ResumeParser()
    resume_data = parser.parse(resume_path)
    if not resume_data:
        logger.error("Failed to parse resume. Exiting.")
        sys.exit(1)
    logger.info(f"Resume parsed. Skills detected: {len(resume_data.get('skills', []))}")

    # ── Step 2: Scrape Jobs ─────────────────────────────────────
    logger.info("Step 2/5 — Scraping job listings...")
    scraper = JobScraper(config)
    raw_jobs = await scraper.scrape_all()
    logger.info(f"Scraped {len(raw_jobs)} raw job listings.")

    # Deduplicate and filter
    new_jobs = data_store.filter_new_jobs(raw_jobs)
    logger.info(f"{len(new_jobs)} new jobs after deduplication.")

    if not new_jobs:
        logger.info("No new jobs found. Exiting.")
        return

    # ── Step 3: AI Matching ─────────────────────────────────────
    logger.info("Step 3/5 — Scoring jobs with AI...")
    matcher = JobMatcher(config)
    scored_jobs = []
    for job in new_jobs[:5]:
        try:
            score_result = await matcher.score(resume_data, job)
            job["match_score"] = score_result.get("score", 50)
            job["match_reasons"] = score_result.get("reasons", "")
            job["missing_skills"] = score_result.get("missing_skills", [])
            scored_jobs.append(job)
            data_store.save_job(job)
            logger.info(f"Scored: {job.get('title', 'Unknown')} — {job['match_score']}/100")
        except Exception as e:
            logger.warning(f"Scoring failed for job, skipping. Error: {e}")
            job["match_score"] = 50
            job["match_reasons"] = "Scoring failed"
            job["missing_skills"] = []
            scored_jobs.append(job)

    # Filter by minimum score
    qualified_jobs = [
        j for j in scored_jobs if j["match_score"] >= config.MIN_MATCH_SCORE
    ]
    qualified_jobs.sort(key=lambda x: x["match_score"], reverse=True)
    logger.info(
        f"{len(qualified_jobs)} jobs meet the minimum score "
        f"threshold of {config.MIN_MATCH_SCORE}."
    )

    if not qualified_jobs:
        logger.info("No qualified jobs found. Try lowering MIN_MATCH_SCORE in .env")
        return

    # Apply batch limit
    batch_jobs = qualified_jobs[:batch_size]
    logger.info(f"Processing batch of {len(batch_jobs)} jobs.")

    # ── Step 4: Generate Cover Letters ─────────────────────────
    logger.info("Step 4/5 — Generating cover letters...")
    cover_gen = CoverLetterGenerator(config)
    for job in batch_jobs:
        try:
            letter = await cover_gen.generate_async(
                resume_data, job, config.APPLICANT_NAME
            )
            job["cover_letter"] = letter
            logger.info(f"Cover letter generated for {job.get('company', 'Unknown')}")
        except Exception as e:
            logger.warning(f"Cover letter generation failed, using fallback. Error: {e}")
            job["cover_letter"] = (
                f"Dear Hiring Manager,\n\n"
                f"I am {config.APPLICANT_NAME} and I am excited to apply for "
                f"the {job.get('title', 'this')} position at "
                f"{job.get('company', 'your company')}.\n\n"
                f"Thank you for your consideration.\n\n"
                f"Sincerely,\n{config.APPLICANT_NAME}"
            )

    # ── Step 5: Apply ───────────────────────────────────────────
    logger.info("Step 5/5 — Submitting applications...")

    if dry_run:
        logger.info("DRY RUN MODE — No applications will be submitted.")
        for job in batch_jobs:
            logger.info(f"[DRY RUN] Would apply to: {job.get('title', 'Unknown')} @ {job.get('company', 'Unknown')}")
            logger.info(f"  Score: {job.get('match_score', 0)}/100")
            logger.info(f"  Cover letter preview: {job.get('cover_letter', '')[:100]}...")
            data_store.save_application(job, {"status": "dry_run"})
    else:
        try:
            from automation.apply_bot import ApplyBot
            bot = ApplyBot(config, headless=(mode == "headless"), dry_run=dry_run)
            async with bot:
                for job in batch_jobs:
                    try:
                        result = await bot.apply(job, resume_data)
                        data_store.save_application(job, result)
                        status = result.get("status", "unknown")
                        logger.info(f"[{status.upper()}] {job.get('title')} @ {job.get('company')}")
                    except Exception as e:
                        logger.error(f"Failed to apply to {job.get('title')}: {e}")
                        data_store.save_application(job, {"status": "failed"})
        except Exception as e:
            logger.error(f"ApplyBot failed: {e}")
            logger.info("Try running with --dry-run flag instead.")

    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info("=" * 60)


async def retry_failed(mode: str = "headless") -> None:
    """Retry all applications that previously failed."""
    config = Config()
    data_store = DataStore(config)
    parser = ResumeParser()

    failed = data_store.get_failed_applications()
    logger.info(f"Retrying {len(failed)} failed applications...")

    if not failed:
        logger.info("No failed applications to retry.")
        return

    resume_data = parser.parse(config.RESUME_PATH)

    try:
        from automation.apply_bot import ApplyBot
        bot = ApplyBot(config, headless=(mode == "headless"), dry_run=False)
        async with bot:
            for record in failed:
                job = record["job"]
                result = await bot.apply(job, resume_data)
                data_store.update_application(record["id"], result)
    except Exception as e:
        logger.error(f"Retry failed: {e}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Job Application Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --resume resume.pdf
  python main.py --resume resume.pdf --mode visible --batch 10
  python main.py --resume resume.pdf --dry-run
  python main.py --retry --mode visible
        """,
    )
    parser.add_argument("--resume", type=str, help="Path to resume (PDF/DOCX)")
    parser.add_argument(
        "--mode",
        choices=["headless", "visible"],
        default="headless",
        help="Browser mode (default: headless)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=5,
        help="Number of applications per run (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and match but do not submit applications",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Retry all previously failed applications",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.retry:
        asyncio.run(retry_failed(mode=args.mode))
    else:
        if not args.resume:
            print("Error: --resume is required unless using --retry")
            sys.exit(1)
        resume_file = Path(args.resume)
        if not resume_file.exists():
            print(f"Error: Resume file not found: {args.resume}")
            sys.exit(1)
        asyncio.run(
            run_pipeline(
                resume_path=str(resume_file),
                mode=args.mode,
                batch_size=args.batch,
                dry_run=args.dry_run,
            )
        )