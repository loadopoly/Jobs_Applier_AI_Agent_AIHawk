from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from src.job import Job


@dataclass
class JobApplication:
    job: Job
    id: str = ""
    status: str = "pending"  # applied, applied_dry_run, failed, skipped, rejected, pipeline_confirmed
    platform: str = "linkedin"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    resume_path: str = ""
    cover_letter_path: str = ""
    tailored_resume_path: str = ""   # path to temp_resumes/<job_id>/resume_tailored.pdf
    tailored_resume_status: str = "" # pending | discarded | confirmed
    application_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            # Generate a simple ID based on company and role if not provided
            self.id = f"{self.job.company}_{self.job.role}".replace(" ", "_").lower()
