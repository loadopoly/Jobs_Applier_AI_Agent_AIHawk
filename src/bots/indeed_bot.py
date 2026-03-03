from typing import List
import time
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from src.bots.base_bot import BaseBot
from src.job import Job
from src.job_application import JobApplication
from src.utils.chrome_utils import init_browser
from src.logging import logger

class IndeedBot(BaseBot):
    def __init__(self, secrets: dict):
        super().__init__("indeed")
        self.secrets = secrets
        self.driver = None

    def login(self):
        email = self.secrets.get("indeed_email")
        password = self.secrets.get("indeed_password")
        
        if not email or not password:
            logger.warning("Indeed credentials missing. Skipping login.")
            return

        self.driver = init_browser()
        self.driver.get("https://www.indeed.com/auth")
        
        try:
            # Note: Indeed usually has more complex CAPTCHAs, but we'll skeleton the flow
            self.driver.find_element(By.ID, "ifl-InputTextField-email").send_keys(email)
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            # Wait for password field would happen here
            logger.info("Indeed login flow started (Manual verification might be needed due to Cloudflare)")
        except Exception as e:
            logger.error(f"Indeed login failed: {e}")

    def search_jobs(self, query: str, location: str, count: int = 10) -> List[Job]:
        """Search Indeed for real job listings."""
        if self.driver is None:
            logger.error("Browser not initialized. Call login() first.")
            return []

        logger.info(f"Searching Indeed for '{query}' in '{location}'")

        encoded_query = urllib.parse.quote(query)
        encoded_location = urllib.parse.quote(location)
        url = f"https://www.indeed.com/jobs?q={encoded_query}&l={encoded_location}&sort=date&fromage=1"

        jobs = []
        try:
            self.driver.get(url)
            time.sleep(3)

            job_cards = self.driver.find_elements(By.CSS_SELECTOR, ".job_seen_beacon, .jobsearch-ResultsList .result")
            logger.info(f"Found {len(job_cards)} job cards for '{query}'")

            for card in job_cards[:count]:
                try:
                    title_el = card.find_element(By.CSS_SELECTOR, "h2.jobTitle a, [data-testid='jobTitle']")
                    company_el = card.find_element(By.CSS_SELECTOR, "[data-testid='company-name'], .companyName")
                    location_el = card.find_element(By.CSS_SELECTOR, "[data-testid='text-location'], .companyLocation")
                    link = title_el.get_attribute("href") or ""

                    description = ""
                    try:
                        title_el.click()
                        time.sleep(2)
                        desc_el = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "#jobDescriptionText"))
                        )
                        description = desc_el.text[:3000]
                    except Exception:
                        pass

                    jobs.append(Job(
                        role=title_el.text.strip(),
                        company=company_el.text.strip(),
                        location=location_el.text.strip(),
                        link=link,
                        description=description,
                    ))
                except Exception as e:
                    logger.debug(f"Could not parse Indeed job card: {e}")
                    continue
        except Exception as e:
            logger.error(f"Indeed job search failed: {e}")

        logger.info(f"Parsed {len(jobs)} real jobs from Indeed for '{query}' in '{location}'")
        return jobs

    def apply(self, job: Job) -> JobApplication:
        logger.info(f"Applying on Indeed to {job.role} at {job.company}")
        if self.driver is None or not job.link:
            logger.warning("Cannot apply: browser not ready or no job link.")
            return JobApplication(job=job, status="failed", platform="indeed")

        try:
            self.driver.get(job.link)
            self.random_sleep(2, 4)

            apply_btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "button[id='indeedApplyButton'], .ia-IndeedApplyButton, [data-testid='IndeedApplyButton']"))
            )
            apply_btn.click()
            self.random_sleep(2, 3)

            # Submit if available
            try:
                submit_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
                )
                submit_btn.click()
                logger.info(f"Application submitted for {job.role} at {job.company}")
                return JobApplication(job=job, status="applied", platform="indeed")
            except Exception:
                pass

            return JobApplication(job=job, status="partial", platform="indeed")
        except Exception as e:
            logger.error(f"Indeed apply failed for {job.role} at {job.company}: {e}")
            return JobApplication(job=job, status="failed", platform="indeed")

