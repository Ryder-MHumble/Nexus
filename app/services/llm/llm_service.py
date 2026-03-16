"""OpenRouter LLM service for business data enrichment."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.services.llm.llm_call_tracker import get_tracker

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


async def call_llm(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
    *,
    stage: str = "general",
    article_id: str | None = None,
    article_title: str | None = None,
    source_id: str | None = None,
    dimension: str | None = None,
) -> str:
    """
    Call OpenRouter API for LLM completion.

    Args:
        prompt: User message content.
        system_prompt: System instruction.
        model: Model ID (defaults to settings.OPENROUTER_MODEL).
        temperature: Sampling temperature.
        max_tokens: Maximum response tokens.
        json_mode: If True, request JSON output format.
        stage: Pipeline stage for tracking (policy, personnel, tech_frontier, etc.).
        article_id: Article/URL hash for reference.
        article_title: Article title for audit trail.
        source_id: News source ID.
        dimension: Data dimension.

    Returns:
        The assistant's response text.

    Raises:
        LLMError: If the API call fails after retries.
    """
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise LLMError("OPENROUTER_API_KEY not configured")

    model = model or settings.OPENROUTER_MODEL
    tracker = get_tracker()
    start_time = time.time()

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://information-crawler.local",
        "X-Title": "Information Crawler",
    }

    last_error: Exception | None = None
    last_response: dict[str, Any] = {}

    # Use longer timeout for heavier models (e.g. gemini-2.5-pro)
    timeout_secs = 180.0 if "pro" in (model or "").lower() else 60.0

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout_secs) as client:
                resp = await client.post(
                    OPENROUTER_API_URL,
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                last_response = data

                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                if not content:
                    raise LLMError(f"Empty response from model {model}")

                # Track successful API call
                duration_ms = (time.time() - start_time) * 1000
                usage = data.get("usage", {})
                tracker.log_call(
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_text=content,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    stage=stage,
                    article_id=article_id,
                    article_title=article_title,
                    source_id=source_id,
                    dimension=dimension,
                    duration_ms=duration_ms,
                    success=True,
                )

                return content

        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code == 429:
                import asyncio
                wait = 2 ** attempt
                logger.warning("Rate limited, waiting %ds...", wait)
                await asyncio.sleep(wait)
                continue
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            tracker.log_call(
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                response_text="",
                input_tokens=0,
                output_tokens=0,
                stage=stage,
                article_id=article_id,
                article_title=article_title,
                source_id=source_id,
                dimension=dimension,
                duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message=error_msg,
            )
            raise LLMError(error_msg) from e

        except httpx.RequestError as e:
            last_error = e
            logger.warning("Request error (attempt %d): %s", attempt + 1, e)
            import asyncio
            await asyncio.sleep(1)
            continue

    error_msg = f"Failed after 3 attempts: {last_error}"
    tracker.log_call(
        model=model,
        prompt=prompt,
        system_prompt=system_prompt,
        response_text="",
        input_tokens=0,
        output_tokens=0,
        stage=stage,
        article_id=article_id,
        article_title=article_title,
        source_id=source_id,
        dimension=dimension,
        duration_ms=(time.time() - start_time) * 1000,
        success=False,
        error_message=error_msg,
    )
    raise LLMError(error_msg)


async def call_llm_json(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    *,
    stage: str = "general",
    article_id: str | None = None,
    article_title: str | None = None,
    source_id: str | None = None,
    dimension: str | None = None,
) -> dict[str, Any] | list[Any]:
    """
    Call LLM and parse the response as JSON.

    Returns parsed JSON (dict or list).
    """
    raw = await call_llm(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
        stage=stage,
        article_id=article_id,
        article_title=article_title,
        source_id=source_id,
        dimension=dimension,
    )

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to parse LLM response as JSON: {e}\nRaw: {text[:500]}") from e


class LLMError(Exception):
    """Raised when LLM service call fails."""
