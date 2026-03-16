"""LLM API call tracking — cost, usage, and audit logging."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

LOGS_DIR = BASE_DIR / "data" / "logs" / "llm_calls"
SUMMARY_FILE = LOGS_DIR / "summary.json"
CALLS_LOG_FILE = LOGS_DIR / "calls.jsonl"

# OpenRouter pricing (USD per 1M tokens) — update based on actual model costs
PRICING_MAP = {
    "google/gemini-2.0-flash-001": {
        "input": 0.075,
        "output": 0.30,
    },
    "google/gemini-2.5-pro": {
        "input": 1.25,
        "output": 5.0,
    },
    "google/gemini-2.5-flash": {
        "input": 0.15,
        "output": 0.60,
    },
    "google/gemini-3-flash-preview": {
        "input": 0.075,
        "output": 0.30,
    },
    "openai/gpt-4o": {
        "input": 2.5,
        "output": 10.0,
    },
    "openai/gpt-4-turbo": {
        "input": 10.0,
        "output": 30.0,
    },
    "meta-llama/llama-3.1-405b-instruct": {
        "input": 0.54,
        "output": 0.81,
    },
}


class LLMCallTracker:
    """Track LLM API calls with cost, tokens, and audit information."""

    def __init__(self):
        self._ensure_logs_dir()

    @staticmethod
    def _ensure_logs_dir() -> None:
        """Create logs directory if it doesn't exist."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def log_call(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str,
        response_text: str,
        input_tokens: int,
        output_tokens: int,
        stage: str = "general",
        article_id: str | None = None,
        article_title: str | None = None,
        source_id: str | None = None,
        dimension: str | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """Log a single LLM API call.

        Args:
            model: Model identifier (e.g., 'google/gemini-2.0-flash-001')
            prompt: User prompt sent to LLM
            system_prompt: System instruction
            response_text: Full response text from LLM
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            stage: Pipeline stage name (policy, personnel, tech_frontier, etc.)
            article_id: URL hash or article identifier
            article_title: Article title for reference
            source_id: News source ID
            dimension: Data dimension (national_policy, beijing_policy, etc.)
            duration_ms: API call duration in milliseconds
            success: Whether the call succeeded
            error_message: Error details if call failed
        """
        now = datetime.now(timezone.utc)
        cost_usd = self._calculate_cost(model, input_tokens, output_tokens)

        call_record = {
            "timestamp": now.isoformat(),
            "model": model,
            "stage": stage,
            "article_id": article_id,
            "article_title": article_title,
            "source_id": source_id,
            "dimension": dimension,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(cost_usd, 6),
            "duration_ms": duration_ms,
            "success": success,
            "error_message": error_message,
            "prompt_length": len(prompt),
            "system_prompt_length": len(system_prompt),
            "response_length": len(response_text),
        }

        # Append to JSONL log
        self._append_to_log(call_record)

        # Update summary
        self._update_summary(model, input_tokens, output_tokens, cost_usd, success)

        # Log to standard logger
        if success:
            logger.info(
                "LLM call [%s/%s] — model=%s, tokens=%d/%d (%.2f¢), duration=%.1fms",
                stage, article_id or "?",
                model.split("/")[-1],
                input_tokens, output_tokens,
                cost_usd * 100,  # Convert to cents
                duration_ms or 0,
            )
        else:
            logger.warning(
                "LLM call failed [%s/%s] — %s",
                stage, article_id or "?",
                error_message,
            )

    @staticmethod
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate API cost in USD."""
        pricing = PRICING_MAP.get(model)
        if not pricing:
            logger.warning("Unknown model pricing: %s", model)
            return 0.0

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    @staticmethod
    def _append_to_log(call_record: dict[str, Any]) -> None:
        """Append call record to JSONL log file."""
        try:
            with open(CALLS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(call_record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("Failed to write LLM call log: %s", e)

    @staticmethod
    def _update_summary(
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        success: bool,
    ) -> None:
        """Update summary statistics."""
        try:
            summary = {}
            if SUMMARY_FILE.exists():
                with open(SUMMARY_FILE, encoding="utf-8") as f:
                    summary = json.load(f)

            if "last_updated" not in summary:
                summary["last_updated"] = datetime.now(timezone.utc).isoformat()

            if "models" not in summary:
                summary["models"] = {}

            model_key = model.split("/")[-1]  # Extract model name
            if model_key not in summary["models"]:
                summary["models"][model_key] = {
                    "call_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cost_usd": 0.0,
                }

            model_stats = summary["models"][model_key]
            model_stats["call_count"] += 1
            if success:
                model_stats["success_count"] += 1
            else:
                model_stats["error_count"] += 1
            model_stats["total_input_tokens"] += input_tokens
            model_stats["total_output_tokens"] += output_tokens
            model_stats["total_cost_usd"] = round(
                model_stats["total_cost_usd"] + cost_usd,
                6,
            )

            summary["last_updated"] = datetime.now(timezone.utc).isoformat()
            summary["total_calls"] = sum(m["call_count"] for m in summary["models"].values())
            summary["total_cost_usd"] = round(
                sum(m["total_cost_usd"] for m in summary["models"].values()),
                6,
            )

            with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

        except OSError as e:
            logger.error("Failed to update LLM summary: %s", e)

    @staticmethod
    def get_summary() -> dict[str, Any]:
        """Get current LLM usage summary."""
        if not SUMMARY_FILE.exists():
            return {
                "total_calls": 0,
                "total_cost_usd": 0.0,
                "models": {},
            }

        try:
            with open(SUMMARY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return {
                "total_calls": 0,
                "total_cost_usd": 0.0,
                "models": {},
            }

    @staticmethod
    def get_calls_by_stage(stage: str) -> list[dict[str, Any]]:
        """Get all LLM calls for a specific pipeline stage."""
        if not CALLS_LOG_FILE.exists():
            return []

        calls = []
        try:
            with open(CALLS_LOG_FILE, encoding="utf-8") as f:
                for line in f:
                    try:
                        call = json.loads(line.strip())
                        if call.get("stage") == stage:
                            calls.append(call)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return calls

    @staticmethod
    def get_calls_by_article(article_id: str) -> list[dict[str, Any]]:
        """Get all LLM calls for a specific article."""
        if not CALLS_LOG_FILE.exists():
            return []

        calls = []
        try:
            with open(CALLS_LOG_FILE, encoding="utf-8") as f:
                for line in f:
                    try:
                        call = json.loads(line.strip())
                        if call.get("article_id") == article_id:
                            calls.append(call)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return calls

    @staticmethod
    def export_audit_trail(
        limit: int = 100,
        stage: str | None = None,
        start_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Export audit trail of LLM calls for review.

        Args:
            limit: Maximum number of records to return
            stage: Filter by pipeline stage
            start_date: ISO format date to filter from (YYYY-MM-DD)

        Returns:
            List of call records
        """
        if not CALLS_LOG_FILE.exists():
            return []

        calls = []
        try:
            with open(CALLS_LOG_FILE, encoding="utf-8") as f:
                for line in f:
                    try:
                        call = json.loads(line.strip())
                        if stage and call.get("stage") != stage:
                            continue
                        if start_date and call.get("timestamp", "")[:10] < start_date:
                            continue
                        calls.append(call)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return sorted(
            calls,
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )[:limit]


# Global tracker instance
_tracker = LLMCallTracker()


def get_tracker() -> LLMCallTracker:
    """Get the global LLM call tracker."""
    return _tracker
