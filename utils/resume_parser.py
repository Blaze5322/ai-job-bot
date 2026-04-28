"""
Resume Parser
=============
Extracts structured data from PDF and DOCX resumes.
Returns a normalised dict used by the AI matcher and form filler.
"""

import re
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


class ResumeParser:
    """
    Parse a resume file (PDF or DOCX) into a structured dictionary.

    Extracted fields:
        - raw_text   : full plain-text of the document
        - name       : candidate's full name (heuristic)
        - email      : email address
        - phone      : phone number
        - linkedin   : LinkedIn URL
        - github     : GitHub URL
        - skills     : list of detected skill tokens
        - experience : list of experience block strings
        - education  : list of education block strings
        - summary    : professional summary / objective paragraph
    """

    # Common skill keywords used for naive extraction
    SKILL_VOCAB = {
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
        "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
        "react", "vue", "angular", "nextjs", "nuxtjs", "svelte",
        "django", "flask", "fastapi", "express", "spring", "rails",
        "postgresql", "mysql", "sqlite", "mongodb", "redis", "elasticsearch",
        "docker", "kubernetes", "terraform", "ansible", "ci/cd",
        "aws", "gcp", "azure", "linux", "git", "graphql", "rest", "grpc",
        "machine learning", "deep learning", "nlp", "computer vision",
        "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
        "spark", "hadoop", "kafka", "airflow", "dbt",
        "html", "css", "tailwind", "sass",
        "agile", "scrum", "jira", "confluence",
    }

    def parse(self, file_path: str) -> dict[str, Any] | None:
        """
        Parse a resume from disk.

        Args:
            file_path: Absolute or relative path to a .pdf or .docx file.

        Returns:
            Structured resume dict, or None on failure.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Resume file not found: {file_path}")
            return None

        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                raw_text = self._extract_pdf(path)
            elif suffix in (".docx", ".doc"):
                raw_text = self._extract_docx(path)
            else:
                logger.error(f"Unsupported resume format: {suffix}")
                return None
        except Exception as exc:
            logger.exception(f"Failed to read resume: {exc}")
            return None

        if not raw_text.strip():
            logger.error("Resume appears to be empty or unreadable.")
            return None

        return self._structure(raw_text)

    # ── Private extraction helpers ───────────────────────────────

    def _extract_pdf(self, path: Path) -> str:
        """Extract plain text from a PDF using PyMuPDF (fitz)."""
        import fitz  # PyMuPDF

        text_parts: list[str] = []
        with fitz.open(str(path)) as doc:
            for page in doc:
                text_parts.append(page.get_text("text"))  # type: ignore[attr-defined]
        return "\n".join(text_parts)

    def _extract_docx(self, path: Path) -> str:
        """Extract plain text from a DOCX file using python-docx."""
        from docx import Document

        doc = Document(str(path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs)

    # ── Parsing / structuring ────────────────────────────────────

    def _structure(self, raw: str) -> dict[str, Any]:
        """
        Extract structured fields from raw resume text.

        Args:
            raw: Full plain-text content of the resume.

        Returns:
            Dictionary with parsed fields.
        """
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        return {
            "raw_text": raw,
            "name": self._extract_name(lines),
            "email": self._extract_email(raw),
            "phone": self._extract_phone(raw),
            "linkedin": self._extract_url(raw, "linkedin"),
            "github": self._extract_url(raw, "github"),
            "skills": self._extract_skills(raw),
            "experience": self._extract_section(raw, ["experience", "work history", "employment"]),
            "education": self._extract_section(raw, ["education", "academic background"]),
            "summary": self._extract_section(raw, ["summary", "objective", "profile"], max_chars=800),
        }

    @staticmethod
    def _extract_name(lines: list[str]) -> str:
        """
        Heuristic: the name is usually in the first 1-3 non-empty lines
        and doesn't look like an email, URL, or phone number.
        """
        for line in lines[:5]:
            if (
                len(line.split()) in range(2, 5)
                and "@" not in line
                and "http" not in line
                and not re.search(r"\d{3}", line)
            ):
                return line
        return lines[0] if lines else "Unknown"

    @staticmethod
    def _extract_email(text: str) -> str:
        match = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
        return match.group(0) if match else ""

    @staticmethod
    def _extract_phone(text: str) -> str:
        match = re.search(
            r"(\+?\d[\d\s\-().]{7,}\d)", text
        )
        return match.group(0).strip() if match else ""

    @staticmethod
    def _extract_url(text: str, domain: str) -> str:
        pattern = rf"https?://(?:www\.)?{re.escape(domain)}[\S]+"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0).rstrip(".,)") if match else ""

    def _extract_skills(self, text: str) -> list[str]:
        """
        Return list of recognised skills found in the resume text.
        Performs case-insensitive substring matching against SKILL_VOCAB.
        """
        text_lower = text.lower()
        found = []
        for skill in self.SKILL_VOCAB:
            # Use word-boundary matching for short tokens to avoid false positives
            pattern = rf"\b{re.escape(skill)}\b"
            if re.search(pattern, text_lower):
                found.append(skill)
        return sorted(found)

    @staticmethod
    def _extract_section(
        text: str,
        headers: list[str],
        max_chars: int = 3000,
    ) -> str:
        """
        Extract text under a section identified by one of the given headers.

        Args:
            text: Full resume text.
            headers: Candidate section header names (case-insensitive).
            max_chars: Maximum characters to return.

        Returns:
            Extracted section text (may be empty string).
        """
        pattern = "|".join(re.escape(h) for h in headers)
        # Match the header line (possibly surrounded by whitespace / decoration)
        section_re = re.compile(
            rf"(?:^|\n)(?:{pattern})[^\n]*\n(.*?)(?=\n[A-Z][^\n]{{3,}}\n|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        match = section_re.search(text)
        if match:
            return match.group(1).strip()[:max_chars]
        return ""
