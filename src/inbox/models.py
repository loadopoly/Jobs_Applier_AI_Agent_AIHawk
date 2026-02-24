from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class EmailCategory(str, Enum):
    REJECTION = "rejection"
    RECRUITER = "recruiter"
    INTERVIEW = "interview"
    OTHER = "other"


@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    received_at: str
    body: str


@dataclass
class ScanSummary:
    scanned_at: str
    source_email: str
    lookback_hours: int
    total_messages: int
    rejection_messages: int
    recruiter_messages: int
    interview_messages: int
    other_messages: int
    categorized_messages: Dict[str, List[Dict[str, str]]]

    @classmethod
    def from_messages(
        cls,
        source_email: str,
        lookback_hours: int,
        categorized_messages: Dict[EmailCategory, List[EmailMessage]],
        scanned_at: Optional[datetime] = None,
    ) -> "ScanSummary":
        scanned_at = scanned_at or datetime.now(timezone.utc)
        total_messages = sum(len(messages) for messages in categorized_messages.values())

        serializable = {
            category.value: [asdict(message) for message in messages]
            for category, messages in categorized_messages.items()
        }

        return cls(
            scanned_at=scanned_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_email=source_email,
            lookback_hours=lookback_hours,
            total_messages=total_messages,
            rejection_messages=len(categorized_messages.get(EmailCategory.REJECTION, [])),
            recruiter_messages=len(categorized_messages.get(EmailCategory.RECRUITER, [])),
            interview_messages=len(categorized_messages.get(EmailCategory.INTERVIEW, [])),
            other_messages=len(categorized_messages.get(EmailCategory.OTHER, [])),
            categorized_messages=serializable,
        )
