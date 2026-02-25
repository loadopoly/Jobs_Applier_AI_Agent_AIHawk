
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

## Multi-format resumes, background batching, live logs & auto-pipeline (v0.7.0)

### Real-time Batch Tracking

You no longer have to wait for a batch to finish to see results. The **Start Batch** process now runs in the background:
- **Live Logs**: Watch the bot's activity (searching, scoring, applying) in real-time in the Output panel.
- **Auto-Scrolling**: The log view stays synced with the newest activity.
- **Background Execution**: You can browse the Pipeline Tracker or scan your inbox while a batch is still running.

### Auto-Pipeline Management

Email scanning is now integrated with your **Pipeline Tracker**:
- When you run **🔍 Scan Inbox**, the system matches recruiter emails to your pending job applications.
- **Auto-Confirm**: If an interview or "next step" is detected, the job status moves to `confirmed` automatically.
- **Auto-Discard**: If a rejection is detected, the temporary resume is marked as `discarded`.
- The dashboard notifies you how many job statuses were automatically updated after each scan.

### Resume upload — any format

The web dashboard accepts resumes in any common format:

- **PDF, DOCX, DOC, RTF, TXT, YAML**

All formats are normalised to internal YAML on save. The bot reads positions and skills from the uploaded resume automatically.

### Tailored resume per job

For every job that clears the ATS threshold the system generates a **job-specific resume variant**:

1. The LLM rewrites bullet points to naturally incorporate missing keywords.
2. A `resume_tailored.pdf` is produced via `reportlab`.
3. An `interview_highlights.txt` is created with role-specific talking points.

### Email inbox monitoring

Connect your IMAP email box to auto-classify incoming messages. Use [App Passwords](https://myaccount.google.com/apppasswords) for Gmail.

### New API endpoints (v0.7.0)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/batch-status` | Get live activity logs and running state |
| `GET` | `/api/tailored-resumes` | List all tailored resumes |
| `GET` | `/api/tailored-resumes/{job_id}/pdf` | Download tailored PDF (confirmed only) |
| `POST` | `/api/email/scan?hours=N` | Scan inbox & **auto-update pipeline stats** |
| `GET` | `/api/email/config` | Check email config status |


