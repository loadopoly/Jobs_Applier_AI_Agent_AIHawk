import email
import imaplib
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr
from typing import List

from src.inbox.models import EmailMessage


DEFAULT_IMAP_HOSTS = {
    "gmail": "imap.gmail.com",
    "outlook": "outlook.office365.com",
    "yahoo": "imap.mail.yahoo.com",
}


class IMAPScanError(RuntimeError):
    pass


class IMAPScanner:
    def __init__(self, email_address: str, password: str, provider: str = "gmail", imap_host: str = "", imap_port: int = 993):
        self.email_address = email_address
        self.password = password
        self.provider = (provider or "gmail").lower().strip()
        self.imap_host = imap_host or DEFAULT_IMAP_HOSTS.get(self.provider)
        self.imap_port = int(imap_port or 993)

        if not self.imap_host:
            raise IMAPScanError(
                "Unable to determine IMAP host. Set 'inbox_provider' to gmail/outlook/yahoo or provide 'imap_host'."
            )

    def fetch_messages(self, lookback_hours: int) -> List[EmailMessage]:
        since_date = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%d-%b-%Y")

        try:
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port) as client:
                client.login(self.email_address, self.password)
                status, _ = client.select("INBOX")
                if status != "OK":
                    raise IMAPScanError("Unable to select INBOX")

                status, data = client.search(None, f'(SINCE "{since_date}")')
                if status != "OK":
                    raise IMAPScanError("Unable to search inbox messages")

                message_ids = data[0].split()
                messages: List[EmailMessage] = []

                for message_id in message_ids:
                    status, message_data = client.fetch(message_id, "(RFC822 INTERNALDATE)")
                    if status != "OK":
                        continue

                    raw_bytes = message_data[0][1]
                    msg = email.message_from_bytes(raw_bytes)
                    body = self._extract_body(msg)

                    subject = self._decode_header_value(msg.get("Subject", ""))
                    sender = parseaddr(msg.get("From", ""))[1] or msg.get("From", "")
                    received_at = self._extract_internal_date(message_data)

                    messages.append(
                        EmailMessage(
                            uid=message_id.decode("utf-8", errors="ignore"),
                            subject=subject,
                            sender=sender,
                            received_at=received_at,
                            body=body,
                        )
                    )

                return messages
        except imaplib.IMAP4.error as exc:
            raise IMAPScanError(f"IMAP login/search failed: {exc}") from exc

    @staticmethod
    def _decode_header_value(value: str) -> str:
        chunks = decode_header(value)
        decoded_parts = []
        for raw_part, encoding in chunks:
            if isinstance(raw_part, bytes):
                decoded_parts.append(raw_part.decode(encoding or "utf-8", errors="replace"))
            else:
                decoded_parts.append(raw_part)
        return "".join(decoded_parts)

    @staticmethod
    def _extract_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
            return ""

        payload = msg.get_payload(decode=True)
        if not payload:
            return ""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    @staticmethod
    def _extract_internal_date(message_data) -> str:
        for segment in message_data:
            if not isinstance(segment, tuple):
                continue
            metadata = segment[0]
            if not metadata:
                continue
            metadata_text = metadata.decode("utf-8", errors="ignore") if isinstance(metadata, bytes) else str(metadata)
            marker = 'INTERNALDATE "'
            if marker in metadata_text:
                start = metadata_text.find(marker) + len(marker)
                end = metadata_text.find('"', start)
                if end > start:
                    return metadata_text[start:end]
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
