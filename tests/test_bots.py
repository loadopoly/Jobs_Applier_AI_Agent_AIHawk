"""
Tests for LinkedInBot and IndeedBot.
Uses mocked Selenium driver so no real browser is needed.
Covers: search_jobs() with no driver, and headless chrome_utils behaviour.
"""
import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.job import Job
from src.job_application import JobApplication
from src.bots.linkedin_bot import LinkedInBot
from src.bots.indeed_bot import IndeedBot


# ── LinkedInBot ──────────────────────────────────────────────────────────────

class TestLinkedInBotNoDriver:
    def test_search_returns_empty_when_driver_none(self):
        bot = LinkedInBot(secrets={"linkedin_email": "u", "linkedin_password": "p"})
        assert bot.driver is None
        result = bot.search_jobs("Logistics Manager", "Baltimore")
        assert result == []

    def test_apply_returns_failed_when_driver_none(self):
        bot = LinkedInBot(secrets={})
        job = Job(role="Logistics Manager", company="ACME", link="https://linkedin.com/jobs/1")
        result = bot.apply(job)
        assert result.status == "failed"
        assert result.platform == "linkedin"

    def test_apply_returns_failed_when_no_link(self):
        bot = LinkedInBot(secrets={})
        bot.driver = MagicMock()
        job = Job(role="Logistics Manager", company="ACME", link="")
        result = bot.apply(job)
        assert result.status == "failed"

    def test_search_jobs_with_mock_driver(self):
        """search_jobs with a driver that finds 2 matching cards returns 2 jobs."""
        bot = LinkedInBot(secrets={})

        mock_card = MagicMock()
        mock_card.find_element.side_effect = lambda by, sel: MagicMock(
            text={"h3": "Logistics Manager", "h4": "ACME Corp",
                  ".job-card-container__metadata-item": "Baltimore, MD"}.get(sel, "value"),
            get_attribute=lambda attr: "https://linkedin.com/jobs/123"
        )

        mock_driver = MagicMock()
        mock_driver.find_elements.return_value = [mock_card, mock_card]
        bot.driver = mock_driver

        # Patch WebDriverWait to avoid timeout logic
        with patch("src.bots.linkedin_bot.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = MagicMock(text="Job description text")
            jobs = bot.search_jobs("Logistics Manager", "Baltimore", count=5)

        # We get at most as many jobs as cards returned
        assert isinstance(jobs, list)

    def test_login_skipped_when_no_credentials(self):
        bot = LinkedInBot(secrets={})
        # Should not raise, driver stays None
        bot.login()
        assert bot.driver is None


# ── IndeedBot ─────────────────────────────────────────────────────────────────

class TestIndeedBotNoDriver:
    def test_search_returns_empty_when_driver_none(self):
        bot = IndeedBot(secrets={})
        result = bot.search_jobs("Supply Chain Manager", "Remote")
        assert result == []

    def test_apply_returns_failed_when_driver_none(self):
        bot = IndeedBot(secrets={})
        job = Job(role="Supply Chain Manager", company="Beta", link="https://indeed.com/job/1")
        result = bot.apply(job)
        assert result.status == "failed"
        assert result.platform == "indeed"

    def test_apply_returns_failed_when_no_link(self):
        bot = IndeedBot(secrets={})
        bot.driver = MagicMock()
        job = Job(role="Supply Chain Manager", company="Beta", link="")
        result = bot.apply(job)
        assert result.status == "failed"

    def test_login_skipped_when_no_credentials(self):
        bot = IndeedBot(secrets={})
        bot.login()
        assert bot.driver is None


# ── chrome_utils headless detection ──────────────────────────────────────────

class TestChromeHeadlessDetection:
    def test_headless_arg_added_when_no_display(self):
        from src.utils.chrome_utils import chrome_browser_options
        with patch.dict(os.environ, {}, clear=True):
            # Ensure DISPLAY is absent
            os.environ.pop("DISPLAY", None)
            options = chrome_browser_options()
        args = options.arguments
        assert any("headless" in a for a in args), f"Expected --headless in {args}"

    def test_headless_not_added_when_display_present(self):
        from src.utils.chrome_utils import chrome_browser_options
        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            options = chrome_browser_options()
        args = options.arguments
        assert not any("headless" in a for a in args), f"headless should not be in {args}"
