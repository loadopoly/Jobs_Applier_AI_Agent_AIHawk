import json
import os
from typing import List, Dict, Any
from pathlib import Path

from src.bots.linkedin_bot import LinkedInBot
from src.bots.indeed_bot import IndeedBot
from src.job_application import JobApplication
from src.job_application_saver import ApplicationSaver
from src.logging import logger
from src.application_stats import ApplicationStatsService
from src.libs.ats_scorer import ATSScorer
from src.libs.llm_manager import AIAdapter
from src.libs.resume_parser import extract_positions, extract_skills
from src.libs.resume_tailor import ResumeTailor


class BotManager:
    def __init__(self, secrets: Dict[str, str], config: Dict[str, Any], llm_api_key: str = ""):
        self.secrets = secrets
        self.config = config
        self.applications_dir = Path("job_applications")
        self.applications_dir.mkdir(exist_ok=True)
        self.ai_adapter = None
        selected_key = llm_api_key or secrets.get("llm_api_key", "")
        if selected_key:
            try:
                self.ai_adapter = AIAdapter(config, selected_key)
            except Exception as exc:
                logger.warning(f"LLM adapter unavailable, using heuristic ATS scoring: {exc}")
        self.scorer = ATSScorer(self.ai_adapter)
        self.tailor = ResumeTailor(self.ai_adapter)
        self.resume_path = config.get("uploads", {}).get("plainTextResume", Path("data_folder/plain_text_resume.yaml"))

    def run_batch(self, platform: str = "linkedin", count: int = 5):
        logger.info(f"Starting {platform} batch for {count} jobs")
        
        bot = None
        if platform.lower() == "linkedin":
            bot = LinkedInBot(self.secrets)
        elif platform.lower() == "indeed":
            bot = IndeedBot(self.secrets)
        else:
            logger.error(f"Unsupported platform: {platform}")
            return 0

        dry_run = bool(self.config.get("dry_run", False))
        if not dry_run:
            bot.login()
        else:
            logger.info("Dry-run enabled: skipping browser login and submitting simulated applications.")
        
        # Derive search positions from the user's resume.
        # config["positions"] (passed from the UI or CLI) takes precedence;
        # if absent, fall back to titles extracted from the uploaded resume.
        resume_positions = extract_positions(self.resume_path)
        default_positions = resume_positions if resume_positions else [
            "Supply Chain Manager",
            "Operations Manager",
            "Logistics Manager",
            "Procurement Manager",
        ]
        positions = self.config.get("positions") or default_positions
        if not positions:
            positions = default_positions
        locations = self.config.get("locations") or ["United States"]
        
        applied_count = 0
        for position in positions:
            if applied_count >= count:
                break
            for location in locations:
                if applied_count >= count:
                    break
                
                logger.info(f"Searching for '{position}' in '{location}'")
                jobs = bot.search_jobs(position, location)
                
                for job in jobs:
                    if applied_count >= count:
                        break
                    
                    try:
                        # ATS Scoring
                        logger.info(f"Scoring job: {job.role} at {job.company}")
                        analysis = self.scorer.score_job(self.resume_path, job.description or f"{job.role} at {job.company}")
                        score = analysis.get("score", 0)
                        
                        from config import JOB_SUITABILITY_SCORE
                        min_score = self.config.get("min_suitability_score", JOB_SUITABILITY_SCORE * 10)
                        if score < min_score:
                            logger.warning(f"Skipping job at {job.company} due to low score ({score}/100)")
                            continue
                        
                        logger.info(f"Job score {score}/100 exceeds threshold {min_score}. Applying...")

                        # ── Generate tailored resume for this specific job ──
                        tailored = None
                        try:
                            logger.info(f"Tailoring resume for {job.role} at {job.company}")
                            tailored = self.tailor.tailor(
                                base_resume_path=self.resume_path,
                                job_description=job.description or f"{job.role} at {job.company}",
                                ats_analysis=analysis,
                                job_id=f"{job.company}_{job.role}".replace(" ", "_").lower(),
                                job_title=job.role,
                                company=job.company,
                            )
                        except Exception as te:
                            logger.warning(f"Resume tailoring skipped: {te}")

                        if dry_run:
                            application = JobApplication(
                                job=job,
                                status="applied_dry_run",
                                platform=platform,
                            )
                        else:
                            application = bot.apply(job)

                        application.application_data = analysis
                        if tailored:
                            application.tailored_resume_path = str(tailored.pdf_path or tailored.tailored_yaml_path)
                            application.tailored_resume_status = tailored.status
                            self.tailor._save_metadata(tailored)

                        ApplicationSaver.save(application)
                        applied_count += 1
                        logger.info(f"Successfully applied to {job.role} at {job.company} | tailored_resume={'yes' if tailored else 'no'}")
                    except Exception as e:
                        logger.error(f"Failed to apply to {job.company}: {e}")
        
        logger.info(f"Finished {platform} batch. Applied to {applied_count} jobs.")
        return applied_count

    def run_linkedin_batch(self, count: int = 5):
        # Legacy method for backward compatibility
        return self.run_batch("linkedin", count)
