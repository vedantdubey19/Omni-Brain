import os
from typing import Tuple, Optional, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_gemini_api_key() -> str:
    """Retrieve Gemini API key from environment variables (case-insensitive)."""
    for key_name in ["GEMINI_API_KEY", "Gemini_API_KEY", "gemini_api_key"]:
        val = os.getenv(key_name, "").strip()
        if val and not val.startswith("sk-placeholder") and not val.startswith("your-"):
            return val
    return ""


def get_openai_api_key() -> str:
    """Retrieve OpenAI API key from environment variables."""
    val = os.getenv("OPENAI_API_KEY", "").strip()
    if val and not val.startswith("sk-placeholder") and not val.startswith("your-"):
        return val
    return ""


def get_llm_client(timeout_seconds: float = 15.0) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """
    Returns (client, default_model, provider_name).
    Prefers Gemini if GEMINI_API_KEY is configured, else falls back to OpenAI.
    Returns (None, None, None) if neither key is configured.
    """
    gemini_key = get_gemini_api_key()
    if gemini_key:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=timeout_seconds,
                max_retries=0
            )
            return client, "gemini-2.5-flash", "gemini"
        except Exception as e:
            print(f"[llm_client] Failed to initialize Gemini OpenAI client: {e}")

    openai_key = get_openai_api_key()
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key, timeout=timeout_seconds)
            return client, "gpt-4o-mini", "openai"
        except Exception as e:
            print(f"[llm_client] Failed to initialize OpenAI client: {e}")

    return None, None, None


def get_vision_client(timeout_seconds: float = 20.0) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """
    Returns (client, vision_model, provider_name) for Multimodal Visual Reasoning.
    """
    client, model, provider = get_llm_client(timeout_seconds=timeout_seconds)
    if provider == "gemini":
        return client, "gemini-2.5-flash", "gemini"
    elif provider == "openai":
        return client, "gpt-4o", "openai"
    return None, None, None
