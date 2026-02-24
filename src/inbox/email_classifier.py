import re
from typing import Tuple

from src.inbox.models import EmailCategory, EmailMessage


REJECTION_PATTERNS = [
    r"move forward with other candidates",
    r"we will not be moving forward",
    r"position has been filled",
    r"decided to pursue other applicants",
    r"regret to inform you",
    r"unfortunately",
    r"not selected",
]

INTERVIEW_PATTERNS = [
    r"interview",
    r"schedule a call",
    r"screening call",
    r"technical interview",
    r"availability",
    r"available for a call",
    r"next step",
]

RECRUITER_PATTERNS = [
    r"recruiter",
    r"talent acquisition",
    r"hiring team",
    r"would like to connect",
    r"came across your profile",
    r"opportunity",
    r"opening on our team",
]


def _contains_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def classify_email(message: EmailMessage) -> Tuple[EmailCategory, str]:
    combined_text = f"{message.subject}\n{message.body}"

    if _contains_pattern(combined_text, INTERVIEW_PATTERNS):
        return EmailCategory.INTERVIEW, "matched interview intent keywords"

    if _contains_pattern(combined_text, REJECTION_PATTERNS):
        return EmailCategory.REJECTION, "matched rejection intent keywords"

    if _contains_pattern(combined_text, RECRUITER_PATTERNS):
        return EmailCategory.RECRUITER, "matched recruiter outreach keywords"

    return EmailCategory.OTHER, "no high-confidence keyword matches"
