"""
resume_converter.py
===================
Convert resume files in any common format (PDF, DOCX, TXT, RTF, YAML/YML)
into:
  1. A plain-text string  (used as the LLM context)
  2. A normalised YAML dict (used as the structured data store)

The YAML output uses the same schema as data_folder/plain_text_resume.yaml so
the rest of the system can treat it identically regardless of upload format.

Supported input formats
-----------------------
  .pdf   → pdfminer.six (already in requirements)
  .docx  → python-docx  (already in requirements)
  .rtf   → striprtf     (already in requirements)
  .txt   → plain read
  .yaml / .yml → yaml.safe_load (no conversion needed)
"""

from __future__ import annotations

import io
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from src.logging import logger


# ---------------------------------------------------------------------------
# Text extractors
# ---------------------------------------------------------------------------

def _extract_pdf(file_bytes: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text as _pdf_extract
        return _pdf_extract(io.BytesIO(file_bytes))
    except Exception as exc:
        logger.error(f"PDF extraction failed: {exc}")
        return ""


def _extract_docx(file_bytes: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(para.text for para in doc.paragraphs)
    except Exception as exc:
        logger.error(f"DOCX extraction failed: {exc}")
        return ""


def _extract_rtf(file_bytes: bytes) -> str:
    try:
        from striprtf.striprtf import rtf_to_text
        return rtf_to_text(file_bytes.decode("latin-1", errors="replace"))
    except Exception as exc:
        logger.error(f"RTF extraction failed: {exc}")
        return ""


def _extract_txt(file_bytes: bytes) -> str:
    # Try UTF-8, then chardet fallback
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            import chardet
            enc = chardet.detect(file_bytes).get("encoding") or "latin-1"
            return file_bytes.decode(enc, errors="replace")
        except Exception:
            return file_bytes.decode("latin-1", errors="replace")


def _extract_yaml(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".rtf", ".txt", ".yaml", ".yml", ".doc"}


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return raw text from the uploaded file."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(file_bytes)
    elif ext == ".docx" or ext == ".doc":
        return _extract_docx(file_bytes)
    elif ext == ".rtf":
        return _extract_rtf(file_bytes)
    elif ext in (".yaml", ".yml"):
        return _extract_yaml(file_bytes)
    else:  # .txt and anything else
        return _extract_txt(file_bytes)


# ---------------------------------------------------------------------------
# YAML normaliser
# If the file is already YAML and matches our schema → use it directly.
# Otherwise, store the raw text under a "raw_text" key so the rest of the
# system can still pass it to the LLM for ATS scoring.
# ---------------------------------------------------------------------------

def _is_schema_yaml(data: Any) -> bool:
    """True if the parsed YAML looks like our resume schema."""
    if not isinstance(data, dict):
        return False
    expected_keys = {"personal_information", "experience_details", "education_details"}
    return bool(expected_keys & set(data.keys()))


def to_resume_yaml(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Parse a resume file and return a dict in our resume schema.

    For YAML/YML that already matches the schema → returned as-is.
    For all other formats → returns a minimal dict with the raw text so
    the LLM can work with it for ATS scoring and tailoring.
    """
    ext = Path(filename).suffix.lower()

    if ext in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(file_bytes.decode("utf-8", errors="replace"))
            if _is_schema_yaml(data):
                return data
        except Exception:
            pass

    # Non-YAML or malformed YAML → extract text
    raw_text = extract_text(file_bytes, filename)
    return {
        "raw_text": raw_text,
        "_source_format": ext.lstrip("."),
        "_converted": True,
    }


def save_resume(file_bytes: bytes, filename: str, dest_path: Path) -> Dict[str, Any]:
    """
    Save the resume to *dest_path* (always as .yaml).
    Returns the parsed resume dict.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    resume_dict = to_resume_yaml(file_bytes, filename)

    with open(dest_path, "w", encoding="utf-8") as fh:
        yaml.dump(resume_dict, fh, allow_unicode=True, default_flow_style=False)

    return resume_dict


def resume_to_text(resume_yaml_path: Path) -> str:
    """
    Load a resume YAML (possibly from a converted non-YAML source) and return
    a single string LLMs can read.
    """
    try:
        with open(resume_yaml_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return ""

    if data.get("_converted"):
        return data.get("raw_text", "")

    # Structured schema: flatten into readable lines
    lines: list[str] = []

    pi = data.get("personal_information", {})
    if pi.get("name") or pi.get("surname"):
        lines.append(f"{pi.get('name','')} {pi.get('surname','')}".strip())

    for exp in data.get("experience_details", []):
        lines.append(
            f"[Experience] {exp.get('position','')} at {exp.get('company','')} "
            f"({exp.get('employment_period','')})"
        )
        for resp_dict in exp.get("key_responsibilities", []):
            if isinstance(resp_dict, dict):
                lines.extend(resp_dict.values())
            elif isinstance(resp_dict, str):
                lines.append(resp_dict)
        for skill in exp.get("skills_acquired", []):
            lines.append(f"  Skill: {skill}")

    for edu in data.get("education_details", []):
        lines.append(
            f"[Education] {edu.get('education_level','')} in "
            f"{edu.get('field_of_study','')} at {edu.get('institution','')}"
        )

    for cert in data.get("certifications", []):
        lines.append(f"[Cert] {cert.get('name','')} - {cert.get('description','')}")

    for proj in data.get("projects", []):
        lines.append(f"[Project] {proj.get('name','')} - {proj.get('description','')}")

    return "\n".join(lines)
