#!/usr/bin/env python3
"""
Automated Live Application Runner for JobHawk using Playwright.
Usage:
    python run_cover_letter.py [JOB_URL] [--no-auto]
"""
import sys
import json
from pathlib import Path

# Ensure root is in sys.path
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.libs.playwright_cover_letter import run_playwright_cover_letter
from src.application_stats import ApplicationStatsService

def main():
    target_url = "https://www.linkedin.com/jobs/view/4451271011/"
    auto_update = True
    
    for arg in sys.argv[1:]:
        if arg.startswith("http://") or arg.startswith("https://"):
            target_url = arg
        elif arg in ("--no-auto", "--manual"):
            auto_update = False
        elif arg in ("--auto", "--automated"):
            auto_update = True

    print("================================================================")
    print("      JobHawk Automated Live Application Processor")
    print("================================================================")
    print(f"Target Live Job URL: {target_url}")
    print(f"Auto-update Application Records: {auto_update}\n")
    
    try:
        result = run_playwright_cover_letter(target_url, auto_update_app=auto_update)
        
        # Summarize application stats
        app_dir = repo_root / "job_applications"
        if app_dir.exists():
            stats = ApplicationStatsService(app_dir).summarize()
            print("\n---------------- Application Statistics ----------------")
            print(json.dumps(stats.as_dict(), indent=2))
            print("--------------------------------------------------------\n")
            
        print("[SUCCESS] Automated live application processing complete.")
    except Exception as e:
        print(f"[ERROR] Execution failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
