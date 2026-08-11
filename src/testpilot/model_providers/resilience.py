from __future__ import annotations

import time
from threading import Event
from typing import Callable, TypeVar


T = TypeVar("T")


class AIRequestCancelled(RuntimeError):
    """Raised when the user explicitly cancels an AI generation."""


def is_retryable(error: Exception) -> bool:
    text = str(error).lower()
    non_retryable = (
        "not logged in", "unauthorized", "forbidden", "invalid model",
        "model_not_found", "authentication", "401", "403", "404",
    )
    return not any(marker in text for marker in non_retryable)


def run_with_retry(
    operation: Callable[[int], T], retries: int, cancel_event: Event | None = None,
    delay: float = 1.0,
) -> T:
    last_error: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        if cancel_event and cancel_event.is_set():
            raise AIRequestCancelled("AI 请求已取消。")
        try:
            return operation(attempt + 1)
        except AIRequestCancelled:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= retries or not is_retryable(exc):
                raise
            deadline = time.monotonic() + delay * (2 ** attempt)
            while time.monotonic() < deadline:
                if cancel_event and cancel_event.wait(min(0.1, deadline - time.monotonic())):
                    raise AIRequestCancelled("AI 请求已取消。")
                if not cancel_event:
                    time.sleep(min(0.1, deadline - time.monotonic()))
    raise last_error or RuntimeError("AI 请求失败。")
