import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.inbox.email_classifier import classify_email
from src.inbox.imap_scanner import IMAPScanner
from src.inbox.models import EmailCategory, EmailMessage, ScanSummary
from src.logging import logger


class InboxScanService:
    def __init__(
        self,
        output_directory: Path,
        message_fetcher: Optional[Callable[[int], List[EmailMessage]]] = None,
    ):
        self.output_directory = Path(output_directory)
        self.message_fetcher = message_fetcher

    def run_scan(self, secrets: dict, lookback_hours: int = 168) -> ScanSummary:
        inbox_email = secrets.get("inbox_email", "").strip()
        inbox_password = secrets.get("inbox_app_password", "").strip()
        inbox_provider = secrets.get("inbox_provider", "gmail").strip()
        imap_host = secrets.get("imap_host", "").strip()
        imap_port = secrets.get("imap_port", 993)

        if not inbox_email or not inbox_password:
            raise ValueError(
                "Missing inbox credentials. Add 'inbox_email' and 'inbox_app_password' to data_folder/secrets.yaml"
            )

        fetcher = self.message_fetcher
        if fetcher is None:
            scanner = IMAPScanner(
                email_address=inbox_email,
                password=inbox_password,
                provider=inbox_provider,
                imap_host=imap_host,
                imap_port=imap_port,
            )
            fetcher = scanner.fetch_messages

        logger.info(f"Scanning inbox for the last {lookback_hours} hours")
        messages = fetcher(lookback_hours)

        categorized: Dict[EmailCategory, List[EmailMessage]] = defaultdict(list)
        for message in messages:
            category, _ = classify_email(message)
            categorized[category].append(message)

        for category in EmailCategory:
            categorized.setdefault(category, [])

        summary = ScanSummary.from_messages(
            source_email=inbox_email,
            lookback_hours=lookback_hours,
            categorized_messages=categorized,
            scanned_at=datetime.now(timezone.utc),
        )
        self._save_report(summary)
        return summary

    def _save_report(self, summary: ScanSummary):
        self.output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        report_data = {
            "scanned_at": summary.scanned_at,
            "source_email": summary.source_email,
            "lookback_hours": summary.lookback_hours,
            "total_messages": summary.total_messages,
            "rejection_messages": summary.rejection_messages,
            "recruiter_messages": summary.recruiter_messages,
            "interview_messages": summary.interview_messages,
            "other_messages": summary.other_messages,
            "categorized_messages": summary.categorized_messages,
        }

        dated_report = self.output_directory / f"email_scan_report_{timestamp}.json"
        latest_report = self.output_directory / "email_scan_report_latest.json"

        with open(dated_report, "w", encoding="utf-8") as report_file:
            json.dump(report_data, report_file, indent=2, ensure_ascii=False)

        with open(latest_report, "w", encoding="utf-8") as latest_file:
            json.dump(report_data, latest_file, indent=2, ensure_ascii=False)

        logger.info(f"Inbox scan report saved: {dated_report}")
