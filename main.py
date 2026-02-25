import base64
import sys
from pathlib import Path
import traceback
from typing import List, Optional, Tuple, Dict

import click
import inquirer
import yaml
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import re
import json
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.inbox.service import InboxScanService
from src.application_stats import ApplicationStatsService
from src.bots.bot_manager import BotManager
from src.resume_schemas.job_application_profile import JobApplicationProfile
from src.resume_schemas.resume import Resume
from src.logging import logger
from src.utils.chrome_utils import init_browser
from src.utils.constants import (
    PLAIN_TEXT_RESUME_YAML,
    SECRETS_YAML,
    WORK_PREFERENCES_YAML,
)
# from ai_hawk.bot_facade import AIHawkBotFacade
# from ai_hawk.job_manager import AIHawkJobManager
# from ai_hawk.llm.llm_manager import GPTAnswerer


class ConfigError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class ConfigValidator:
    """Validates configuration and secrets YAML files."""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    REQUIRED_CONFIG_KEYS = {
        "remote": bool,
        "experience_level": dict,
        "job_types": dict,
        "date": dict,
        "positions": list,
        "locations": list,
        "location_blacklist": list,
        "distance": int,
        "company_blacklist": list,
        "title_blacklist": list,
    }
    EXPERIENCE_LEVELS = [
        "internship",
        "entry",
        "associate",
        "mid_senior_level",
        "director",
        "executive",
    ]
    JOB_TYPES = [
        "full_time",
        "contract",
        "part_time",
        "temporary",
        "internship",
        "other",
        "volunteer",
    ]
    DATE_FILTERS = ["all_time", "month", "week", "24_hours"]
    APPROVED_DISTANCES = {0, 5, 10, 25, 50, 100}

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate the format of an email address."""
        return bool(ConfigValidator.EMAIL_REGEX.match(email))

    @staticmethod
    def load_yaml(yaml_path: Path) -> dict:
        """Load and parse a YAML file."""
        try:
            with open(yaml_path, "r") as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading YAML file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"YAML file not found: {yaml_path}")

    @classmethod
    def validate_config(cls, config_yaml_path: Path) -> dict:
        """Validate the main configuration YAML file."""
        parameters = cls.load_yaml(config_yaml_path)
        # Check for required keys and their types
        for key, expected_type in cls.REQUIRED_CONFIG_KEYS.items():
            if key not in parameters:
                if key in ["company_blacklist", "title_blacklist", "location_blacklist"]:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Missing required key '{key}' in {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ["company_blacklist", "title_blacklist", "location_blacklist"] and parameters[key] is None:
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Invalid type for key '{key}' in {config_yaml_path}. Expected {expected_type.__name__}."
                    )
        cls._validate_experience_levels(parameters["experience_level"], config_yaml_path)
        cls._validate_job_types(parameters["job_types"], config_yaml_path)
        cls._validate_date_filters(parameters["date"], config_yaml_path)
        cls._validate_list_of_strings(parameters, ["positions", "locations"], config_yaml_path)
        cls._validate_distance(parameters["distance"], config_yaml_path)
        cls._validate_blacklists(parameters, config_yaml_path)
        return parameters

    @classmethod
    def _validate_experience_levels(cls, experience_levels: dict, config_path: Path):
        """Ensure experience levels are booleans."""
        for level in cls.EXPERIENCE_LEVELS:
            if not isinstance(experience_levels.get(level), bool):
                raise ConfigError(
                    f"Experience level '{level}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_job_types(cls, job_types: dict, config_path: Path):
        """Ensure job types are booleans."""
        for job_type in cls.JOB_TYPES:
            if not isinstance(job_types.get(job_type), bool):
                raise ConfigError(
                    f"Job type '{job_type}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_date_filters(cls, date_filters: dict, config_path: Path):
        """Ensure date filters are booleans."""
        for date_filter in cls.DATE_FILTERS:
            if not isinstance(date_filters.get(date_filter), bool):
                raise ConfigError(
                    f"Date filter '{date_filter}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_list_of_strings(cls, parameters: dict, keys: list, config_path: Path):
        """Ensure specified keys are lists of strings."""
        for key in keys:
            if not all(isinstance(item, str) for item in parameters[key]):
                raise ConfigError(
                    f"'{key}' must be a list of strings in {config_path}"
                )

    @classmethod
    def _validate_distance(cls, distance: int, config_path: Path):
        """Validate the distance value."""
        if distance not in cls.APPROVED_DISTANCES:
            raise ConfigError(
                f"Invalid distance value '{distance}' in {config_path}. Must be one of: {cls.APPROVED_DISTANCES}"
            )

    @classmethod
    def _validate_blacklists(cls, parameters: dict, config_path: Path):
        """Ensure blacklists are lists."""
        for blacklist in ["company_blacklist", "title_blacklist", "location_blacklist"]:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(
                    f"'{blacklist}' must be a list in {config_path}"
                )
            if parameters[blacklist] is None:
                parameters[blacklist] = []

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> str:
        """Validate the secrets YAML file and retrieve the LLM API key.

        Supports a generic 'llm_api_key' or model-specific keys:
          - 'gemini_api_key'   for Google Gemini models
          - 'openai_api_key'   for OpenAI models
          - 'claude_api_key'   for Anthropic Claude models
          - 'huggingface_api_key' for HuggingFace models
          - 'perplexity_api_key'  for Perplexity models
        Falls back to 'llm_api_key' if no model-specific key is found.
        """
        import config as cfg

        secrets = ConfigValidator.load_yaml(secrets_yaml_path)

        # Model-type to key name mapping
        model_key_map = {
            "gemini": "gemini_api_key",
            "openai": "openai_api_key",
            "claude": "claude_api_key",
            "huggingface": "huggingface_api_key",
            "perplexity": "perplexity_api_key",
        }

        model_type = getattr(cfg, "LLM_MODEL_TYPE", "openai")
        specific_key = model_key_map.get(model_type)

        # Try model-specific key first, then fall back to generic llm_api_key
        if specific_key and specific_key in secrets and secrets[specific_key]:
            return secrets[specific_key]

        if "llm_api_key" in secrets and secrets["llm_api_key"]:
            return secrets["llm_api_key"]

        # Ollama doesn't need an API key
        if model_type == "ollama":
            return ""

        key_name = specific_key or "llm_api_key"
        raise ConfigError(
            f"Missing or empty API key for model type '{model_type}'. "
            f"Add '{key_name}' or 'llm_api_key' to {secrets_yaml_path}"
        )


class FileManager:
    """Handles file system operations and validations."""

    REQUIRED_FILES = [SECRETS_YAML, WORK_PREFERENCES_YAML, PLAIN_TEXT_RESUME_YAML]

    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> Tuple[Path, Path, Path, Path]:
        """Validate the existence of the data folder and required files."""
        if not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        missing_files = [file for file in FileManager.REQUIRED_FILES if not (app_data_folder / file).exists()]
        if missing_files:
            raise FileNotFoundError(f"Missing files in data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / "output"
        output_folder.mkdir(exist_ok=True)

        return (
            app_data_folder / SECRETS_YAML,
            app_data_folder / WORK_PREFERENCES_YAML,
            app_data_folder / PLAIN_TEXT_RESUME_YAML,
            output_folder,
        )

    @staticmethod
    def get_uploads(plain_text_resume_file: Path) -> Dict[str, Path]:
        """Convert resume file paths to a dictionary."""
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"Plain text resume file not found: {plain_text_resume_file}")

        uploads = {"plainTextResume": plain_text_resume_file}

        return uploads


def create_cover_letter(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Carica il resume in testo semplice
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")
        questions = [
    inquirer.Text('job_url', message="Please enter the URL of the job description:")
        ]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_browser()
        resume_generator.set_resume_object(resume_object)
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = resume_facade.create_cover_letter()         

        # Decodifica Base64 in dati binari
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Definisci il percorso della cartella di output utilizzando `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Crea la cartella se non esiste
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella di output creata o già esistente: {output_dir}")
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise
        
        output_path = output_dir / "cover_letter_tailored.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf_job_tailored(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Carica il resume in testo semplice
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")
        questions = [inquirer.Text('job_url', message="Please enter the URL of the job description:")]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_browser()
        resume_generator.set_resume_object(resume_object)
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = resume_facade.create_resume_pdf_job_tailored()         

        # Decodifica Base64 in dati binari
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Definisci il percorso della cartella di output utilizzando `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Crea la cartella se non esiste
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella di output creata o già esistente: {output_dir}")
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise
        
        output_path = output_dir / "resume_tailored.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Load the plain text resume
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        # Initialize StyleManager
        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")

        # Initialize the Resume Generator
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_browser()
        resume_generator.set_resume_object(resume_object)

        # Create the ResumeFacade
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        result_base64 = resume_facade.create_resume_pdf()

        # Decode Base64 to binary data
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Define the output directory using `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"])

        # Write the PDF file
        output_path = output_dir / "resume_base.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"Resume saved at: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def scan_email_inbox(parameters: dict):
    """
    Scan inbox for job-related messages and classify them into rejection,
    recruiter outreach, interview, and other categories.
    """
    try:
        questions = [
            inquirer.Text(
                "lookback_hours",
                message="How many hours back should JobHawk scan your inbox?",
                default="168",
            )
        ]
        answer = inquirer.prompt(questions) or {}
        lookback_raw = answer.get("lookback_hours", "168")

        try:
            lookback_hours = int(lookback_raw)
            if lookback_hours <= 0:
                raise ValueError
        except ValueError:
            raise ConfigError("lookback_hours must be a positive integer")

        secrets_file = parameters.get("secretsFile")
        if not secrets_file:
            raise ConfigError("Missing secrets file path in runtime parameters")

        secrets = ConfigValidator.load_yaml(secrets_file)
        scanner = InboxScanService(output_directory=Path(parameters["outputFileDirectory"]))
        summary = scanner.run_scan(secrets=secrets, lookback_hours=lookback_hours)

        summary_text = {
            "source_email": summary.source_email,
            "lookback_hours": summary.lookback_hours,
            "total_messages": summary.total_messages,
            "interview_messages": summary.interview_messages,
            "recruiter_messages": summary.recruiter_messages,
            "rejection_messages": summary.rejection_messages,
            "other_messages": summary.other_messages,
            "latest_report": str(Path(parameters["outputFileDirectory"]) / "email_scan_report_latest.json"),
        }
        print(json.dumps(summary_text, indent=2))
        logger.info("Inbox scan completed successfully.")
    except Exception as e:
        logger.exception(f"Inbox scan failed: {e}")
        raise


def generate_recruiter_briefing(parameters: dict, llm_api_key: str):
    """Generate a briefing card for a recruiter conversation."""
    try:
        questions = [
            inquirer.Text("company", message="Enter Company Name:"),
            inquirer.Text("role", message="Enter Job Role/Title:"),
        ]
        answers = inquirer.prompt(questions)
        company = answers.get("company")
        role = answers.get("role")
        
        if not company or not role:
            logger.warning("Company and Role are required.")
            return

        from src.libs.recruiter_prep import RecruiterPrepEngine
        from src.libs.llm_manager import AIAdapter
        
        ai_adapter = AIAdapter(parameters, llm_api_key)
        engine = RecruiterPrepEngine(ai_adapter)
        
        resume_path = parameters["uploads"]["plainTextResume"]
        briefing = engine.generate_briefing(company, role, resume_path)
        
        print("\n--- RECRUITER BRIEFING CARD ---")
        print(json.dumps(briefing, indent=2))
        print("-------------------------------\n")
        logger.info(f"Briefing card generated for {company}.")
    except Exception as e:
        logger.exception(f"Failed to generate recruiter briefing: {e}")


def analyze_job_match(parameters: dict, llm_api_key: str):
    """Analyze a job description against the resume using ATS scoring."""
    try:
        questions = [
            inquirer.List(
                "source",
                message="Where is the job description?",
                choices=["Latest Application", "Paste Text"],
                default="Latest Application",
            )
        ]
        answer = inquirer.prompt(questions)
        source = answer.get("source")
        
        description = ""
        if source == "Latest Application":
            apps_dir = Path("job_applications")
            if not apps_dir.exists():
                print("No applications found.")
                return
            dirs = sorted(apps_dir.glob("*"), key=lambda d: d.stat().st_mtime, reverse=True)
            if not dirs:
                print("No applications found.")
                return
            jd_path = dirs[0] / "job_description.json"
            if jd_path.exists():
                with open(jd_path, 'r') as f:
                    data = json.load(f)
                    description = data.get("description", "")
        else:
            questions = [inquirer.Editor("description", message="Paste the job description:")]
            # Note: Editor might not work in some terminals, could fallback to Text
            answer = inquirer.prompt(questions)
            description = answer.get("description", "")

        if not description:
            print("No job description found/provided.")
            return

        from src.libs.ats_scorer import ATSScorer
        from src.libs.llm_manager import AIAdapter
        
        ai_adapter = AIAdapter(parameters, llm_api_key)
        scorer = ATSScorer(ai_adapter)
        
        resume_path = parameters["uploads"]["plainTextResume"]
        analysis = scorer.score_job(resume_path, description)
        
        print("\n--- ATS SCORE REPORT ---")
        print(f"Match Score: {analysis.get('score', 0)}/100")
        print(f"Summary: {analysis.get('match_summary', '')}")
        print("\nTop Missing Keywords:", ", ".join(analysis.get("missing_keywords", [])))
        print("\nSurvival Tweaks (High ROI):")
        for tweak in analysis.get("survival_tweaks", []):
            print(f" - {tweak}")
        print("------------------------\n")
        logger.info("ATS analysis completed.")
    except Exception as e:
        logger.exception(f"ATS analysis failed: {e}")


def summarize_application_results(parameters: dict):
    """Summarize applied jobs and classify outcomes into success/failure buckets."""
    try:
        applications_dir = Path("job_applications")
        stats = ApplicationStatsService(applications_dir).summarize()

        summary = {
            "total_jobs": stats.total_jobs,
            "successes": stats.successes,
            "failures": stats.failures,
            "unknown": stats.unknown,
        }
        print(json.dumps(summary, indent=2))
        logger.info("Application summary completed successfully.")
    except Exception as e:
        logger.exception(f"Failed to summarize application results: {e}")
        raise


def run_application_bot(parameters: dict, llm_api_key: str):
    """Start the automated job application process (LinkedIn)."""
    try:
        questions = [
            inquirer.List(
                "platform",
                message="Select platform to apply on:",
                choices=["LinkedIn", "Indeed (Work in Progress)", "All"],
                default="LinkedIn",
            ),
            inquirer.Text(
                "count",
                message="How many jobs should JobHawk apply to in this batch?",
                default="5",
            )
        ]
        answers = inquirer.prompt(questions) or {}
        platform = answers.get("platform", "LinkedIn")
        count_raw = answers.get("count", "5")
        
        try:
            count = int(count_raw)
        except ValueError:
            count = 5
            
        secrets_file = parameters.get("secretsFile")
        secrets = ConfigValidator.load_yaml(secrets_file)
        
        manager = BotManager(secrets=secrets, config=parameters, llm_api_key=llm_api_key)
        
        if platform == "LinkedIn":
            manager.run_batch("linkedin", count=count)
        elif platform == "Indeed (Work in Progress)":
            manager.run_batch("indeed", count=count)
        elif platform == "All":
            manager.run_batch("linkedin", count=count)
            manager.run_batch("indeed", count=count)
            
        logger.info("Batch application run completed.")
    except Exception as e:
        logger.exception(f"Bot application run failed: {e}")
        raise

        
def handle_inquiries(selected_actions: List[str], parameters: dict, llm_api_key: Optional[str] = None):
    """
    Decide which function to call based on the selected user actions.

    :param selected_actions: List of actions selected by the user.
    :param parameters: Configuration parameters dictionary.
    :param llm_api_key: API key for the language model.
    """
    try:
        def require_llm_key() -> str:
            nonlocal llm_api_key
            if llm_api_key:
                return llm_api_key
            secrets_file = parameters.get("secretsFile")
            if not secrets_file:
                raise ConfigError("Secrets file path missing. Cannot load LLM API key.")
            llm_api_key = ConfigValidator.validate_secrets(secrets_file)
            return llm_api_key

        if selected_actions:
            if "Generate Resume" == selected_actions:
                logger.info("Crafting a standout professional resume...")
                create_resume_pdf(parameters, require_llm_key())
                
            if "Generate Resume Tailored for Job Description" == selected_actions:
                logger.info("Customizing your resume to enhance your job application...")
                create_resume_pdf_job_tailored(parameters, require_llm_key())
                
            if "Generate Tailored Cover Letter for Job Description" == selected_actions:
                logger.info("Designing a personalized cover letter to enhance your job application...")
                create_cover_letter(parameters, require_llm_key())

            if "Scan Inbox for Rejections/Recruiters/Interviews" == selected_actions:
                logger.info("Scanning inbox and classifying job-related emails...")
                scan_email_inbox(parameters)

            if "Summarize Job Application Results" == selected_actions:
                logger.info("Summarizing job applications with successes and failures...")
                summarize_application_results(parameters)
                
            if "Start Application Bot (Auto-Apply)" == selected_actions:
                logger.info("Starting automated job applications...")
                run_application_bot(parameters, require_llm_key())
                
            if "ATS Scorer (Analyze Job Match)" == selected_actions:
                logger.info("Analyzing job suitability...")
                analyze_job_match(parameters, require_llm_key())

            if "Generate Recruiter Briefing Card" == selected_actions:
                logger.info("Preparing for recruiter conversation...")
                generate_recruiter_briefing(parameters, require_llm_key())

        else:
            logger.warning("No actions selected. Nothing to execute.")
    except Exception as e:
        logger.exception(f"An error occurred while handling inquiries: {e}")
        raise

def prompt_user_action() -> str:
    """
    Use inquirer to ask the user which action they want to perform.

    :return: Selected action.
    """
    try:
        questions = [
            inquirer.List(
                'action',
                message="Select the action you want to perform:",
                choices=[
                    "Generate Resume",
                    "Start Application Bot (Auto-Apply)",
                    "ATS Scorer (Analyze Job Match)",
                    "Generate Recruiter Briefing Card",
                    "Generate Resume Tailored for Job Description",
                    "Generate Tailored Cover Letter for Job Description",
                    "Scan Inbox for Rejections/Recruiters/Interviews",
                    "Summarize Job Application Results",
                ],
            ),
        ]
        answer = inquirer.prompt(questions)
        if answer is None:
            print("No answer provided. The user may have interrupted.")
            return ""
        return answer.get('action', "")
    except Exception as e:
        print(f"An error occurred: {e}")
        return ""


def main():
    """Main entry point for the AIHawk Job Application Bot."""
    try:
        # Define and validate the data folder
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)

        # Validate configuration and secrets
        config = ConfigValidator.validate_config(config_file)
        # Prepare parameters
        config["uploads"] = FileManager.get_uploads(plain_text_resume_file)
        config["outputFileDirectory"] = output_folder
        config["secretsFile"] = secrets_file

        # Interactive prompt for user to select actions
        selected_actions = prompt_user_action()

        # Handle selected actions and execute them
        handle_inquiries(selected_actions, config)

    except ConfigError as ce:
        logger.error(f"Configuration error: {ce}")
        logger.error(
            "Refer to the configuration guide for troubleshooting: "
            "https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk?tab=readme-ov-file#configuration"
        )
    except FileNotFoundError as fnf:
        logger.error(f"File not found: {fnf}")
        logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        logger.error(f"Runtime error: {re}")
        logger.debug(traceback.format_exc())
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
