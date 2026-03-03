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


class LinkedInBot(BaseBot):
    def __init__(self, secrets: dict):
        super().__init__("linkedin")
        self.secrets = secrets
        self.driver = None

    def login(self):
        email = self.secrets.get("linkedin_email")
        password = self.secrets.get("linkedin_password")
        
        if not email or not password:
            logger.warning("LinkedIn credentials missing. Skipping login.")
            return

        self.driver = init_browser()
        self.driver.get("https://www.linkedin.com/login")
        
        try:
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "username")))
            self.driver.find_element(By.ID, "username").send_keys(email)
            self.driver.find_element(By.ID, "password").send_keys(password)
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            # Wait for redirect away from login page
            WebDriverWait(self.driver, 15).until(lambda d: "linkedin.com/login" not in d.current_url)
            logger.info("Logged into LinkedIn")
        except Exception as e:
            logger.error(f"Login failed: {e}")

    def search_jobs(self, query: str, location: str, count: int = 10) -> List[Job]:
        """Search LinkedIn jobs and return real job listings."""
        if self.driver is None:
            logger.error("Browser not initialized. Call login() first.")
            return []

        logger.info(f"Searching LinkedIn for '{query}' in '{location}'")
        
        encoded_query = urllib.parse.quote(query)
        encoded_location = urllib.parse.quote(location)
        url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={encoded_query}&location={encoded_location}"
            f"&f_AL=true&f_TPR=r86400&sortBy=DD"  # Easy Apply, last 24h, newest
        )
        
        jobs = []
        try:
            self.driver.get(url)
            time.sleep(3)
            
            # Scroll to load more results
            for _ in range(2):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            
            job_cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "ul.jobs-search__results-list li, div.job-search-card, li.jobs-search-results__list-item"
            )
            
            if not job_cards:
                # Try alternate selector
                job_cards = self.driver.find_elements(By.CSS_SELECTOR, "[data-job-id], .job-card-container")
            
            logger.info(f"Found {len(job_cards)} job cards for '{query}'")
            
            for card in job_cards[:count]:
                try:
                    title_el = card.find_element(By.CSS_SELECTOR, "h3, .job-card-list__title, .base-search-card__title")
                    company_el = card.find_element(By.CSS_SELECTOR, "h4, .job-card-container__company-name, .base-search-card__subtitle")
                    location_el = card.find_element(By.CSS_SELECTOR, ".job-card-container__metadata-item, .job-search-card__location, .base-search-card__metadata")
                    
                    link = ""
                    try:
                        link_el = card.find_element(By.CSS_SELECTOR, "a")
                        link = link_el.get_attribute("href") or ""
                        # Trim tracking params
                        if "?" in link:
                            link = link.split("?")[0]
                    except Exception:
                        pass
                    
                    # Get job description by clicking card
                    description = ""
                    try:
                        card.find_element(By.CSS_SELECTOR, "a").click()
                        time.sleep(2)
                        desc_el = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR,
                                ".jobs-description__content, .show-more-less-html__markup, .jobs-box__html-content"))
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
                    logger.debug(f"Could not parse job card: {e}")
                    continue
        except Exception as e:
            logger.error(f"Job search failed: {e}")
        
        logger.info(f"Parsed {len(jobs)} real jobs for '{query}' in '{location}'")
        return jobs

    def apply(self, job: Job) -> JobApplication:
        """Apply to a job via LinkedIn Easy Apply."""
        logger.info(f"Applying to {job.role} at {job.company}")
        
        if self.driver is None or not job.link:
            logger.warning("Cannot apply: browser not ready or no job link.")
            return JobApplication(job=job, status="failed", platform="linkedin")
        
        try:
            self.driver.get(job.link)
            self.random_sleep(2, 4)
            
            # Click Easy Apply button
            easy_apply_btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    ".jobs-apply-button--top-card button, button[aria-label*='Easy Apply'], .jobs-s-apply button"))
            )
            easy_apply_btn.click()
            self.random_sleep(1, 2)
            
            # Walk through multi-step form — submit/next until done or max steps
            max_steps = 8
            for _ in range(max_steps):
                try:
                    # Submit button (final step)
                    submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[aria-label='Submit application']")
                    submit_btn.click()
                    logger.info(f"Application submitted for {job.role} at {job.company}")
                    return JobApplication(job=job, status="applied", platform="linkedin")
                except Exception:
                    pass
                
                try:
                    # Next/Review button (intermediate step)
                    next_btn = self.driver.find_element(By.CSS_SELECTOR,
                        "button[aria-label='Continue to next step'], button[aria-label='Review your application']")
                    next_btn.click()
                    self.random_sleep(1, 2)
                except Exception:
                    break
            
            logger.warning(f"Could not complete Easy Apply for {job.role} at {job.company}")
            return JobApplication(job=job, status="partial", platform="linkedin")
        
        except Exception as e:
            logger.error(f"Apply failed for {job.role} at {job.company}: {e}")
            return JobApplication(job=job, status="failed", platform="linkedin")

