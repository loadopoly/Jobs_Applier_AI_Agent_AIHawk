import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import yaml

from src.application_stats import ApplicationStatsService
from src.bots.bot_manager import BotManager
from src.libs.ats_scorer import ATSScorer
from src.libs.email_monitor import (
    EmailMonitor, load_email_config, save_email_config,
)
from src.libs.llm_manager import AIAdapter
from src.libs.recruiter_prep import RecruiterPrepEngine
from src.libs.resume_converter import (
    SUPPORTED_EXTENSIONS, save_resume,
)
from src.libs.resume_parser import extract_summary, extract_positions
from src.libs.resume_tailor import (
    ResumeTailor, list_tailored_resumes, load_tailored_resume,
)
from src.logging import logger

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RunBatchRequest(BaseModel):
    platform: Literal["linkedin", "indeed", "all"] = "linkedin"
    count: int = Field(default=5, ge=1, le=100)
    dry_run: bool = True
    positions: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    min_suitability_score: Optional[int] = Field(default=None, ge=0, le=100)


class ATSRequest(BaseModel):
    job_description: str = Field(min_length=20)


class RecruiterBriefingRequest(BaseModel):
    company: str = Field(min_length=2)
    role: str = Field(min_length=2)


class EmailConfigRequest(BaseModel):
    imap_host: str
    imap_port: int = 993
    email_address: str
    password: str = ""
    folder: str = "INBOX"
    use_ssl: bool = True


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="AIHawk Web", version="0.6.0")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

RESUME_PATH = Path("data_folder/plain_text_resume.yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_runtime():
    data_folder = Path("data_folder")
    if not data_folder.exists():
        raise HTTPException(status_code=400, detail="data_folder is missing")

    secrets_file = data_folder / "secrets.yaml"
    config_file = data_folder / "work_preferences.yaml"
    output_folder = data_folder / "output"

    for p in [secrets_file, config_file]:
        if not p.exists():
            raise HTTPException(status_code=400, detail=f"Missing required file: {p}")

    output_folder.mkdir(parents=True, exist_ok=True)
    RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(config_file, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    config["uploads"] = {"plainTextResume": RESUME_PATH}
    config["outputFileDirectory"] = output_folder
    config["secretsFile"] = secrets_file

    with open(secrets_file, "r", encoding="utf-8") as fh:
        secrets = yaml.safe_load(fh) or {}

    llm_api_key = ""
    for key in ["gemini_api_key", "openai_api_key", "claude_api_key",
                "huggingface_api_key", "perplexity_api_key", "llm_api_key"]:
        value = secrets.get(key)
        if value:
            llm_api_key = value
            break

    if not llm_api_key:
        logger.warning("No LLM API key found; ATS/briefing endpoints need one.")

    return config, secrets, llm_api_key


def _load_secrets() -> Dict[str, Any]:
    secrets_path = Path("data_folder/secrets.yaml")
    if not secrets_path.exists():
        return {}
    try:
        with open(secrets_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _save_secrets(secrets: Dict[str, Any]) -> None:
    secrets_path = Path("data_folder/secrets.yaml")
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    with open(secrets_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(secrets, fh, sort_keys=False)


def _resolve_email_config(cfg: Dict[str, Any], persist_password: bool = False) -> Dict[str, Any]:
    resolved = dict(cfg)

    email_address = (resolved.get("email_address") or "").strip()
    imap_host = (resolved.get("imap_host") or "").strip()
    password = (resolved.get("password") or "").strip()

    # Gmail defaults and common app-password formatting (spaces are often copied in)
    if email_address.lower().endswith(("@gmail.com", "@googlemail.com")):
        if not imap_host:
            imap_host = "imap.gmail.com"
        if not resolved.get("imap_port"):
            resolved["imap_port"] = 993
        resolved["use_ssl"] = True
        password = password.replace(" ", "")

    resolved["email_address"] = email_address
    resolved["imap_host"] = imap_host

    # When password is omitted/masked, recover from secrets.yaml
    if not password or password == "***":
        secrets = _load_secrets()
        password = (secrets.get("email_password") or "").strip()

    resolved["password"] = password

    if persist_password and password:
        secrets = _load_secrets()
        secrets["email_password"] = password
        _save_secrets(secrets)

    return resolved


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.6.0"}


@app.get("/api/stats")
def stats():
    summary = ApplicationStatsService(Path("job_applications")).summarize()
    return summary.as_dict()


# ---------------------------------------------------------------------------
# Resume management
# ---------------------------------------------------------------------------

@app.get("/api/resume")
def get_resume():
    if not RESUME_PATH.exists():
        raise HTTPException(status_code=404, detail="No resume uploaded yet.")
    return extract_summary(RESUME_PATH)


@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Accept resume in any format: PDF, DOCX, RTF, TXT, YAML.
    Converts to internal YAML and saves as plain_text_resume.yaml.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup = RESUME_PATH.with_suffix(".yaml.bak")
    if RESUME_PATH.exists():
        shutil.copy2(RESUME_PATH, backup)

    try:
        file_bytes = await file.read()
    finally:
        await file.close()

    try:
        resume_dict = save_resume(file_bytes, file.filename or "resume", RESUME_PATH)
    except Exception as exc:
        if backup.exists():
            shutil.copy2(backup, RESUME_PATH)
        raise HTTPException(status_code=422, detail=f"Could not parse resume: {exc}")

    summary = extract_summary(RESUME_PATH)
    return {
        "status": "ok",
        "source_format": ext.lstrip("."),
        "resume": summary,
    }


# ---------------------------------------------------------------------------
# Batch application run
# ---------------------------------------------------------------------------

@app.post("/api/run-batch")
def run_batch(payload: RunBatchRequest):
    config, secrets, llm_api_key = _load_runtime()

    if payload.positions:
        config["positions"] = payload.positions
    else:
        resume_positions = extract_positions(RESUME_PATH) if RESUME_PATH.exists() else []
        if resume_positions:
            config["positions"] = resume_positions

    if payload.locations:
        config["locations"] = payload.locations
    if payload.min_suitability_score is not None:
        config["min_suitability_score"] = payload.min_suitability_score
    config["dry_run"] = payload.dry_run

    positions_used = config.get("positions", [])
    manager = BotManager(secrets=secrets, config=config, llm_api_key=llm_api_key)

    if payload.platform == "all":
        li = manager.run_batch("linkedin", payload.count)
        in_ = manager.run_batch("indeed", payload.count)
        return {
            "platform": "all",
            "linkedin_applied": li, "indeed_applied": in_,
            "total_applied": li + in_,
            "positions_targeted": positions_used,
            "ats_scoring": "automatic — every job scored & resume tailored before applying",
        }

    applied = manager.run_batch(payload.platform, payload.count)
    return {
        "platform": payload.platform,
        "applied": applied,
        "positions_targeted": positions_used,
        "ats_scoring": "automatic — every job scored & resume tailored before applying",
    }


# ---------------------------------------------------------------------------
# ATS manual preview
# ---------------------------------------------------------------------------

@app.post("/api/ats-score")
def ats_score(payload: ATSRequest):
    config, _s, llm_api_key = _load_runtime()
    scorer = ATSScorer(AIAdapter(config, llm_api_key) if llm_api_key else None)
    return scorer.score_job(RESUME_PATH, payload.job_description)


# ---------------------------------------------------------------------------
# Recruiter briefing
# ---------------------------------------------------------------------------

@app.post("/api/recruiter-briefing")
def recruiter_briefing(payload: RecruiterBriefingRequest):
    config, _s, llm_api_key = _load_runtime()
    if not llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key missing in secrets.yaml")
    engine = RecruiterPrepEngine(AIAdapter(config, llm_api_key))
    briefing = engine.generate_briefing(payload.company, payload.role, str(RESUME_PATH))
    return briefing


# ---------------------------------------------------------------------------
# Tailored resumes
# ---------------------------------------------------------------------------

@app.get("/api/tailored-resumes")
def get_tailored_resumes():
    return {"resumes": list_tailored_resumes()}


@app.get("/api/tailored-resumes/{job_id}/pdf")
def download_tailored_pdf(job_id: str):
    tr = load_tailored_resume(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found for this job.")
    if tr.status == "discarded":
        raise HTTPException(status_code=410, detail="This resume was discarded (rejection received).")
    if not tr.pdf_path or not tr.pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not yet generated for this job.")
    return FileResponse(
        str(tr.pdf_path),
        media_type="application/pdf",
        filename=f"resume_{job_id}.pdf",
    )


@app.get("/api/tailored-resumes/{job_id}/highlights")
def download_highlights(job_id: str):
    tr = load_tailored_resume(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found for this job.")
    if not tr.highlights_path.exists():
        raise HTTPException(status_code=404, detail="Highlights file not found.")
    return FileResponse(
        str(tr.highlights_path),
        media_type="text/plain",
        filename=f"interview_highlights_{job_id}.txt",
    )


# ---------------------------------------------------------------------------
# Pipeline management (confirm / reject)
# ---------------------------------------------------------------------------

@app.post("/api/pipeline/{job_id}/confirm")
def confirm_pipeline(job_id: str):
    """User or email confirms the job is progressing. Deliver tailored resume."""
    tr = load_tailored_resume(job_id)
    tailor = ResumeTailor()
    if tr:
        result = tailor.confirm(tr)
        return {"status": "confirmed", "resume": result}
    # No tailored resume yet — just acknowledge
    return {"status": "confirmed", "resume": None}


@app.post("/api/pipeline/{job_id}/reject")
def reject_pipeline(job_id: str):
    """Rejection email received. Discard temp resume."""
    tr = load_tailored_resume(job_id)
    tailor = ResumeTailor()
    if tr:
        tailor.discard(tr)
    return {"status": "discarded", "job_id": job_id}


# ---------------------------------------------------------------------------
# Email monitoring
# ---------------------------------------------------------------------------

@app.get("/api/email/config")
def get_email_config():
    cfg = load_email_config()
    if not cfg:
        return {"configured": False}
    resolved = _resolve_email_config(cfg)
    return {
        "configured": True,
        "imap_host": resolved.get("imap_host"),
        "imap_port": resolved.get("imap_port", 993),
        "use_ssl": bool(resolved.get("use_ssl", True)),
        "email_address": resolved.get("email_address"),
    }


@app.post("/api/email/config")
def set_email_config(payload: EmailConfigRequest):
    cfg = _resolve_email_config(payload.model_dump(), persist_password=True)
    if not cfg.get("password"):
        raise HTTPException(
            status_code=400,
            detail="Missing email app password. For Gmail, generate a 16-character App Password.",
        )

    # Test connection before saving
    monitor = EmailMonitor.from_config(cfg)
    if not monitor.test_connection():
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not connect to IMAP server. For Gmail use imap.gmail.com:993 with SSL and a 16-character App Password."
            ),
        )

    save_email_config(cfg)
    return {
        "status": "saved",
        "imap_host": cfg["imap_host"],
        "email_address": cfg["email_address"],
    }


@app.get("/api/email/scan")
def scan_email(hours: int = 48):
    cfg = load_email_config()
    if not cfg:
        raise HTTPException(status_code=400, detail="Email not configured. POST /api/email/config first.")
    cfg = _resolve_email_config(cfg)
    if not cfg.get("password"):
        raise HTTPException(
            status_code=400,
            detail="Email password is not set. Save your IMAP config with an app password first.",
        )

    monitor = EmailMonitor.from_config(cfg)
    events = monitor.scan_since(hours=hours)
    classified = EmailMonitor.events_to_list(events)

    # -----------------------------------------------------------------------
    # Auto-update Pipeline Tracker based on classified emails
    # -----------------------------------------------------------------------
    tailored_resumes = list_tailored_resumes()
    auto_updated = []
    tailor = ResumeTailor()

    for event in classified:
        if event["classification"] == "unknown":
            continue

        company_hint = event.get("company_hint", "").lower()
        if not company_hint:
            continue

        # Try to find a matching pending job
        for tr in tailored_resumes:
            if tr.status != "pending":
                continue
            
            # Simple substring match for company
            if company_hint in tr.company.lower() or tr.company.lower() in company_hint:
                if event["classification"] == "rejection":
                    tailor.discard(tr)
                    auto_updated.append({"job_id": tr.job_id, "company": tr.company, "status": "discarded"})
                    event["auto_matched"] = tr.job_id
                elif event["classification"] == "pipeline":
                    tailor.confirm(tr)
                    auto_updated.append({"job_id": tr.job_id, "company": tr.company, "status": "confirmed"})
                    event["auto_matched"] = tr.job_id
                break

    rejections = [e for e in classified if e["classification"] == "rejection"]
    pipelines  = [e for e in classified if e["classification"] == "pipeline"]

    return {
        "scanned": len(classified),
        "rejections": rejections,
        "pipeline_updates": pipelines,
        "unknown": [e for e in classified if e["classification"] == "unknown"],
        "auto_updated_count": len(auto_updated),
        "auto_updated_jobs": auto_updated
    }
