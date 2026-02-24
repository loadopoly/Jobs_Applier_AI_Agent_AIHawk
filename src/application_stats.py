import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from src.logging import logger


SUCCESS_KEYWORDS = {"applied", "submitted", "success", "succeeded", "interview", "offer"}
FAILURE_KEYWORDS = {"failed", "error", "rejected", "declined", "cancelled"}


@dataclass
class ApplicationStats:
    total_jobs: int
    successes: int
    failures: int
    unknown: int

    def as_dict(self) -> Dict[str, int]:
        return {
            "total_jobs": self.total_jobs,
            "successes": self.successes,
            "failures": self.failures,
            "unknown": self.unknown,
        }


class ApplicationStatsService:
    def __init__(self, applications_dir: Path):
        self.applications_dir = Path(applications_dir)

    def summarize(self) -> ApplicationStats:
        if not self.applications_dir.exists() or not self.applications_dir.is_dir():
            return ApplicationStats(total_jobs=0, successes=0, failures=0, unknown=0)

        job_dirs = [
            path
            for path in self.applications_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]

        successes = 0
        failures = 0
        unknown = 0

        for job_dir in job_dirs:
            status = self._extract_status(job_dir)
            state = self._classify_status(status)
            if state == "success":
                successes += 1
            elif state == "failure":
                failures += 1
            else:
                unknown += 1

        return ApplicationStats(
            total_jobs=len(job_dirs),
            successes=successes,
            failures=failures,
            unknown=unknown,
        )

    def _extract_status(self, job_dir: Path) -> str:
        application_file = job_dir / "job_application.json"
        if not application_file.exists():
            return ""

        try:
            data = json.loads(application_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Unable to parse {application_file}: {exc}")
            return ""

        if isinstance(data, dict):
            status = data.get("status") or data.get("application_status") or ""
            return str(status).strip().lower()
        return ""

    @staticmethod
    def _classify_status(status: str) -> str:
        if not status:
            return "unknown"

        lowered = status.lower().strip()
        if any(keyword in lowered for keyword in FAILURE_KEYWORDS):
            return "failure"
        if any(keyword in lowered for keyword in SUCCESS_KEYWORDS):
            return "success"
        return "unknown"
