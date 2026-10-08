# In this file, you can set the configurations of the app.
# Version: 0.7.0

from src.utils.constants import DEBUG, ERROR

#config related to logging must have prefix LOG_
LOG_LEVEL = 'INFO'
LOG_SELENIUM_LEVEL = ERROR
LOG_TO_FILE = False
LOG_TO_CONSOLE = True

MINIMUM_WAIT_TIME_IN_SECONDS = 60

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7

JOB_MAX_APPLICATIONS = 5
JOB_MIN_APPLICATIONS = 1

import os

# LLM provider: 'quipu' | 'gemini' | 'openai' | 'claude' | 'ollama' | 'huggingface' | 'perplexity'
# 'quipu' (default, 2026-09-29) uses QUIPU's own route: OpenRouter with xAI
# fallback, model map / fallbacks / key resolution from
# pipeline/src/brain/llm_caller_openrouter.py (see src/libs/quipu_llm.py).
# Its key is OPENROUTER_API_KEY / XAI_API_KEY, not secrets.yaml.
LLM_MODEL_TYPE = os.environ.get("JOBHAWK_LLM_PROVIDER", "quipu").strip().lower()
# For 'quipu': a brain.yaml canonical ID (e.g. 'hermes-3-405b', 'glm-5.1') or a
# vendor/slug; empty = QUIPU's default model. For other providers, their model name.
LLM_MODEL = os.environ.get(
    "JOBHAWK_LLM_MODEL",
    "" if LLM_MODEL_TYPE == "quipu" else "gemini-2.5-flash",
).strip()
# Only required for OLLAMA models
LLM_API_URL = os.environ.get("JOBHAWK_LLM_API_URL", "")
