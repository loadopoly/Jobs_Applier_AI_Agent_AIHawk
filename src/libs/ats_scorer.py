import json
import yaml
from pathlib import Path
from typing import Dict, Any, List
from src.logging import logger


DEFAULT_IN_SCOPE_KEYWORDS = [
    "supply chain",
    "operations",
    "operational",
    "logistics",
    "procurement",
    "inventory",
    "warehouse",
    "demand planning",
    "planning",
    "vendor management",
    "s&op",
    "erp",
]

DEFAULT_OUT_OF_SCOPE_KEYWORDS = [
    "software engineer",
    "software developer",
    "frontend",
    "backend",
    "full stack",
    "site reliability",
    "devops engineer",
]


class ATSScorer:
    def __init__(self, ai_adapter):
        self.ai_adapter = ai_adapter

    def score_job(self, resume_yaml_path: Path, job_description: str) -> Dict[str, Any]:
        """
        Scores a job description against a resume and provides actionable feedback.
        """
        try:
            with open(resume_yaml_path, 'r') as f:
                resume_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read resume at {resume_yaml_path}: {e}")
            return self._error_response("Could not read resume file.")
        
        prompt = f"""
        You are an expert ATS (Applicant Tracking System) and Technical Recruiter.
        Analyze the following Resume (in YAML format) against the Job Description.

        RESUME:
        {resume_content}

        JOB DESCRIPTION:
        {job_description}

        Provide a JSON response with the following fields:
        - score: A number from 0-100 indicating match.
        - match_summary: A 2-3 sentence summary of why the candidate matches or not.
        - missing_keywords: A list of key skills or technologies from the job description missing in the resume.
        - strong_points: A list of areas where the resume strongly matches the job.
        - survival_tweaks: 3-5 specific, actionable changes to the resume (e.g., rephrasing a bullet point) to increase the ATS score.

        Return ONLY the JSON.
        """

        if self.ai_adapter is None:
            data = self._heuristic_score_data(resume_content, job_description)
            return self._apply_alignment_adjustments(data, resume_content, job_description)
        
        try:
            logger.info("Requesting ATS score from LLM...")
            response = self.ai_adapter.invoke(prompt)
            
            # Extract content from response (handling LangChain message objects)
            content = getattr(response, 'content', str(response))
                
            # Clean JSON if it has markdown blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # Ensure it's valid JSON
            data = json.loads(content)
            data = self._apply_alignment_adjustments(data, resume_content, job_description)
            return data
        except Exception as e:
            logger.error(f"Error scoring job with LLM: {e}")
            fallback = self._heuristic_score_data(resume_content, job_description)
            fallback["match_summary"] = f"LLM unavailable, used heuristic scoring. Reason: {e}"
            return self._apply_alignment_adjustments(fallback, resume_content, job_description)

    def _apply_alignment_adjustments(
        self,
        score_data: Dict[str, Any],
        resume_content: str,
        job_description: str,
    ) -> Dict[str, Any]:
        base_score = self._safe_score(score_data.get("score", 0))

        role_alignment = self._compute_role_alignment(resume_content, job_description)
        adjusted_score = max(0, min(100, base_score + role_alignment["adjustment"]))

        if role_alignment["hard_mismatch"]:
            adjusted_score = min(adjusted_score, 45)

        score_data["base_score"] = base_score
        score_data["alignment_adjustment"] = role_alignment["adjustment"]
        score_data["alignment_notes"] = role_alignment["notes"]
        score_data["score"] = adjusted_score
        return score_data

    def _compute_role_alignment(self, resume_content: str, job_description: str) -> Dict[str, Any]:
        resume_text = resume_content.lower()
        jd_text = job_description.lower()

        in_scope_hits = [keyword for keyword in DEFAULT_IN_SCOPE_KEYWORDS if keyword in jd_text]
        out_scope_hits = [keyword for keyword in DEFAULT_OUT_OF_SCOPE_KEYWORDS if keyword in jd_text]

        resume_strength_hits = [keyword for keyword in DEFAULT_IN_SCOPE_KEYWORDS if keyword in resume_text]

        adjustment = min(len(in_scope_hits) * 3, 15)
        adjustment -= min(len(out_scope_hits) * 8, 32)

        if resume_strength_hits and in_scope_hits:
            adjustment += 5

        hard_mismatch = len(out_scope_hits) >= 2 and len(in_scope_hits) == 0

        notes = {
            "in_scope_hits": in_scope_hits,
            "out_of_scope_hits": out_scope_hits,
            "resume_strength_hits": resume_strength_hits,
            "hard_mismatch": hard_mismatch,
        }

        return {"adjustment": adjustment, "hard_mismatch": hard_mismatch, "notes": notes}

    @staticmethod
    def _safe_score(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _heuristic_score_data(self, resume_content: str, job_description: str) -> Dict[str, Any]:
        resume_tokens = set(resume_content.lower().replace("\n", " ").split())
        jd_tokens = set(job_description.lower().replace("\n", " ").split())

        overlap = len(resume_tokens & jd_tokens)
        coverage = int(min(100, overlap * 2))

        return {
            "score": coverage,
            "match_summary": "Heuristic ATS estimate based on token overlap.",
            "missing_keywords": [],
            "strong_points": [],
            "survival_tweaks": [
                "Use role-specific keywords from the job posting in your experience bullets.",
                "Quantify outcomes in operations/supply chain terms (cost, cycle time, fill rate).",
                "Place the exact role title in your headline if it matches your target role.",
            ],
        }

    def _error_response(self, message: str) -> Dict[str, Any]:
        return {
            "score": 0,
            "match_summary": message,
            "missing_keywords": [],
            "strong_points": [],
            "survival_tweaks": []
        }
