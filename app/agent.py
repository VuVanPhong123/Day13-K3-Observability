from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .logging_config import get_logger
from .pii import hash_user_id, summarize_text
from .prompt_management import resolve_prompt
from .tracing import (
    get_langfuse_client,
    observe,
    start_generation,
    start_span,
    tracing_enabled,
)


log = get_logger()


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    trace_id: str | None = None


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="agent_execution", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str | None = None,
    ) -> AgentResult:
        started = time.perf_counter()
        langfuse_client = get_langfuse_client()
        user_id_hash = hash_user_id(user_id)
        env = os.getenv("APP_ENV", "dev")
        trace_id: str | None = None

        with start_span(
            langfuse_client,
            name="retrieval",
            input={"query_preview": summarize_text(message)},
            metadata={
                "feature": feature,
                "session_id": session_id,
                "correlation_id": correlation_id,
            },
        ) as retrieval_span:
            retrieval_started = time.perf_counter()
            docs = retrieve(message)
            retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)
            log.info(
                "retrieval_completed",
                service="agent",
                latency_ms=retrieval_latency_ms,
                tool_name="mock_rag",
                payload={"doc_count": len(docs)},
            )
            trace_id = getattr(retrieval_span, "trace_id", None) or trace_id
            if retrieval_span is not None and hasattr(retrieval_span, "update"):
                retrieval_span.update(
                    output={
                        "doc_count": len(docs),
                        "doc_previews": [summarize_text(doc) for doc in docs],
                    }
                )

        prompt_name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
        prompt_label = os.getenv("LANGFUSE_PROMPT_LABEL", "production")
        with start_span(
            langfuse_client,
            name="prompt_resolution",
            input={"prompt_name": prompt_name, "prompt_label": prompt_label},
            metadata={"feature": feature, "correlation_id": correlation_id},
        ) as prompt_span:
            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=tracing_enabled(),
            )
            trace_id = getattr(prompt_span, "trace_id", None) or trace_id
            if prompt_span is not None and hasattr(prompt_span, "update"):
                prompt_span.update(
                    output={
                        "prompt_name": prompt.name,
                        "prompt_label": prompt.label,
                        "prompt_version": prompt.version,
                        "prompt_source": prompt.source,
                    }
                )

        prompt_metadata = {
            "prompt_name": prompt.name,
            "prompt_label": prompt.label,
            "prompt_version": prompt.version,
            "prompt_source": prompt.source,
        }
        trace_metadata = {
            **prompt_metadata,
            "user_id_hash": user_id_hash,
            "session_id": session_id,
            "feature": feature,
            "model": self.model,
            "env": env,
            "correlation_id": correlation_id,
        }

        # The public adapter tests use a deliberately small fake client. Keep
        # its original prompt metadata contract while the installed Langfuse
        # v3 client receives the complete correlation context.
        metadata_for_client = (
            trace_metadata
            if callable(getattr(langfuse_client, "start_as_current_span", None))
            else prompt_metadata
        )
        langfuse_client.update_current_trace(
            user_id=user_id_hash,
            session_id=session_id,
            tags=["lab", feature, self.model],
            metadata=metadata_for_client,
        )

        generation_metadata = {
            **trace_metadata,
            "doc_count": len(docs),
            "prompt_fetch_error": prompt.fetch_error,
        }
        with start_generation(
            langfuse_client,
            name="llm_generation",
            model=self.model,
            input={"prompt_preview": summarize_text(prompt.text, max_len=160)},
            metadata=generation_metadata,
            prompt=prompt.managed_prompt,
        ) as generation_span:
            response = self.llm.generate(prompt.text)
            trace_id = getattr(generation_span, "trace_id", None) or trace_id
            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = self._estimate_cost(
                response.usage.input_tokens, response.usage.output_tokens
            )

            # Keep this update inside the generation context. In Langfuse v3 it
            # enriches the active generation rather than the parent agent span.
            langfuse_client.update_current_generation(
                model=self.model,
                input={"prompt_preview": summarize_text(prompt.text, max_len=160)},
                output={"answer_preview": summarize_text(response.text)},
                metadata=generation_metadata,
                usage_details={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                },
                cost_details={"total": cost_usd},
                prompt=prompt.managed_prompt,
            )

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
            trace_id=trace_id,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
