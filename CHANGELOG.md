# Changelog

## [0.2.1] - 2026-02-24

### Added
- New terminal action: `Summarize Job Application Results`
- New application results service in `src/application_stats.py` that reports:
  - total jobs
  - successes
  - failures
  - unknown statuses
- New tests in `tests/test_application_stats.py`

### Changed
- README updated with usage instructions for application summary command.

## [0.2.0] - 2026-02-24

### Added
- Inbox scanning feature from terminal UI to classify job-related emails into:
  - `interview`
  - `recruiter`
  - `rejection`
  - `other`
- New email scanning modules under `src/inbox/`:
  - `imap_scanner.py` for IMAP inbox fetching
  - `email_classifier.py` for keyword-based job email triage
  - `service.py` for orchestration and report generation
  - `models.py` for typed scan data models
- New CLI action in `main.py`: `Scan Inbox for Rejections/Recruiters/Interviews`
- JSON reports written to `data_folder/output/`:
  - `email_scan_report_latest.json`
  - timestamped `email_scan_report_YYYYMMDD_HHMMSS.json`
- New tests:
  - `tests/test_inbox_classifier.py`
  - `tests/test_inbox_service.py`

### Changed
- `main.py` now loads LLM API keys lazily so inbox scanning can run without requiring LLM credentials.
- `data_folder_example/secrets.yaml` now includes inbox credentials fields.
- `data_folder_example/work_preferences.yaml` includes optional inbox scanning settings.
- `requirements.txt` now explicitly includes `inquirer` and removes duplicate `pytest` entry.
- `src/libs/resume_and_cover_builder/__init__.py` version bumped to `0.2.0`.
