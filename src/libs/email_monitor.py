"""
email_monitor.py
================
IMAP-based email watcher that classifies incoming messages as:

  rejection    → recruiter passed
  pipeline     → next steps scheduled / offer / interview requested
  unknown      → everything else

The monitor is intentionally lightweight — no dependencies beyond stdlib.
It does NOT auto-reply or delete any email.

Usage (manual poll)
-------------------
    monitor = EmailMonitor.from_config(email_cfg)
    events  = monitor.scan_since(hours=24)
    # events is a list of EmailEvent
"""

from __future__ import annotations

import email
import imaplib
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header as _decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.logging import logger


# ---------------------------------------------------------------------------
# Signal word lists
# ---------------------------------------------------------------------------

REJECTION_SIGNALS = [
    "not moving forward",
    "not selected",
    "decided to move forward with other",
    "we have decided not to proceed",
    "your application was not successful",
    "we regret",
    "unfortunately",
    "position has been filled",
    "we will not be moving forward",
    "not a fit",
    "no longer considering",
    "rejected",
    "decline",
    "not a match",
]

PIPELINE_SIGNALS = [
    "interview",
    "next step",
    "schedule a call",
    "offer",
    "move forward",
    "would like to connect",
    "moving you",
    "shortlisted",
    "congratulations",
    "pleased to inform",
    "excited to offer",
    "background check",
    "reference check",
    "start date",
    "onboarding",
    "welcome to the team",
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EmailEvent:
    uid: str
    subject: str
    sender: str
    date: str
    snippet: str
    classification: str   # rejection | pipeline | unknown
    company_hint: str = ""


@dataclass
class EmailConfig:
    imap_host: str
    imap_port: int
    email_address: str
    password: str
    folder: str = "INBOX"
    use_ssl: bool = True

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EmailConfig":
        return cls(
            imap_host=d.get("imap_host", ""),
            imap_port=int(d.get("imap_port", 993)),
            email_address=d.get("email_address", ""),
            password=d.get("password", ""),
            folder=d.get("folder", "INBOX"),
            use_ssl=bool(d.get("use_ssl", True)),
        )


# ---------------------------------------------------------------------------
# Core monitor
# ---------------------------------------------------------------------------

class EmailMonitor:
    def __init__(self, config: EmailConfig):
        self.config = config

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "EmailMonitor":
        return cls(EmailConfig.from_dict(cfg))

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        cfg = self.config
        if cfg.use_ssl:
            conn = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        else:
            conn = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
        conn.login(cfg.email_address, cfg.password)
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Return True if login succeeds."""
        try:
            conn = self._connect()
            conn.logout()
            return True
        except Exception as exc:
            logger.warning(f"Email connection test failed: {exc}")
            return False

    def scan_since(self, hours: int = 48) -> List[EmailEvent]:
        """Return classified EmailEvent list for messages in the last *hours*."""
        events: List[EmailEvent] = []
        try:
            conn = self._connect()
            conn.select(self.config.folder)

            since_dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
            since_str = since_dt.strftime("%d-%b-%Y")
            _, uids_bytes = conn.uid("search", None, f'SINCE "{since_str}"')
            uids = uids_bytes[0].split() if uids_bytes and uids_bytes[0] else []

            for uid in uids:
                try:
                    _, msg_data = conn.uid("fetch", uid, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    event = self._parse_message(uid.decode(), msg)
                    if event:
                        events.append(event)
                except Exception:
                    pass

            conn.logout()
        except Exception as exc:
            logger.error(f"Email scan failed: {exc}\n{traceback.format_exc()}")

        return events

    def scan_for_company(self, company: str, hours: int = 168) -> List[EmailEvent]:
        """Return events where sender or subject mentions *company*."""
        all_events = self.scan_since(hours=hours)
        company_lower = company.lower()
        return [
            e for e in all_events
            if company_lower in e.sender.lower()
            or company_lower in e.subject.lower()
            or company_lower in e.snippet.lower()
        ]

    # ------------------------------------------------------------------
    # Parsing & classification
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_str(value: Optional[str]) -> str:
        if not value:
            return ""
        parts = _decode_header(value)
        decoded_parts: List[str] = []
        for part_bytes, charset in parts:
            if isinstance(part_bytes, bytes):
                decoded_parts.append(
                    part_bytes.decode(charset or "utf-8", errors="replace")
                )
            else:
                decoded_parts.append(part_bytes)
        return " ".join(decoded_parts)

    @staticmethod
    def _body_snippet(msg: email.message.Message, max_len: int = 400) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        body = payload.decode(
                            part.get_content_charset("utf-8"), errors="replace"
                        )
                        break
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                body = payload.decode(
                    msg.get_content_charset("utf-8"), errors="replace"
                )
            except Exception:
                pass
        return body[:max_len]

    def _parse_message(self, uid: str, msg: email.message.Message) -> Optional[EmailEvent]:
        subject = self._decode_str(msg.get("Subject", ""))
        sender = self._decode_str(msg.get("From", ""))
        snippet = self._body_snippet(msg)
        combined = (subject + " " + snippet).lower()

        classification = self._classify(combined)

        # Best-effort company hint from sender domain
        company_hint = ""
        domain_match = re.search(r"@([\w.-]+)", sender)
        if domain_match:
            domain = domain_match.group(1)
            # Strip common providers
            if not any(p in domain for p in ("gmail", "yahoo", "outlook", "hotmail")):
                company_hint = domain.split(".")[0].title()

        return EmailEvent(
            uid=uid,
            subject=subject,
            sender=sender,
            date=str(msg.get("Date", "")),
            snippet=snippet[:200],
            classification=classification,
            company_hint=company_hint,
        )

    @staticmethod
    def _classify(text: str) -> str:
        rej_hits = sum(1 for s in REJECTION_SIGNALS if s in text)
        pip_hits = sum(1 for s in PIPELINE_SIGNALS if s in text)
        if rej_hits > pip_hits and rej_hits > 0:
            return "rejection"
        if pip_hits > 0:
            return "pipeline"
        return "unknown"

    # ------------------------------------------------------------------
    # Serialisation helpers (for API layer)
    # ------------------------------------------------------------------

    @staticmethod
    def events_to_list(events: List[EmailEvent]) -> List[Dict[str, Any]]:
        return [
            {
                "uid": e.uid,
                "subject": e.subject,
                "sender": e.sender,
                "date": e.date,
                "snippet": e.snippet,
                "classification": e.classification,
                "company_hint": e.company_hint,
            }
            for e in events
        ]


# ---------------------------------------------------------------------------
# Email config persistence (saved alongside secrets.yaml)
# ---------------------------------------------------------------------------

EMAIL_CONFIG_PATH = Path("data_folder/email_config.yaml")


def save_email_config(cfg: Dict[str, Any]) -> None:
    EMAIL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Never store raw password in YAML in a shared repo — store a masked version
    safe = {k: ("***" if "password" in k else v) for k, v in cfg.items()}
    with open(EMAIL_CONFIG_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(safe, fh)


def load_email_config() -> Optional[Dict[str, Any]]:
    if not EMAIL_CONFIG_PATH.exists():
        return None
    try:
        with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or None
    except Exception:
        return None
