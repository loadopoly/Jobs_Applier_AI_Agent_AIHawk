import json

from src.inbox.models import EmailCategory, EmailMessage
from src.inbox.service import InboxScanService


def test_inbox_scan_service_writes_latest_report(tmp_path):
    messages = [
        EmailMessage(
            uid="10",
            subject="Interview request",
            sender="recruiting@company.com",
            received_at="2026-01-01T00:00:00Z",
            body="Please share your availability for an interview.",
        ),
        EmailMessage(
            uid="11",
            subject="Application update",
            sender="jobs@company.com",
            received_at="2026-01-01T00:00:00Z",
            body="We decided to move forward with other candidates.",
        ),
    ]

    def fake_fetcher(_lookback_hours):
        return messages

    service = InboxScanService(output_directory=tmp_path, message_fetcher=fake_fetcher)
    secrets = {
        "inbox_email": "user@example.com",
        "inbox_app_password": "app-pass",
        "inbox_provider": "gmail",
    }

    summary = service.run_scan(secrets=secrets, lookback_hours=24)

    assert summary.total_messages == 2
    assert summary.interview_messages == 1
    assert summary.rejection_messages == 1

    latest_report = tmp_path / "email_scan_report_latest.json"
    assert latest_report.exists()

    report = json.loads(latest_report.read_text(encoding="utf-8"))
    assert report["source_email"] == "user@example.com"
    assert len(report["categorized_messages"][EmailCategory.INTERVIEW.value]) == 1


def test_inbox_scan_service_requires_credentials(tmp_path):
    service = InboxScanService(output_directory=tmp_path, message_fetcher=lambda _: [])

    try:
        service.run_scan(secrets={}, lookback_hours=24)
        assert False, "Expected ValueError for missing credentials"
    except ValueError as exc:
        assert "Missing inbox credentials" in str(exc)
