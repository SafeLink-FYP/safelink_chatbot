"""
Phase 3 — LLMService failover tests.

Provider clients are mocked. Real LLM calls are exercised separately
(integration smoke, gated on env keys) — see Phase 3 acceptance report.
The unit-level concern here is the failover semantics: Gemini → Groq on
exception/timeout, both fail → LLMUnavailable.
"""
import asyncio
import time

import pytest

from prompts.tool_specs import ALL_TOOLS
from services.llm_service import (
    ChatTurn,
    LLMResponse,
    LLMService,
    LLMUnavailable,
)


def _make_service(*, gemini_key="g", groq_key="r") -> LLMService:
    return LLMService(
        gemini_api_key=gemini_key,
        groq_api_key=groq_key,
        gemini_model="gemini-2.5-flash",
        groq_model="llama-3.3-70b-versatile",
        primary_timeout=2.0,
        fallback_timeout=2.0,
        temperature=0.3,
        max_tokens=200,
        max_tool_rounds=2,
        tools=ALL_TOOLS,
    )


# ─── Both providers fail → LLMUnavailable ─────────────────────────────────────
@pytest.mark.asyncio
async def test_both_providers_fail_raises_llm_unavailable(monkeypatch):
    svc = _make_service()

    async def boom_g(**kwargs):
        raise RuntimeError("gemini boom")

    async def boom_r(**kwargs):
        raise RuntimeError("groq boom")

    monkeypatch.setattr(svc, "_gemini_with_tools", boom_g)
    monkeypatch.setattr(svc, "_groq_with_tools", boom_r)

    with pytest.raises(LLMUnavailable):
        await svc.generate(
            user_message="hi",
            history=[],
            sources_block="(none)",
            province=None,
            intent="safety_advice",
        )


# ─── Gemini fails → Groq succeeds within budget ───────────────────────────────
@pytest.mark.asyncio
async def test_gemini_failure_falls_back_to_groq(monkeypatch):
    svc = _make_service()

    async def boom_g(**kwargs):
        raise RuntimeError("gemini timeout")

    async def ok_r(**kwargs):
        return LLMResponse(
            text="Groq says hello.",
            tool_calls=[],
            provider_used="groq",
            latency_ms=50,
            finish_reason="stop",
        )

    monkeypatch.setattr(svc, "_gemini_with_tools", boom_g)
    monkeypatch.setattr(svc, "_groq_with_tools", ok_r)

    start = time.time()
    out = await svc.generate(
        user_message="hi",
        history=[],
        sources_block="(none)",
        province="punjab",
        intent="safety_advice",
    )
    elapsed = time.time() - start
    assert out.provider_used == "groq"
    assert out.text == "Groq says hello."
    # The fallback path must not exceed the locked 15-second wall budget
    # (here we use 5s as a generous test cap because mocked calls return
    # instantly).
    assert elapsed < 5.0


# ─── Gemini succeeds — Groq isn't called ──────────────────────────────────────
@pytest.mark.asyncio
async def test_gemini_success_does_not_invoke_groq(monkeypatch):
    svc = _make_service()
    groq_calls = 0

    async def ok_g(**kwargs):
        return LLMResponse(
            text="Gemini replied.",
            provider_used="gemini",
            latency_ms=80,
            finish_reason="stop",
        )

    async def boom_r(**kwargs):
        nonlocal groq_calls
        groq_calls += 1
        raise RuntimeError("should not be called")

    monkeypatch.setattr(svc, "_gemini_with_tools", ok_g)
    monkeypatch.setattr(svc, "_groq_with_tools", boom_r)

    out = await svc.generate(
        user_message="hi",
        history=[],
        sources_block="(none)",
        province=None,
        intent="safety_advice",
    )
    assert out.provider_used == "gemini"
    assert groq_calls == 0


# ─── No keys configured → LLMUnavailable ──────────────────────────────────────
@pytest.mark.asyncio
async def test_no_keys_raises_llm_unavailable():
    svc = _make_service(gemini_key=None, groq_key=None)
    with pytest.raises(LLMUnavailable):
        await svc.generate(
            user_message="hi",
            history=[],
            sources_block="(none)",
            province=None,
            intent="safety_advice",
        )


# ─── Streaming yields chunks then done ────────────────────────────────────────
@pytest.mark.asyncio
async def test_generate_stream_yields_done_marker(monkeypatch):
    svc = _make_service()

    async def ok_g(**kwargs):
        return LLMResponse(
            text="Once upon a time. " * 10,
            provider_used="gemini",
            latency_ms=10,
            finish_reason="stop",
        )

    monkeypatch.setattr(svc, "_gemini_with_tools", ok_g)
    chunks = []
    async for ch in svc.generate_stream(
        user_message="tell me",
        history=[],
        sources_block="(none)",
        province=None,
        intent="safety_advice",
    ):
        chunks.append(ch)
    assert chunks
    assert chunks[-1].done is True
    # Concatenated deltas must reconstruct the original text.
    reconstructed = "".join(c.delta for c in chunks if not c.done)
    assert "Once upon a time" in reconstructed


# ─── format_sources_block ─────────────────────────────────────────────────────
def test_format_sources_block_handles_empty():
    from services.llm_service import format_sources_block

    assert "no relevant sources" in format_sources_block([]).lower()


def test_format_sources_block_truncates_content():
    from services.llm_service import format_sources_block

    class P:
        title = "T"
        content = "x" * 10_000
        source = "NDMA"

    block = format_sources_block([P()])
    assert "[Source 1 | NDMA | T]" in block
    # 1200-char content cap per source
    assert block.count("x") == 1200
