"""LiteLLM integration compatibility patches."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, Optional

try:
    from litellm.litellm_core_utils.logging_worker import LoggingWorker
except ImportError:  # pragma: no cover - LiteLLM is an optional dependency
    LoggingWorker = None  # type: ignore[assignment]

try:  # pragma: no cover - defensive import
    from dspy.clients import base_lm as _base_lm
except Exception:  # pragma: no cover - DSPy optional or import failure
    _base_lm = None


def _is_loop_closed(loop: Optional[asyncio.AbstractEventLoop]) -> bool:
    """Best-effort check to see if an event loop is closed."""
    if loop is None:
        return True
    try:
        return loop.is_closed()
    except Exception:
        return True


def patch_litellm_logging_worker() -> None:
    """
    Monkey-patch LiteLLM's LoggingWorker to tolerate new event loops.

    LiteLLM keeps a global LoggingWorker instance whose queue is bound to the
    event loop that first initializes it. When ROMA spins up new event loops
    (e.g., GEPA threads invoking asyncio.run), the original queue raises
    `RuntimeError: <Queue> is bound to a different event loop`.

    The patched start() detects when the queue belongs to a different or closed
    loop, cancels the stale worker task, and forces the queue to be recreated
    on the current loop before delegating to the original start().
    """
    if LoggingWorker is None:
        return

    if getattr(LoggingWorker, "_roma_patch_applied", False):
        return

    original_start = LoggingWorker.start

    def patched_start(self: LoggingWorker) -> None:  # type: ignore[override]
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (shouldn't happen for async workflows); fall back
            return original_start(self)

        queue = getattr(self, "_queue", None)
        if queue is not None:
            queue_loop = getattr(queue, "_loop", None)
            if queue_loop is not current_loop or _is_loop_closed(queue_loop):
                worker_task = getattr(self, "_worker_task", None)
                if worker_task is not None and not worker_task.done():
                    try:
                        worker_task.cancel()
                    except Exception:
                        pass
                self._worker_task = None
                self._queue = None

        return original_start(self)

    LoggingWorker.start = patched_start  # type: ignore[assignment]
    LoggingWorker._roma_patch_applied = True  # type: ignore[attr-defined]


def _coerce_content_text(content_item: Any) -> str:
    """Normalize Response API content fragments into strings."""
    if content_item is None:
        return ""
    if isinstance(content_item, str):
        return content_item
    if isinstance(content_item, dict):
        text = content_item.get("text")
        if text is not None:
            return str(text)
        return str(content_item)
    return str(content_item)


def _process_response_dict_fallback(response: Any) -> list[dict[str, Any]]:
    """
    Replicate DSPy's Response API parsing for providers that return plain dicts.

    LiteLLM 1.78.x can return dictionaries instead of OpenAI Response objects
    for the Responses API. DSPy 3.0.4 expects Pydantic types with attributes,
    so we reconstruct the minimal data structure DSPy needs.
    """
    output_items: Iterable[Any] = getattr(response, "output", []) or []

    text_outputs: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    reasoning_contents: list[str] = []

    for item in output_items:
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        if item_type is None and "text" in item and "content" not in item:
            item_type = "message"

        if item_type == "message":
            content = item.get("content")
            if content is None and "text" in item:
                content = [{"text": item.get("text")}]

            if isinstance(content, list):
                for sub in content:
                    text = _coerce_content_text(sub)
                    if text:
                        text_outputs.append(text)
            else:
                text = _coerce_content_text(content)
                if text:
                    text_outputs.append(text)

        elif item_type == "function_call":
            tool_calls.append(item)

        elif item_type == "reasoning":
            content = item.get("content")
            if isinstance(content, list):
                for sub in content:
                    text = _coerce_content_text(sub)
                    if text:
                        reasoning_contents.append(text)
            else:
                text = _coerce_content_text(content)
                if text:
                    reasoning_contents.append(text)

        else:
            # Fallback: treat as plain text blob if present
            text = item.get("text")
            if text:
                text_outputs.append(str(text))

    result: dict[str, Any] = {}
    if text_outputs:
        result["text"] = "".join(text_outputs)
    if tool_calls:
        result["tool_calls"] = tool_calls
    if reasoning_contents:
        result["reasoning_content"] = "".join(reasoning_contents)

    return [result] if result else []


def patch_dspy_responses_dict_support() -> None:
    """
    Patch DSPy's BaseLM._process_response to tolerate LiteLLM dict outputs.

    Without this guard, DSPy raises AttributeError because plain dicts do not
    expose the `.type` attribute expected from OpenAI Response API objects.
    """
    if _base_lm is None:  # pragma: no cover - DSPy not installed
        return

    BaseLM = getattr(_base_lm, "BaseLM", None)
    if BaseLM is None:
        return

    if getattr(BaseLM, "_roma_dict_patch_applied", False):
        return

    original_process_response = BaseLM._process_response

    def patched_process_response(self, response: Any):  # type: ignore[override]
        try:
            return original_process_response(self, response)
        except AttributeError as exc:
            # Only fall back when the failure is caused by missing `.type`
            if "'dict' object has no attribute 'type'" not in str(exc):
                raise
            return _process_response_dict_fallback(response)

    BaseLM._process_response = patched_process_response  # type: ignore[assignment]
    BaseLM._roma_dict_patch_applied = True  # type: ignore[attr-defined]


__all__ = [
    "patch_litellm_logging_worker",
    "patch_dspy_responses_dict_support",
]
