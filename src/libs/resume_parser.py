"""
resume_parser.py
Extracts structured targeting data from plain_text_resume.yaml.
Handles both structured YAML resumes and converted documents (PDF/DOCX/TXT).
Used to drive bot search terms and ATS domain alignment.
"""
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List


# Any value that starts with '[' is a template placeholder
_PLACEHOLDER_PREFIX = "["

# Common job title seniority words for detecting title lines in raw text
_TITLE_HINTS = [
    "manager", "director", "analyst", "coordinator", "specialist",
    "supervisor", "lead", "head", "vp ", "vice president", "president",
    "officer", "consultant", "engineer", "planner", "buyer", "agent",
    "associate", "representative", "executive",
]


def _real(value: str) -> bool:
    """Return True if the value is a filled-in string, not a template placeholder."""
    return bool(value and not str(value).strip().startswith(_PLACEHOLDER_PREFIX))


def load_resume(resume_path: Path) -> Dict[str, Any]:
    """Load resume YAML and return as dict (empty dict on any error)."""
    try:
        with open(resume_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Raw-text helpers (for converted PDF/DOCX/TXT resumes)
# ---------------------------------------------------------------------------

def _extract_positions_from_text(text: str) -> List[str]:
    """Heuristic: return lines that look like job titles."""
    positions: List[str] = []
    seen: set = set()
    for line in text.splitlines():
        line = line.strip()
        if 4 <= len(line) <= 80:
            lower = line.lower()
            if any(hint in lower for hint in _TITLE_HINTS):
                # Skip lines that are clearly sentences (contain ". ")
                if ". " not in line and len(line.split()) <= 8:
                    normalized = line.title()
                    if normalized not in seen:
                        positions.append(normalized)
                        seen.add(normalized)
    return positions[:6]


def _extract_skills_from_text(text: str) -> List[str]:
    """Pull lines under 'Skills' or 'Competencies' headings, plus comma lists."""
    skills: List[str] = []
    seen: set = set()
    in_skills = False
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if re.match(r"^(skills|core competencies|competencies|technical skills)", lower):
            in_skills = True
            continue
        if in_skills:
            if not stripped or re.match(r"^[A-Z][a-z]+ [A-Z]", stripped):
                # Blank line or new section heading → stop
                if not stripped:
                    in_skills = False
                    continue
            # Parse comma or pipe separated items
            parts = re.split(r"[,|•·]", stripped)
            for p in parts:
                p = p.strip(" -·•")
                if 2 <= len(p) <= 50 and p not in seen:
                    skills.append(p)
                    seen.add(p)
    return skills[:20]


def _extract_name_from_text(text: str) -> str:
    """Take the first non-empty line as the name (common resume convention)."""
    for line in text.splitlines():
        line = line.strip()
        if line and len(line.split()) <= 5:
            return line
    return "Unknown"


# ---------------------------------------------------------------------------
# Structured YAML helpers
# ---------------------------------------------------------------------------

def extract_positions(resume_path: Path) -> List[str]:
    resume = load_resume(resume_path)

    if resume.get("_converted"):
        return _extract_positions_from_text(resume.get("raw_text", ""))

    seen: set = set()
    positions: List[str] = []

    prefs = resume.get("job_preferences") or {}
    for p in prefs.get("desired_positions") or []:
        p = str(p).strip()
        if _real(p) and p not in seen:
            positions.append(p)
            seen.add(p)

    for exp in resume.get("experience_details") or []:
        pos = str(exp.get("position", "")).strip()
        if _real(pos) and pos not in seen:
            positions.append(pos)
            seen.add(pos)

    return positions


def extract_skills(resume_path: Path) -> List[str]:
    resume = load_resume(resume_path)

    if resume.get("_converted"):
        return _extract_skills_from_text(resume.get("raw_text", ""))

    seen: set = set()
    skills: List[str] = []
    for exp in resume.get("experience_details") or []:
        for skill in exp.get("skills_acquired") or []:
            s = str(skill).strip()
            if _real(s) and s not in seen:
                skills.append(s)
                seen.add(s)
    return skills


def extract_industries(resume_path: Path) -> List[str]:
    resume = load_resume(resume_path)
    if resume.get("_converted"):
        return []   # too unreliable from raw text

    seen: set = set()
    industries: List[str] = []
    for exp in resume.get("experience_details") or []:
        ind = str(exp.get("industry", "")).strip()
        if _real(ind) and ind not in seen:
            industries.append(ind)
            seen.add(ind)
    return industries


def extract_summary(resume_path: Path) -> Dict[str, Any]:
    """
    Return a lightweight summary dict for the web UI.
    Works for both structured YAML and converted (PDF/DOCX/TXT) resumes.
    """
    resume = load_resume(resume_path)

    if resume.get("_converted"):
        raw = resume.get("raw_text", "")
        positions = _extract_positions_from_text(raw)
        skills = _extract_skills_from_text(raw)
        name = _extract_name_from_text(raw)
        return {
            "name": name,
            "positions": positions,
            "skills": skills[:20],
            "industries": [],
            "experience_count": len(positions),
            "has_real_data": bool(raw.strip()),
            "source_format": resume.get("_source_format", "unknown"),
        }

    pi = resume.get("personal_information") or {}
    first = str(pi.get("name", "")).strip()
    last = str(pi.get("surname", "")).strip()
    name = " ".join(p for p in [first, last] if _real(p)) or "Unknown"

    positions = extract_positions(resume_path)
    skills = extract_skills(resume_path)
    industries = extract_industries(resume_path)

    exp_count = sum(
        1
        for e in (resume.get("experience_details") or [])
        if _real(str(e.get("company", "")))
    )

    has_real_data = bool(positions or skills or exp_count)

    return {
        "name": name,
        "positions": positions,
        "skills": skills[:20],
        "industries": industries,
        "experience_count": exp_count,
        "has_real_data": has_real_data,
        "source_format": "yaml",
    }

