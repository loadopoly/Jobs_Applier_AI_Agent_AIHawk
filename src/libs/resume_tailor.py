"""
resume_tailor.py
================
Generate a job-specific tailored version of the user's base resume.

For every job that clears the ATS threshold the bot:
  1. Calls ResumeTailor.tailor() which uses the LLM to rewrite bullets/
     headlines to incorporate missing keywords from the ATS analysis.
  2. Saves the result to   temp_resumes/<job_id>/
       resume_tailored.yaml    ← structured (same schema as base)
       resume_highlights.txt   ← human-readable with interview callouts
       resume_tailored.pdf     ← formatted PDF for delivery
  3. Returns the TailoredResume dataclass so BotManager can attach it to
     the JobApplication record.

Lifecycle
---------
  pending   → job just applied to, temp resume created
  discarded → rejection email received; PDF deleted, YAML kept for logging
  confirmed → pipeline confirmed; PDF + highlights delivered to user
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.libs.resume_converter import resume_to_text
from src.logging import logger


TEMP_RESUME_DIR = Path("temp_resumes")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TailoredResume:
    job_id: str
    job_title: str
    company: str
    base_resume_path: Path
    tailored_yaml_path: Path
    highlights_path: Path
    pdf_path: Optional[Path]
    ats_score: int
    status: str = "pending"   # pending | discarded | confirmed
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "ats_score": self.ats_score,
            "status": self.status,
            "created_at": self.created_at,
            "tailored_yaml": str(self.tailored_yaml_path),
            "highlights": str(self.highlights_path),
            "pdf": str(self.pdf_path) if self.pdf_path else None,
        }


# ---------------------------------------------------------------------------
# Tailoring engine
# ---------------------------------------------------------------------------

class ResumeTailor:
    """
    Uses an LLM to produce a job-specific resume variant.
    Falls back to a rule-based approach when no LLM is available.
    """

    def __init__(self, ai_adapter=None):
        self.ai_adapter = ai_adapter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tailor(
        self,
        base_resume_path: Path,
        job_description: str,
        ats_analysis: Dict[str, Any],
        job_id: str,
        job_title: str,
        company: str,
    ) -> TailoredResume:
        """Create tailored resume; return TailoredResume instance."""
        out_dir = TEMP_RESUME_DIR / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        resume_text = resume_to_text(base_resume_path)

        if self.ai_adapter:
            tailored_text, highlights = self._llm_tailor(
                resume_text, job_description, ats_analysis, job_title, company
            )
        else:
            tailored_text, highlights = self._rule_tailor(
                resume_text, ats_analysis
            )

        # Persist
        tailored_yaml_path = out_dir / "resume_tailored.yaml"
        highlights_path = out_dir / "resume_highlights.txt"

        self._save_tailored_yaml(base_resume_path, tailored_text, tailored_yaml_path)
        highlights_path.write_text(highlights, encoding="utf-8")

        pdf_path: Optional[Path] = None
        try:
            pdf_path = self._generate_pdf(tailored_text, highlights, out_dir, job_title, company)
        except Exception as exc:
            logger.warning(f"PDF generation skipped: {exc}")

        ats_score = int(ats_analysis.get("score", 0))
        return TailoredResume(
            job_id=job_id,
            job_title=job_title,
            company=company,
            base_resume_path=base_resume_path,
            tailored_yaml_path=tailored_yaml_path,
            highlights_path=highlights_path,
            pdf_path=pdf_path,
            ats_score=ats_score,
        )

    def discard(self, tailored: TailoredResume) -> None:
        """Mark as discarded (rejection). Delete PDF to save space."""
        tailored.status = "discarded"
        if tailored.pdf_path and tailored.pdf_path.exists():
            tailored.pdf_path.unlink()
            tailored.pdf_path = None
        self._save_metadata(tailored)
        logger.info(f"Temp resume discarded for job {tailored.job_id}")

    def confirm(self, tailored: TailoredResume) -> Dict[str, Any]:
        """Mark as confirmed (pipeline). Returns delivery payload."""
        tailored.status = "confirmed"
        self._save_metadata(tailored)
        logger.info(f"Temp resume confirmed for job {tailored.job_id}")
        return tailored.to_dict()

    # ------------------------------------------------------------------
    # LLM tailoring
    # ------------------------------------------------------------------

    def _llm_tailor(
        self,
        resume_text: str,
        job_description: str,
        ats_analysis: Dict[str, Any],
        job_title: str,
        company: str,
    ):
        missing = ats_analysis.get("missing_keywords", [])
        tweaks = ats_analysis.get("survival_tweaks", [])
        strong = ats_analysis.get("strong_points", [])

        prompt = f"""
You are an expert resume writer specialising in Supply Chain, Operations and Logistics management.

TASK: Rewrite the candidate's resume to maximise ATS match for the target role below.

TARGET ROLE: {job_title} at {company}

JOB DESCRIPTION (excerpt):
{job_description[:3000]}

CURRENT RESUME:
{resume_text}

ATS ANALYSIS:
- Missing keywords: {json.dumps(missing)}
- Suggested tweaks: {json.dumps(tweaks)}
- Strong points already present: {json.dumps(strong)}

RULES:
1. Keep ALL real experience, education and dates — do NOT invent facts.
2. Rephrase bullet points to naturally include missing keywords where truthful.
3. Add a concise 3-line "Professional Summary" at the top if none exists.
4. Return a JSON object with two keys:
   "tailored_resume": the full rewritten resume as a single plain-text string
     (use markdown-like formatting: ## Section, - bullet).
   "interview_highlights": a list of 5-8 strings, each being a specific
     talking point the candidate should prepare for this role/company.

Return ONLY the JSON.
"""
        try:
            response = self.ai_adapter.invoke(prompt)
            content = getattr(response, "content", str(response))
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            data = json.loads(content)
            tailored_text = data.get("tailored_resume", resume_text)
            highlights_list = data.get("interview_highlights", [])
            highlights = self._format_highlights(highlights_list, job_title, company)
            return tailored_text, highlights
        except Exception as exc:
            logger.error(f"LLM tailoring failed: {exc}")
            return self._rule_tailor(resume_text, ats_analysis)

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _rule_tailor(self, resume_text: str, ats_analysis: Dict[str, Any]):
        missing = ats_analysis.get("missing_keywords", [])
        tweaks = ats_analysis.get("survival_tweaks", [])

        appended = ""
        if missing:
            kw_line = ", ".join(missing[:10])
            appended = (
                f"\n\n## Core Competencies (ATS-Enhanced)\n"
                f"- {kw_line}\n"
            )

        tailored_text = resume_text + appended
        highlights = self._format_highlights(tweaks, "target role", "this company")
        return tailored_text, highlights

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save_tailored_yaml(
        self, base_path: Path, tailored_text: str, dest: Path
    ) -> None:
        """Store tailored content alongside original structured data."""
        try:
            with open(base_path, "r", encoding="utf-8") as fh:
                base_data = yaml.safe_load(fh) or {}
        except Exception:
            base_data = {}

        base_data["_tailored_text"] = tailored_text
        base_data["_tailored"] = True
        with open(dest, "w", encoding="utf-8") as fh:
            yaml.dump(base_data, fh, allow_unicode=True, default_flow_style=False)

    def _save_metadata(self, tailored: TailoredResume) -> None:
        meta_path = TEMP_RESUME_DIR / tailored.job_id / "metadata.yaml"
        with open(meta_path, "w", encoding="utf-8") as fh:
            yaml.dump(tailored.to_dict(), fh, allow_unicode=True)

    @staticmethod
    def _format_highlights(items: List[str], job_title: str, company: str) -> str:
        lines = [
            f"INTERVIEW PREPARATION GUIDE",
            f"Role: {job_title}  |  Company: {company}",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "=" * 60,
            "",
            "KEY TALKING POINTS FOR YOUR INTERVIEW:",
            "",
        ]
        for i, item in enumerate(items, 1):
            wrapped = textwrap.fill(str(item), width=72, subsequent_indent="     ")
            lines.append(f"  {i}. {wrapped}")
        lines += [
            "",
            "=" * 60,
            "TIP: Practice each point with a STAR story (Situation, Task,",
            "     Action, Result) before your interview.",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # PDF generation via reportlab
    # ------------------------------------------------------------------

    def _generate_pdf(
        self,
        tailored_text: str,
        highlights: str,
        out_dir: Path,
        job_title: str,
        company: str,
    ) -> Path:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
        )

        pdf_path = out_dir / "resume_tailored.pdf"
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=LETTER,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceAfter=4)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceAfter=2, textColor=colors.HexColor("#1a56db"))
        body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, spaceAfter=3, leading=13)
        small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.gray)

        story = []

        # ── Header ──
        story.append(Paragraph(f"Tailored Resume: {job_title} @ {company}", h1))
        story.append(Paragraph("ATS-Optimised — Confidential", small))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a56db")))
        story.append(Spacer(1, 0.15 * inch))

        # ── Resume body ──
        for line in tailored_text.splitlines():
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.05 * inch))
            elif line.startswith("## "):
                story.append(Paragraph(line[3:], h2))
            elif line.startswith("# "):
                story.append(Paragraph(line[2:], h1))
            elif line.startswith("- "):
                story.append(Paragraph(f"• {line[2:]}", body))
            else:
                story.append(Paragraph(line, body))

        # ── Highlights on page 2 ──
        story.append(PageBreak())
        story.append(Paragraph("Interview Highlights", h1))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a56db")))
        story.append(Spacer(1, 0.1 * inch))
        for line in highlights.splitlines():
            if not line.strip():
                story.append(Spacer(1, 0.04 * inch))
            else:
                story.append(Paragraph(line, body))

        doc.build(story)
        return pdf_path


# ---------------------------------------------------------------------------
# Registry: load all pending tailored resumes from disk
# ---------------------------------------------------------------------------

def list_tailored_resumes() -> List[Dict[str, Any]]:
    """Return metadata for all tailored resumes on disk."""
    results = []
    if not TEMP_RESUME_DIR.exists():
        return results
    for meta_file in sorted(TEMP_RESUME_DIR.glob("*/metadata.yaml")):
        try:
            with open(meta_file, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            results.append(data)
        except Exception:
            pass
    return results


def load_tailored_resume(job_id: str) -> Optional[TailoredResume]:
    """Reconstruct TailoredResume from saved metadata."""
    meta_path = TEMP_RESUME_DIR / job_id / "metadata.yaml"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            d = yaml.safe_load(fh) or {}
        return TailoredResume(
            job_id=d["job_id"],
            job_title=d["job_title"],
            company=d["company"],
            base_resume_path=Path(d.get("tailored_yaml", "")),
            tailored_yaml_path=Path(d.get("tailored_yaml", "")),
            highlights_path=Path(d.get("highlights", "")),
            pdf_path=Path(d["pdf"]) if d.get("pdf") else None,
            ats_score=int(d.get("ats_score", 0)),
            status=d.get("status", "pending"),
            created_at=d.get("created_at", ""),
        )
    except Exception as exc:
        logger.error(f"Failed to load tailored resume for {job_id}: {exc}")
        return None
