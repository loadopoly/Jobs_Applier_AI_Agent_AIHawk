import random
import time
from abc import ABC, abstractmethod
from typing import List

from src.job import Job
from src.job_application import JobApplication
from src.logging import logger


class BaseBot(ABC):
    def __init__(self, platform: str):
        self.platform = platform

    @abstractmethod
    def login(self):
        pass

    @abstractmethod
    def search_jobs(self, query: str, location: str) -> List[Job]:
        pass

    @abstractmethod
    def apply(self, job: Job) -> JobApplication:
        pass

    def ensure_browser(self) -> bool:
        """Open a browser if login() has not. Public job search needs no session."""
        if getattr(self, "driver", None) is not None:
            return True
        try:
            from src.utils.chrome_utils import init_browser
            self.driver = init_browser()
            logger.info(f"{self.platform}: browser opened without login (public search)")
            return True
        except Exception as exc:
            logger.error(f"{self.platform}: could not open browser: {exc}")
            return False

    def close(self):
        """Quit the browser. The web service is long-lived, so every batch must
        release its Chromium instead of relying on process exit."""
        driver = getattr(self, "driver", None)
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                logger.debug(f"{self.platform}: driver.quit() failed: {exc}")
            self.driver = None

    def random_sleep(self, min_s: float = 2.0, max_s: float = 5.0):
        time.sleep(random.uniform(min_s, max_s))
