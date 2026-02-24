
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

