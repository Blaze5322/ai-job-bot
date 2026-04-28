import logging
import time
import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"


def call_ollama(prompt: str) -> str:
    """Send a prompt to local Ollama and return response text."""
    for attempt in range(3):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 400
                    }
                },
                timeout=120
            )
            response.raise_for_status()
            result = response.json().get("response", "").strip()
            if result:
                return result
            logger.warning(f"Empty response from Ollama (attempt {attempt + 1}/3)")
            time.sleep(2)
        except requests.exceptions.ConnectionError:
            logger.error("Ollama is not running! Start it with: ollama serve")
            return ""
        except Exception as e:
            logger.warning(f"Ollama attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    return ""


def generate_cover_letter(
    resume_text: str,
    job_description: str,
    applicant_name: str,
    company_name: str = "the company"
) -> str:
    """
    Generate a personalized cover letter using local Llama.
    Returns the cover letter as a string.
    """
    # Keep prompt short so Llama responds reliably
    resume_short = str(resume_text)[:400].replace("\n", " ")
    job_short = str(job_description)[:300].replace("\n", " ")

    prompt = (
        f"Write a short 3-paragraph professional cover letter.\n"
        f"Applicant: {applicant_name}\n"
        f"Company: {company_name}\n"
        f"Resume: {resume_short}\n"
        f"Job: {job_short}\n"
        f"Start with: Dear Hiring Manager,"
    )

    logger.info(f"Generating cover letter for {company_name}...")
    cover_letter = call_ollama(prompt)

    if not cover_letter:
        logger.warning("Ollama returned empty cover letter, using fallback.")
        return (
            f"Dear Hiring Manager,\n\n"
            f"I am {applicant_name} and I am excited to apply for this position at {company_name}. "
            f"My background aligns well with your requirements and I am eager to contribute.\n\n"
            f"I have relevant experience that makes me a strong candidate for this role. "
            f"I am confident in my ability to deliver results and grow with your team.\n\n"
            f"Thank you for considering my application. I look forward to discussing this opportunity.\n\n"
            f"Sincerely,\n{applicant_name}"
        )

    logger.info("Cover letter generated successfully.")
    return cover_letter.strip()


class CoverLetterGenerator:
    """Wrapper class for compatibility with main.py"""

    def __init__(self, config=None) -> None:
        """Accept optional config argument for compatibility."""
        self.config = config

    def generate(self, resume_text: str, job_description: str,
                 applicant_name: str, company_name: str = "the company") -> str:
        """Generate a cover letter and return as string."""
        return generate_cover_letter(
            resume_text,
            job_description,
            applicant_name,
            company_name
        )

    async def generate_async(self, resume_data: any, job: any, applicant_name: str) -> str:
        """Async generate method for compatibility with main.py"""
        # Extract resume text
        if isinstance(resume_data, dict):
            resume_text = resume_data.get("raw_text", "")
            if not resume_text:
                resume_text = resume_data.get("text", str(resume_data))
        else:
            resume_text = str(resume_data)

        # Extract job details
        if isinstance(job, dict):
            job_description = job.get("description", "")
            if not job_description:
                job_description = job.get("summary", str(job))
            company_name = job.get("company", "the company")
        else:
            job_description = str(job)
            company_name = "the company"

        return generate_cover_letter(
            resume_text,
            job_description,
            applicant_name,
            company_name
        )