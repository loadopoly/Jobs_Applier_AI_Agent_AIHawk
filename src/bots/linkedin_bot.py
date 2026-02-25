from typing import List
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
            self.driver.find_element(By.ID, "username").send_keys(email)
            self.driver.find_element(By.ID, "password").send_keys(password)
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            logger.info("Logged into LinkedIn")
        except Exception as e:
            logger.error(f"Login failed: {e}")

    def search_jobs(self, query: str, location: str) -> List[Job]:
        # Simplified search logic for demonstration
        # In a real scenario, this would navigate to /jobs/search and parse results
        logger.info(f"Searching LinkedIn for {query} in {location}")
        
        # Mocking finding 2 jobs for test run
        return [
            Job(role=query, company="MockCorp", location=location, link="https://linkedin.com/jobs/1"),
            Job(role=query, company="BotWorks", location=location, link="https://linkedin.com/jobs/2")
        ]

    def apply(self, job: Job) -> JobApplication:
        # Simplified application logic
        logger.info(f"Applying to {job.role} at {job.company}")
        self.random_sleep(3, 6)
        
        return JobApplication(
            job=job,
            status="applied",
            platform="linkedin"
        )
