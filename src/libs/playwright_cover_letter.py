import subprocess
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple

try:
    from src.logging import logger
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("JobHawk")

def run_playwright_cover_letter(job_url: Optional[str] = None) -> Tuple[str, Path]:
    """
    Executes the Playwright-based LinkedIn cover letter generator script.
    
    :param job_url: URL to the LinkedIn job posting.
    :return: (cover_letter_text, output_file_path)
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "playwright_cover_letter.js"
    
    if not script_path.exists():
        raise FileNotFoundError(f"Playwright script not found at {script_path}")
        
    cmd = ["node", str(script_path)]
    if job_url:
        cmd.append(job_url)
        
    logger.info(f"Running Playwright LinkedIn cover letter generator for: {job_url or 'default posting'}")
    
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
        
    output_text = result.stdout
    print(output_text)
    
    # Locate the output file
    output_dir = repo_root / "data_folder" / "output"
    saved_files = sorted(output_dir.glob("cover_letter_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest_file = saved_files[0] if saved_files else output_dir / "cover_letter_latest.txt"
    
    return output_text, latest_file
