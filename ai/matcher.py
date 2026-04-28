import json
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
                        "temperature": 0.1,
                        "num_predict": 300
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


def match_resume_to_job(resume_text: str, job_description: str) -> dict:
    """
    Match resume against job description using local Llama.
    Returns a dict with score and reasoning.
    """
    # Keep prompt very short so Llama responds fast and reliably
    resume_short = str(resume_text)[:400].replace("\n", " ")
    job_short = str(job_description)[:300].replace("\n", " ")

    prompt = (
        f"You are a recruiter. Score this resume against this job.\n"
        f"RESUME: {resume_short}\n"
        f"JOB: {job_short}\n"
        f"Reply with ONLY valid JSON, no explanation, no markdown:\n"
        f'{{"score": 70, "matching_skills": ["skill1"], "missing_skills": ["skill2"], '
        f'"reasoning": "reason here", "reasons": "reason here", "recommendation": "apply"}}'
    )

    logger.info("Scoring job with Llama...")
    raw = call_ollama(prompt)

    # If empty response, return safe fallback immediately
    if not raw:
        logger.warning("Ollama returned empty response, using fallback score.")
        return _fallback_result("No response from Ollama")

    # Try to extract JSON from response
    try:
        # Find JSON block in response
        start = raw.find("{")
        end = raw.rfind("}") + 1

        if start == -1 or end == 0:
            logger.warning("No JSON found in Ollama response, using fallback.")
            return _fallback_result(raw[:200])

        json_str = raw[start:end]
        result = json.loads(json_str)

        # Ensure all required keys exist
        result.setdefault("score", 50)
        result.setdefault("matching_skills", [])
        result.setdefault("missing_skills", [])
        result.setdefault("reasoning", "")
        result.setdefault("reasons", result.get("reasoning", ""))
        result.setdefault("recommendation", "apply")

        # Ensure score is a valid integer between 0-100
        try:
            result["score"] = max(0, min(100, int(result["score"])))
        except (ValueError, TypeError):
            result["score"] = 50

        logger.info(f"Match score: {result['score']}/100")
        return result

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Could not parse JSON from Llama: {e}")
        return _fallback_result(raw[:200])


def _fallback_result(reason: str) -> dict:
    """Return a safe default result when Llama fails."""
    return {
        "score": 50,
        "matching_skills": [],
        "missing_skills": [],
        "reasoning": reason,
        "reasons": reason,
        "recommendation": "apply"
    }


class JobMatcher:
    """Wrapper class for compatibility with main.py"""

    def __init__(self, config=None) -> None:
        """Accept optional config argument for compatibility."""
        self.config = config

    def match(self, resume_text: str, job_description: str) -> dict:
        """Match resume to job and return score dict."""
        return match_resume_to_job(resume_text, job_description)

    def get_score(self, resume_text: str, job_description: str) -> int:
        """Return just the numeric score."""
        result = match_resume_to_job(resume_text, job_description)
        return result.get("score", 50)

    async def score(self, resume_data: any, job: any) -> dict:
        """Async score method for compatibility with main.py"""
        # Extract text from resume_data
        if isinstance(resume_data, dict):
            resume_text = resume_data.get("raw_text", "")
            if not resume_text:
                # Try other common keys
                resume_text = resume_data.get("text", str(resume_data))
        else:
            resume_text = str(resume_data)

        # Extract job description
        if isinstance(job, dict):
            job_description = job.get("description", "")
            if not job_description:
                # Try other common keys
                job_description = job.get("summary", str(job))
        else:
            job_description = str(job)

        return match_resume_to_job(resume_text, job_description)