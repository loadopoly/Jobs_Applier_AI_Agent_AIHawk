from src.inbox.email_classifier import classify_email
from src.inbox.models import EmailCategory, EmailMessage


def test_classify_interview_message():
    message = EmailMessage(
        uid="1",
        subject="Interview invitation for Backend Engineer",
        sender="recruiter@example.com",
        received_at="2026-01-01T00:00:00Z",
        body="We would like to schedule a call next step in the process.",
    )

    category, reason = classify_email(message)

    assert category == EmailCategory.INTERVIEW
    assert "interview" in reason


def test_classify_rejection_message():
    message = EmailMessage(
        uid="2",
        subject="Update on your application",
        sender="careers@example.com",
        received_at="2026-01-01T00:00:00Z",
        body="We regret to inform you that we will not be moving forward with your candidacy.",
    )

    category, reason = classify_email(message)

    assert category == EmailCategory.REJECTION
    assert "rejection" in reason


def test_classify_recruiter_message():
    message = EmailMessage(
        uid="3",
        subject="Opportunity on our team",
        sender="talent@example.com",
        received_at="2026-01-01T00:00:00Z",
        body="I am a recruiter and came across your profile.",
    )

    category, reason = classify_email(message)

    assert category == EmailCategory.RECRUITER
    assert "recruiter" in reason


def test_classify_offer_message():
    message = EmailMessage(
        uid="4",
        subject="Your offer letter from Acme Corp",
        sender="hr@acme.com",
        received_at="2026-01-01T00:00:00Z",
        body="We are pleased to offer you the position of Software Engineer. Please find the offer letter attached.",
    )

    category, reason = classify_email(message)

    assert category == EmailCategory.OFFER
    assert "offer" in reason


def test_classify_offer_not_misclassified_as_interview():
    message = EmailMessage(
        uid="5",
        subject="Congratulations — Offer of Employment",
        sender="hr@bigco.com",
        received_at="2026-01-01T00:00:00Z",
        body="Congratulations! We are excited to offer you the role. Your start date will be discussed in your onboarding interview.",
    )

    category, reason = classify_email(message)

    assert category == EmailCategory.OFFER
    assert "offer" in reason
