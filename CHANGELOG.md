# Changelog

## [0.9.0] - 2026-04-15

### Added
- **Always-active agent scheduler** — the web server now ships with an
  `AgentScheduler` background thread that fires job-application batches
  automatically on a configurable interval (default 4 hours) without any
  manual interaction.
  - Enable via `agent_enabled: true` in `data_folder/work_preferences.yaml`
    (persists across restarts) or via `POST /api/agent/config` at runtime.
  - Scheduler settings: `agent_interval_hours`, `agent_batch_count`,
    `agent_platform` (`linkedin` | `indeed` | `all`).
  - After each batch the scheduler also triggers an email inbox scan to
    auto-confirm / auto-discard jobs in the pipeline tracker.
- **GitHub Actions cron workflow** (`.github/workflows/agent.yml`) — runs the
  agent on a cloud runner every 4 hours via `schedule: cron: '0 */4 * * *'`.
  Supports `workflow_dispatch` for on-demand runs with custom `platform`,
  `count`, and `dry_run` inputs.  Reads credentials from repository secrets
  (`SECRETS_YAML`, `WORK_PREFS_YAML`, `RESUME_YAML`).
- New API endpoints:
  - `GET /api/agent/status` — scheduler state (enabled, interval, last/next run)
  - `POST /api/agent/config` — reconfigure scheduler at runtime
- Updated `data_folder_example/work_preferences.yaml` with the four new
  `agent_*` keys (all commented/off by default).
- FastAPI app now uses the modern `lifespan` context manager instead of the
  deprecated `@app.on_event("startup")` pattern.

## [0.8.0] - 2026-03-03

### Fixed
- **MockCorp / BotWorks stub jobs** — `linkedin_bot.search_jobs()` and `indeed_bot.search_jobs()`
  were hardcoded to return fake companies regardless of the selected Mode (Live Apply / Dry Run).
  Both methods now perform real Selenium scraping: LinkedIn uses `/jobs/search` with Easy Apply +
  last-24h filters; Indeed uses `/jobs` sorted by date. `apply()` methods likewise replaced with
  real Easy Apply / Indeed Apply flows.
- **Browser initialization crash** (`session not created: Chrome instance exited`) — `chrome_utils`
  now auto-enables `--headless=new` when no `DISPLAY` environment variable is present (Codespaces,
  remote servers). Headed mode is still used when a display is available.
- **"Business Efficiency Analyst" dropped from Target Positions** — `_extract_positions_from_text()`
  was matching garbage metric lines (e.g. *"Leading To A 16% Reduction…"*) because `lead` matched
  as a substring inside "leading". Fixed by:
  - Whole-word regex matching for all title hints
  - Skipping lines that end with punctuation (`.`, `,`, `;`, `:`)
  - Skipping lines that contain digits
  - Raising the position cap from 6 → 8

### Added
- `tests/test_bots.py` — unit tests for `LinkedInBot`, `IndeedBot`, and Chrome headless detection
  (13 tests, all passing without a real browser using mocked Selenium driver)
- `tests/test_resume_parser_positions.py` — regression and unit tests for `_extract_positions_from_text()`
  (7 tests covering filtering, cap, and the Business Efficiency Analyst regression)

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
