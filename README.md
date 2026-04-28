#  AI Job Application Bot

An AI-powered automation system that scrapes job listings, scores them against your resume using Claude, generates personalised cover letters, and auto-fills applications — all from the command line.

---

##  Features

| Feature | Details |
|---|---|
| **Multi-source scraping** | LinkedIn-style boards + generic boards (Remotive) |
| **AI match scoring** | Claude API scores each job 0–100 against your resume |
| **Cover letter generation** | Personalised letter per job using Claude |
| **Auto form-filling** | Playwright fills name, email, phone, LinkedIn, cover letter, resume upload |
| **Human-like behaviour** | Random typing delays, scroll simulation, randomised wait times |
| **CAPTCHA-safe fallback** | Detects CAPTCHAs and skips — does NOT attempt bypass |
| **Deduplication** | SHA-256 hash of title+company+URL prevents re-applying |
| **Retry system** | Exponential back-off for failed applications |
| **Keyword filtering** | Include/exclude keywords, title matching, location filtering |
| **CSV persistence** | All jobs and applications saved to `data/` |
| **Streamlit dashboard** | Visual monitoring of scores, statuses, and analytics |
| **Dry-run mode** | Test the full pipeline without actually submitting |

---

## 📁 Project Structure

```
ai-job-bot/
├── main.py                   # Entry point — orchestrates the full pipeline
├── config.py                 # Centralised config (env vars + job_prefs.json)
├── dashboard.py              # Streamlit monitoring dashboard
├── job_prefs.json            # Job search preferences (titles, keywords, locations)
├── .env.example              # Environment variable template
├── requirements.txt
│
├── scraper/
│   ├── job_scraper.py        # Orchestrates all site handlers in one browser session
│   └── site_handlers.py      # Per-site scraping logic (LinkedIn-mock, Remotive/generic)
│
├── ai/
│   ├── matcher.py            # Claude API: resume ↔ job scoring (0–100 JSON output)
│   └── cover_letter.py       # Claude API: personalised cover letter generation
│
├── automation/
│   ├── apply_bot.py          # Playwright bot: navigation, CAPTCHA check, submission
│   └── form_filler.py        # Human-like form field filling with randomised delays
│
├── utils/
│   ├── logger.py             # Coloured console + rotating file logger
│   ├── resume_parser.py      # PDF/DOCX resume parser → structured dict
│   └── helpers.py            # DataStore (CSV), hashing, keyword matching, delays
│
└── data/
    ├── jobs.csv              # All scraped jobs with match scores
    └── applications.csv      # Application history with statuses
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/yourname/ai-job-bot.git
cd ai-job-bot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and fill in your ANTHROPIC_API_KEY and personal details
```

Edit `job_prefs.json` to set your target roles, keywords, and locations.

### 3. Run

```bash
# Full pipeline (scrape → score → generate letters → apply)
python main.py --resume resume.pdf

# Visible browser (watch it work)
python main.py --resume resume.pdf --mode visible

# Dry run (no form submission)
python main.py --resume resume.pdf --dry-run

# Increase batch size
python main.py --resume resume.pdf --batch 20

# Retry failed applications
python main.py --retry

# Open dashboard
streamlit run dashboard.py
```

---

## ⚙️ Configuration

### `.env` file

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Required.** Your Anthropic API key | — |
| `CLAUDE_MODEL` | Claude model to use | `claude-sonnet-4-20250514` |
| `RESUME_PATH` | Path to your resume file | `resume.pdf` |
| `MIN_MATCH_SCORE` | Minimum score to attempt application | `60` |
| `APPLICANT_NAME` | Your full name | — |
| `APPLICANT_EMAIL` | Your email address | — |
| `APPLICANT_PHONE` | Your phone number | — |
| `APPLICANT_LINKEDIN` | LinkedIn profile URL | — |
| `APPLICANT_GITHUB` | GitHub profile URL | — |
| `APPLICANT_PORTFOLIO` | Portfolio / personal site URL | — |
| `APPLICANT_LOCATION` | Your city / location | — |
| `TYPING_DELAY_MIN` | Min ms between keystrokes | `50` |
| `TYPING_DELAY_MAX` | Max ms between keystrokes | `150` |
| `MAX_RETRIES` | Retry attempts per application | `3` |

### `job_prefs.json`

```json
{
  "job_titles": ["Software Engineer", "Backend Engineer"],
  "keywords": ["Python", "Django", "FastAPI"],
  "exclude_keywords": ["10+ years", "clearance required"],
  "locations": ["Remote", "San Francisco, CA"],
  "experience_level": ["mid-level"],
  "job_types": ["full-time"],
  "scrape_sources": ["linkedin_mock", "generic_board"],
  "min_salary": 80000,
  "max_salary": 200000
}
```

---

## Architecture

```
main.py
  │
  ├── ResumeParser      → extracts skills, experience, education from PDF/DOCX
  │
  ├── JobScraper        → launches Playwright, runs all site handlers
  │     ├── LinkedInMockHandler    (linkedin_mock)
  │     └── GenericBoardHandler    (generic_board / Remotive)
  │
  ├── DataStore         → deduplicates, saves jobs.csv
  │
  ├── JobMatcher        → Claude API → JSON score + reasons
  │
  ├── CoverLetterGenerator → Claude API → personalised letter
  │
  └── ApplyBot          → Playwright bot
        └── FormFiller  → human-like field filling
```

---

## Adding a New Job Board

1. Create a new class in `scraper/site_handlers.py` inheriting `BaseSiteHandler`
2. Set `SOURCE_ID = "my_board"`
3. Implement `async def scrape(self, page: Page) -> list[dict]`
4. Register it: `HANDLER_REGISTRY["my_board"] = MyBoardHandler`
5. Add `"my_board"` to `scrape_sources` in `job_prefs.json`

---

## Ethics & Legal

- **Respect robots.txt** and each site's Terms of Service
- This tool is built for **personal job searching only** — not commercial scraping
- The CAPTCHA handling is a **skip/fallback only** — no bypassing attempts
- Rate limiting and human-like delays are built in to be respectful to servers
- Never scrape platforms that explicitly prohibit it in their ToS without authorisation

---

## Dashboard

```bash
streamlit run dashboard.py
```

The dashboard provides:
- KPI cards: jobs scraped, avg match score, applications sent, success rate
- Filterable job table with match score progress bars
- Application history with status icons
- One-click retry for failed applications
- Score distribution and status breakdown charts

---

## Troubleshooting

**`ANTHROPIC_API_KEY` not set**
→ Copy `.env.example` to `.env` and add your key.

**Resume not parsing**
→ Ensure the file is not password-protected. Try a text-based PDF (not scanned).

**No jobs found**
→ Check `job_prefs.json` — titles must loosely match what sites show.
→ Some boards block headless browsers; try `--mode visible`.

**All applications failing**
→ Run with `--dry-run` first to inspect form filling without submitting.
→ Check `logs/screenshots/` for page snapshots at point of failure.

**CAPTCHA skips**
→ Expected — the bot detects and skips CAPTCHA-protected pages safely.
→ Use `--mode visible` and handle manually for those sites.

---

## License

MIT License — see `LICENSE` for details.
