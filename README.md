
<div align="center">


# AIHawk: the first Jobs Applier AI Agent


AIHawk's core architecture remains **open source**, allowing developers to inspect and extend the codebase. However, due to copyright considerations, we have removed all third‑party provider plugins from this repository.

For a fully integrated experience, including managed provider connections: check out **[laboro.co](https://laboro.co/)** an AI‑driven job board where the agent **automatically applies to jobs** for you.


---


AIHawk has been featured by major media outlets for revolutionizing how job seekers interact with the job market:

[**Business Insider**](https://www.businessinsider.com/aihawk-applies-jobs-for-you-linkedin-risks-inaccuracies-mistakes-2024-11)
[**TechCrunch**](https://techcrunch.com/2024/10/10/a-reporter-used-ai-to-apply-to-2843-jobs/)
[**Semafor**](https://www.semafor.com/article/09/12/2024/linkedins-have-nots-and-have-bots)
[**Dev.by**](https://devby.io/news/ya-razoslal-rezume-na-2843-vakansii-po-17-v-chas-kak-ii-boty-vytesnyaut-ludei-iz-protsessa-naima.amp)
[**Wired**](https://www.wired.it/article/aihawk-come-automatizzare-ricerca-lavoro/)
[**The Verge**](https://www.theverge.com/2024/10/10/24266898/ai-is-enabling-job-seekers-to-think-like-spammers)
[**Vanity Fair**](https://www.vanityfair.it/article/intelligenza-artificiale-candidature-di-lavoro)
[**404 Media**](https://www.404media.co/i-applied-to-2-843-roles-the-rise-of-ai-powered-job-application-bots/)


---

## Terminal inbox scanning (v0.2.0)

JobHawk can now scan your inbox and classify job-response emails into:

- `interview`
- `recruiter`
- `rejection`
- `other`

### Setup

Add these fields to `data_folder/secrets.yaml`:

```yaml
inbox_email: 'YOUR_EMAIL@example.com'
inbox_provider: 'gmail'  # gmail | outlook | yahoo | imap
inbox_app_password: 'YOUR_APP_PASSWORD_HERE'
# Optional for custom IMAP provider:
# imap_host: 'imap.yourmailhost.com'
# imap_port: 993
```

### Run

```bash
python main.py
```

Choose:

`Scan Inbox for Rejections/Recruiters/Interviews`

### Output

Reports are generated in `data_folder/output/`:

- `email_scan_report_latest.json`
- `email_scan_report_YYYYMMDD_HHMMSS.json`

### Notes

- Use an app-specific password (recommended), not your normal mailbox password.
- Inbox scanning does not require an LLM API key.

---

## Terminal application result summary (v0.2.1)

JobHawk can summarize how many jobs were applied to and classify outcomes.

### Run

```bash
python main.py
```

Choose:

`Summarize Job Application Results`

### Output fields

- `total_jobs`: total saved application folders in `job_applications/`
- `successes`: status matched as applied/submitted/success/interview/offer
- `failures`: status matched as failed/error/rejected/declined/cancelled
- `unknown`: status missing or not recognized

This command reads `job_applications/*/job_application.json` and prints a JSON summary to terminal.

---

## Web dashboard (v0.5.0)

AIHawk now includes a browser-based dashboard you can run in Codespaces or externally.

### Start

```bash
/usr/bin/python3 -m pip install -r requirements.txt --user
/usr/bin/python3 run_web.py
```

Open:

- `http://localhost:8000` (local)
- In Codespaces: open forwarded port `8000` and use the generated public URL.

### Features

- Run application batches on LinkedIn, Indeed, or both.
- Use Dry Run mode for Codespaces/browserless environments.
- Run ATS job-match analysis from pasted job descriptions.
- Generate recruiter briefing cards.
- View application stats in one panel.

### ATS alignment tuning for operations backgrounds

The scorer now applies role alignment adjustments:

- Boosts jobs with supply chain / operations / logistics / procurement signals.
- Penalizes software-heavy roles (for example frontend/backend/full-stack engineering).
- Applies a hard mismatch cap for clearly out-of-scope technical roles.

This keeps auto-apply focused on higher-probability roles for Supply Chain Management and Operational Management profiles.

---

## Multi-format resumes, tailored apply, email inbox & pipeline tracker (v0.6.0)

### Resume upload — any format

The web dashboard now accepts resumes in any common format:

- **PDF** — text extracted via `pdfminer.six`
- **DOCX / DOC** — extracted via `python-docx`
- **RTF** — extracted via `striprtf`
- **TXT** — plain read with encoding detection
- **YAML / YML** — used directly (existing schema)

All formats are normalised to internal YAML on save. The bot reads positions and skills from the uploaded resume automatically — no hardcoded role lists.

### Tailored resume per job

For every job that clears the ATS threshold the system generates a **job-specific resume variant**:

1. The LLM rewrites bullet points to naturally incorporate missing keywords.
2. A `resume_tailored.pdf` is produced via `reportlab` (formatted, print-ready).
3. An `interview_highlights.txt` is created with 5-8 role-specific talking points.
4. All files live in `temp_resumes/<job_id>/`.

**Lifecycle:**

| Event | Action |
|---|---|
| Job batch applied | `pending` — temp resume created |
| Rejection email detected | `discarded` — PDF deleted, YAML kept |
| Pipeline confirmed (email or user click) | `confirmed` — PDF + highlights unlocked for download |

### Pipeline Tracker (dashboard)

The **Pipeline Tracker** table in the dashboard shows every job a tailored resume was generated for:

- **Confirm** — pipeline progressing; unlocks PDF + highlights download
- **Reject** — rejection; discards temp PDF
- **⬇ Resume PDF** — download the tailored PDF (confirmed only)
- **📝 Highlights** — download interview prep notes

### Email inbox monitoring

Connect your IMAP email box to auto-classify incoming messages:

1. Go to **Email Inbox Setup** in the dashboard.
2. Enter your IMAP host, port, and app password.
3. Click **Save & Test Connection**.
4. Use **Scan Inbox** to classify the last N hours of messages as:
   - `rejection` — recruiter passed
   - `pipeline` — next steps / interview / offer
   - `unknown` — unclassified

> **Gmail tip:** Use [App Passwords](https://myaccount.google.com/apppasswords) — not your main login.

### New API endpoints (v0.6.0)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/resume` | Resume summary (name, positions, skills) |
| `POST` | `/api/upload-resume` | Upload resume (any format) |
| `GET` | `/api/tailored-resumes` | List all tailored resumes |
| `GET` | `/api/tailored-resumes/{job_id}/pdf` | Download tailored PDF (confirmed only) |
| `GET` | `/api/tailored-resumes/{job_id}/highlights` | Download interview highlights |
| `POST` | `/api/pipeline/{job_id}/confirm` | Confirm pipeline → unlock delivery |
| `POST` | `/api/pipeline/{job_id}/reject` | Mark as rejected → discard PDF |
| `GET` | `/api/email/config` | Check email config status |
| `POST` | `/api/email/config` | Save &amp; test IMAP credentials |
| `GET` | `/api/email/scan?hours=N` | Scan inbox, classify messages |


