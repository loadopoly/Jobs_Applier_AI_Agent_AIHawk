"""
This module contains utility functions for the Resume and Cover Letter Builder service.
"""

# app/libs/resume_and_cover_builder/utils.py
import json
import openai
import time
from datetime import datetime
from typing import Any, Dict, List
from langchain_core.messages.ai import AIMessage
from langchain_core.prompt_values import StringPromptValue
from .config import global_config
from loguru import logger
from requests.exceptions import HTTPError as HTTPStatusError


def create_llm_from_config(api_key: str) -> Any:
    """
    Create a LangChain chat model based on the LLM_MODEL_TYPE and LLM_MODEL
    settings in config.py.  Supported types: openai, gemini, claude, ollama,
    huggingface, perplexity.
    """
    import config as cfg

    llm_model_type = getattr(cfg, "LLM_MODEL_TYPE", "openai").lower()
    llm_model = getattr(cfg, "LLM_MODEL", "gpt-4o-mini")
    llm_api_url = getattr(cfg, "LLM_API_URL", "")

    logger.debug(f"Creating LLM of type '{llm_model_type}' with model '{llm_model}'")

    if llm_model_type == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model_name=llm_model, openai_api_key=api_key, temperature=0.4)
    elif llm_model_type == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
        return ChatGoogleGenerativeAI(
            model=llm_model,
            google_api_key=api_key,
            temperature=0.4,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            },
        )
    elif llm_model_type == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=llm_model, api_key=api_key, temperature=0.4)
    elif llm_model_type == "ollama":
        from langchain_ollama import ChatOllama
        if llm_api_url:
            return ChatOllama(model=llm_model, base_url=llm_api_url)
        return ChatOllama(model=llm_model)
    elif llm_model_type == "huggingface":
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
        endpoint = HuggingFaceEndpoint(
            repo_id=llm_model, huggingfacehub_api_token=api_key, temperature=0.4
        )
        return ChatHuggingFace(llm=endpoint)
    elif llm_model_type == "perplexity":
        from langchain_community.chat_models import ChatPerplexity
        return ChatPerplexity(model=llm_model, api_key=api_key, temperature=0.4)
    else:
        raise ValueError(f"Unsupported LLM model type: '{llm_model_type}'. "
                         "Choose from: openai, gemini, claude, ollama, huggingface, perplexity")


def create_embeddings_from_config(api_key: str) -> Any:
    """
    Create a LangChain embeddings model based on the LLM_MODEL_TYPE setting in
    config.py.  Falls back to OpenAI embeddings for non-Gemini types.
    """
    import config as cfg

    llm_model_type = getattr(cfg, "LLM_MODEL_TYPE", "openai").lower()

    if llm_model_type == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model="models/embedding-001", google_api_key=api_key
        )
    else:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(openai_api_key=api_key)


class LLMLogger:

    def __init__(self, llm: Any):
        self.llm = llm

    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]):
        calls_log = global_config.LOG_OUTPUT_FILE_PATH / "open_ai_calls.json"
        if isinstance(prompts, StringPromptValue):
            prompts = prompts.text
        elif isinstance(prompts, Dict):
            # Convert prompts to a dictionary if they are not in the expected format
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }
        else:
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract token usage details from the response
        token_usage = parsed_reply["usage_metadata"]
        output_tokens = token_usage["output_tokens"]
        input_tokens = token_usage["input_tokens"]
        total_tokens = token_usage["total_tokens"]

        # Extract model details from the response
        model_name = parsed_reply["response_metadata"]["model_name"]
        prompt_price_per_token = 0.00000015
        completion_price_per_token = 0.0000006

        # Calculate the total cost of the API call
        total_cost = (input_tokens * prompt_price_per_token) + (
            output_tokens * completion_price_per_token
        )

        # Create a log entry with all relevant information
        log_entry = {
            "model": model_name,
            "time": current_time,
            "prompts": prompts,
            "replies": parsed_reply["content"],  # Response content
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
        }

        # Write the log entry to the log file in JSON format
        with open(calls_log, "a", encoding="utf-8") as f:
            json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
            f.write(json_string + "\n")


class LoggerChatModel:

    def __init__(self, llm: Any):
        self.llm = llm

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        max_retries = 15
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                reply = self.llm.invoke(messages)
                parsed_reply = self.parse_llmresult(reply)
                LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
                return reply
            except openai.RateLimitError as err:
                wait_time = self.parse_wait_time_from_error_message(str(err))
                logger.warning(f"OpenAI rate limit exceeded. Waiting {wait_time}s before retrying (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            except HTTPStatusError as err:
                if err.response.status_code == 429:
                    logger.warning(f"HTTP 429 Too Many Requests: Waiting for {retry_delay} seconds before retrying (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"HTTP error {err.response.status_code}: {err}")
                    raise
            except Exception as e:
                # Catch Gemini / Anthropic / HuggingFace rate-limit and transient errors
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower() or "resource exhausted" in err_str.lower():
                    logger.warning(f"Rate limit / quota error from LLM. Waiting {retry_delay}s before retrying (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Unexpected error occurred: {err_str}, retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2

        logger.critical("Failed to get a response from the model after multiple attempts.")
        raise Exception("Failed to get a response from the model after multiple attempts.")

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        # Parse the LLM result into a structured format.
        content = llmresult.content
        response_metadata = llmresult.response_metadata
        id_ = llmresult.id
        usage_metadata = llmresult.usage_metadata

        parsed_result = {
            "content": content,
            "response_metadata": {
                "model_name": response_metadata.get("model_name", ""),
                "system_fingerprint": response_metadata.get("system_fingerprint", ""),
                "finish_reason": response_metadata.get("finish_reason", ""),
                "logprobs": response_metadata.get("logprobs", None),
            },
            "id": id_,
            "usage_metadata": {
                "input_tokens": usage_metadata.get("input_tokens", 0),
                "output_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            },
        }
        return parsed_result
