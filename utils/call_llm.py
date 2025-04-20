import os
import logging
import json
from datetime import datetime
from openai import OpenAI

# Configure logging
log_directory = os.getenv("LOG_DIR", "logs")
os.makedirs(log_directory, exist_ok=True)
log_file = os.path.join(log_directory, f"llm_calls_{datetime.now().strftime('%Y%m%d')}.log")
logger = logging.getLogger("llm_logger")
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent propagation to root logger
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)

def call_llm(prompt: str, use_cache: bool = True) -> str:
    """
    Calls an OpenAI-compatible LLM endpoint to generate a response to the prompt.
    The base URL can be set via the OPENAI_BASE_URL environment variable.
    API key is read from OPENAI_API_KEY.
    The function caches responses if use_cache is True.
    """
    logger.info(f"PROMPT: {prompt}")

    # Simple cache configuration
    cache_file = "llm_cache.json"
    cache = {}
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache, starting with empty cache: {e}")
        if prompt in cache:
            logger.info(f"RESPONSE: {cache[prompt]}")
            return cache[prompt]

    try:
        base_url = os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("OPENAI_API_KEY", "your-api-key")
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "text"},
        )
        response_text = r.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        response_text = f"[OpenAI call failed: {e}]"

    # Save to cache if enabled and successful
    if use_cache and response_text and not response_text.startswith("["):
        cache[prompt] = response_text
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")


    return response_text
    
