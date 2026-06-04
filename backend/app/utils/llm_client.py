"""
LLM client wrapper.
Uses the OpenAI-format API uniformly.
Provides retry with temperature decay, JSON repair, and fence stripping.
"""

import json
import re
import time
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .logger import log_llm_interaction


class LLMClient:
    """LLM client."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        should_log: bool = True
    ) -> str:
        """
        Send a chat request.
        
        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format (e.g., JSON mode)
            should_log: Whether to save request/response to log file
            
        Returns:
            Model response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format and Config.LLM_JSON_MODE:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        content_raw = response.choices[0].message.content or ""
        # Some models (e.g., MiniMax M2.5) include <think> content that should be removed
        content_cleaned = re.sub(r'<think>[\s\S]*?</think>', '', content_raw).strip()

        if should_log:
            log_llm_interaction(
                source_file="llm_client.py",
                messages=messages,
                response_text=content_cleaned,
            )

        return content_cleaned
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send a chat request and return JSON.
        
        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            
        Returns:
            Parsed JSON object
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            should_log=False,
        )
        cleaned = _strip_fences(response)

        try:
            parsed_json = json.loads(cleaned)
            log_llm_interaction(
                source_file="llm_client.py",
                messages=messages,
                response_text=cleaned,
            )
            return parsed_json
        except json.JSONDecodeError:
            log_llm_interaction(
                source_file="llm_client.py",
                messages=messages,
                response_text=cleaned,
            )
            raise ValueError(f"Invalid JSON returned by LLM: {cleaned}")

    def chat_json_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_attempts: int = 3,
        temperature_decay: float = 0.1,
        backoff_base: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Send a chat request expecting JSON back, with retry, temperature decay,
        truncated-JSON repair, and fence stripping.

        Args:
            messages: Message list
            temperature: Starting temperature (decays by temperature_decay each retry)
            max_tokens: Maximum token count (None = let model decide)
            max_attempts: Number of attempts before raising
            temperature_decay: How much to lower temperature per retry
            backoff_base: Exponential backoff multiplier in seconds

        Returns:
            Parsed JSON dict
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            current_temp = max(0.0, temperature - attempt * temperature_decay)
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": current_temp,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if Config.LLM_JSON_MODE:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.client.chat.completions.create(**kwargs)
                content_raw = response.choices[0].message.content or ""
                finish_reason = response.choices[0].finish_reason

                # Strip think tags and fences
                content = re.sub(r'<think>[\s\S]*?</think>', '', content_raw).strip()
                content = _strip_fences(content)

                log_llm_interaction(
                    source_file="llm_client.py",
                    messages=messages,
                    response_text=content,
                )

                # Handle truncation
                if finish_reason == "length":
                    content = _fix_truncated_json(content)

                # Try parsing
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    # Attempt repair
                    repaired = _try_repair_json(content)
                    if repaired is not None:
                        return repaired
                    last_error = e

            except Exception as e:
                last_error = e
                time.sleep(backoff_base * (attempt + 1))

        raise last_error or Exception("LLM JSON call failed after retries")


# ─── Private helpers ───────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fence wrappers from LLM output."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _fix_truncated_json(content: str) -> str:
    """Attempt to close unclosed brackets/braces in truncated JSON."""
    content = content.strip()

    # Close an unclosed string literal
    if content and content[-1] not in '",}]':
        content += '"'

    open_brackets = content.count('[') - content.count(']')
    open_braces = content.count('{') - content.count('}')

    content += ']' * max(0, open_brackets)
    content += '}' * max(0, open_braces)

    return content


def _try_repair_json(content: str) -> Optional[Dict[str, Any]]:
    """Try multiple strategies to extract valid JSON from malformed content."""
    # Strategy 1: fix truncation
    fixed = _fix_truncated_json(content)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract outermost JSON object
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        candidate = json_match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Strategy 3: strip control characters
            cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', candidate)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    return None
