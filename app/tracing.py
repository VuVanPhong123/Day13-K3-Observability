from __future__ import annotations

from contextlib import contextmanager, nullcontext
import os
from typing import Any, Iterator

try:
    from langfuse import get_client, observe

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_trace(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

        def flush(self) -> None:
            return None

    def get_client():
        return _DummyClient()


def get_langfuse_client():
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


@contextmanager
def start_span(
    client: Any,
    *,
    name: str,
    input: Any = None,
    output: Any = None,
    metadata: Any = None,
) -> Iterator[Any | None]:
    """Start a child span when Langfuse is enabled, otherwise do nothing.

    Keeping the no-op path here makes the agent testable with lightweight fake
    clients and preserves the documented local fallback when Langfuse is down.
    """

    starter = getattr(client, "start_as_current_span", None)
    if not tracing_enabled() or not callable(starter):
        with nullcontext() as span:
            yield span
        return

    try:
        context = starter(
            name=name,
            input=input,
            output=output,
            metadata=metadata,
        )
    except Exception:
        # Observability must not make the lab API unavailable. The application
        # still records its structured local logs when a client cannot start.
        with nullcontext() as span:
            yield span
        return

    with context as span:
        yield span


@contextmanager
def start_generation(
    client: Any,
    *,
    name: str,
    model: str,
    input: Any = None,
    metadata: Any = None,
    prompt: Any = None,
) -> Iterator[Any | None]:
    """Start a Langfuse generation child span with a safe input preview."""

    starter = getattr(client, "start_as_current_generation", None)
    if not tracing_enabled() or not callable(starter):
        with nullcontext() as generation:
            yield generation
        return

    try:
        context = starter(
            name=name,
            model=model,
            input=input,
            metadata=metadata,
            prompt=prompt,
        )
    except Exception:
        with nullcontext() as generation:
            yield generation
        return

    with context as generation:
        yield generation


def flush() -> None:
    """Flush pending spans before short-lived scripts exit."""

    if not tracing_enabled():
        return
    try:
        client = get_langfuse_client()
        flush_client = getattr(client, "flush", None)
        if callable(flush_client):
            flush_client()
    except Exception:
        # Flush is best-effort; a transient telemetry failure must not mask the
        # result of the application or evidence script.
        return
