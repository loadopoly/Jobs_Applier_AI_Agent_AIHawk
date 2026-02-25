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

    def random_sleep(self, min_s: float = 2.0, max_s: float = 5.0):
        time.sleep(random.uniform(min_s, max_s))
