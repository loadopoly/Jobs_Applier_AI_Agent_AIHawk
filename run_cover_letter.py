#!/usr/bin/env python3
"""
CLI runner for Playwright-based LinkedIn Cover Letter Generator.
Usage:
    python run_cover_letter.py [JOB_URL]
"""
import sys
from pathlib import Path

# Ensure root is in sys.path
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.libs.playwright_cover_letter import run_playwright_cover_letter

def main():
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.linkedin.com/jobs/view/4451271011/"
    print(f"--- Launching JobHawk Playwright Cover Letter Generator ---")
    print(f"Target URL: {target_url}\n")
    try:
        run_playwright_cover_letter(target_url)
    except Exception as e:
        print(f"Execution failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
