import json
from pathlib import Path
from unittest.mock import MagicMock
import src.bots.linkedin_bot
import src.utils.chrome_utils

# Mock browser initialization to avoid "Chrome binary not found" error
src.utils.chrome_utils.init_browser = MagicMock(return_value=MagicMock())
src.bots.linkedin_bot.init_browser = src.utils.chrome_utils.init_browser

# Mock ATS Scoring to avoid LLM call in test
from src.libs.ats_scorer import ATSScorer
ATSScorer.score_job = MagicMock(return_value={
    "score": 85,
    "match_summary": "Good match based on mock data.",
    "missing_keywords": ["FastAPI"],
    "strong_points": ["Python", "Automation"],
    "survival_tweaks": ["Highlight FastAPI projects."]
})

from src.bots.bot_manager import BotManager
from src.application_stats import ApplicationStatsService
from config import LLM_MODEL_TYPE

def main():
    # Load configuration
    secrets = {
        "linkedin_email": "test@example.com",
        "linkedin_password": "testpassword"
    }
    config = {
        "positions": ["Software Engineer"],
        "locations": ["Remote"],
        "secretsFile": Path("data_folder/secrets.yaml"),
        "outputFileDirectory": Path("data_folder/output")
    }
    
    # Run a batch of 2 jobs
    manager = BotManager(secrets=secrets, config=config, llm_api_key="mock_key")
    print("--- Starting Bot Run (Mock) ---")
    manager.run_linkedin_batch(count=2)
    
    # Summarize results
    print("\n--- Summarizing Results ---")
    stats = ApplicationStatsService(Path("job_applications")).summarize()
    print(json.dumps(stats.as_dict(), indent=2))

if __name__ == "__main__":
    print("SCRIPT STARTING")
    main()
