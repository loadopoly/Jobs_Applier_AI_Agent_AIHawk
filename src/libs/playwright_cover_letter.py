import subprocess
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

try:
    from src.logging import logger
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("JobHawk")


def run_playwright_cover_letter(job_url: Optional[str] = None, auto_update_app: bool = True) -> Dict[str, Any]:
    """
    Executes the Playwright-based LinkedIn cover letter generator script,
    tailors the application with regards to the live posting, and updates
    JobHawk's live application records.
    
    :param job_url: URL to the LinkedIn job posting.
    :param auto_update_app: Whether to automatically create/update the job application in job_applications/.
    :return: Dictionary with execution details and file paths.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "playwright_cover_letter.js"
    
    if not script_path.exists():
        raise FileNotFoundError(f"Playwright script not found at {script_path}")
        
    cmd = ["node", str(script_path)]
    if job_url:
        cmd.append(job_url)
    if auto_update_app:
        cmd.append("--auto")
    cmd.append("--json")
        
    logger.info(f"Running automated Playwright LinkedIn live application updater for: {job_url or 'default posting'}")
    
    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode != 0:
        logger.error(f"Playwright script failed with code {result.returncode}: {result.stderr}")
        raise RuntimeError(f"Playwright script failed: {result.stderr or result.stdout}")
        
    raw_output = result.stdout
    print(raw_output)
    
    # Extract JSON summary if present
    parsed_json = {}
    if "--- JSON RESULT ---" in raw_output:
        try:
            json_str = raw_output.split("--- JSON RESULT ---")[-1].strip()
            parsed_json = json.loads(json_str)
        except Exception as e:
            logger.warning(f"Could not parse JSON output from Playwright runner: {e}")
            
    return parsed_json
