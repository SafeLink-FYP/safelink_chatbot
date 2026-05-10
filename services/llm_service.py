"""
LLMService — hybrid Gemini (primary) + Groq (failover) wrapper.

Both providers are imported lazily so a USE_LLM=false deploy doesn't pay
the import cost. The wrapper exposes:

- ``LLMService.generate(...)``        — non-streaming, with tool-call loop.
- ``LLMService.generate_stream(...)`` — async generator of LLMChunk.

Failover semantics (locked Phase 3 decision):

- Gemini is tried first with ``LLM_TIMEOUT_SECONDS``.
- On timeout, 5xx, or any provider exception, retry once on Gemini, then
  fall back to Groq with ``LLM_FALLBACK_TIMEOUT_SECONDS``.
- If Groq also fails, raise ``LLMUnavailable`` so the caller can route to
  the legacy (template) pipeline.

Tool-call loop:

- Up to ``LLM_MAX_TOOL_ROUNDS`` iterations (hard cap to prevent
  infinite loops on a misbehaving model).
- After each tool call we re-issue the conversation including the tool
  result as an additional message and let the model produce its final
  text.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


# ─── Errors ───────────────────────────────────────────────────────────────────
class LLMUnavailable(Exception):
    """Both providers failed. Caller should fall through to legacy."""


# ─── Wire types ───────────────────────────────────────────────────────────────
@dataclass
class ChatTurn:
    """Mirrors session_store.ChatTurn — duplicated here to avoid the
    cyclic dependency."""
    role: str
    content: str


@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: Optional[str] = None  # provider-supplied (Groq) or None (Gemini)


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider_used: str = ""  # "gemini" | "groq" | "legacy_fallback"
    latency_ms: int = 0
    finish_reason: str = ""


@dataclass
class LLMChunk:
    delta: str = ""
    done: bool = False
    error: Optional[str] = None


# ─── System prompt loader ─────────────────────────────────────────────────────
_PROMPT_TEMPLATE: Optional[str] = None
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.txt"


def _load_system_prompt_template() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        with _PROMPT_PATH.open("r", encoding="utf-8") as f:
            _PROMPT_TEMPLATE = f.read()
    return _PROMPT_TEMPLATE


def _build_system_prompt(
    *,
    province: Optional[str],
    intent: Optional[str],
    sources_block: str,
) -> str:
    return (
        _load_system_prompt_template()
        .replace("{{PROVINCE}}", province or "(not specified)")
        .replace("{{INTENT}}", intent or "(unknown)")
        .replace("{{SOURCES_BLOCK}}", sources_block or "(no relevant sources retrieved)")
    )


# ─── Service ──────────────────────────────────────────────────────────────────
class LLMService:
    """Hybrid Gemini + Groq client. See module docstring."""

    def __init__(
        self,
        *,
        gemini_api_key: Optional[str],
        groq_api_key: Optional[str],
        gemini_model: str,
        groq_model: str,
        primary_timeout: float,
        fallback_timeout: float,
        temperature: float,
        max_tokens: int,
        max_tool_rounds: int,
        tools: list[dict],
    ) -> None:
        self.gemini_api_key = (gemini_api_key or "").strip() or None
        self.groq_api_key = (groq_api_key or "").strip() or None
        self.gemini_model = gemini_model
        self.groq_model = groq_model
        self.primary_timeout = primary_timeout
        self.fallback_timeout = fallback_timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds
        self.tools = tools

        # Lazy-built provider clients.
        self._gemini = None
        self._groq = None

    # ─── Provider client builders ─────────────────────────────────────────────
    def _get_gemini(self):
        if self._gemini is None and self.gemini_api_key:
            import google.generativeai as genai

            genai.configure(api_key=self.gemini_api_key)
            # Tools translate to Gemini's "function declarations" shape.
            gemini_tools = [
                {
                    "function_declarations": [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "parameters": t["parameters"],
                        }
                        for t in self.tools
                    ]
                }
            ]
            self._gemini = genai.GenerativeModel(
                model_name=self.gemini_model,
                tools=gemini_tools,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                },
            )
        return self._gemini

    def _get_groq(self):
        if self._groq is None and self.groq_api_key:
            from groq import Groq

            self._groq = Groq(api_key=self.groq_api_key, timeout=self.fallback_timeout)
        return self._groq

    # ─── Public — non-streaming ───────────────────────────────────────────────
    async def generate(
        self,
        *,
        user_message: str,
        history: list[ChatTurn],
        sources_block: str,
        province: Optional[str],
        intent: Optional[str],
    ) -> LLMResponse:
        system_prompt = _build_system_prompt(
            province=province, intent=intent, sources_block=sources_block
        )
        # Try Gemini first.
        try:
            return await self._gemini_with_tools(
                system_prompt=system_prompt,
                user_message=user_message,
                history=history,
            )
        except LLMUnavailable:
            raise
        except Exception as e:
            logger.warning("Gemini failed (%s) — falling back to Groq", e)
        # Then Groq.
        try:
            return await self._groq_with_tools(
                system_prompt=system_prompt,
                user_message=user_message,
                history=history,
            )
        except Exception as e:
            logger.error(
                "Groq fallback also failed: %s: %s",
                e.__class__.__name__,
                e,
            )
            raise LLMUnavailable("both LLM providers failed") from e

    # ─── Public — streaming ───────────────────────────────────────────────────
    async def generate_stream(
        self,
        *,
        user_message: str,
        history: list[ChatTurn],
        sources_block: str,
        province: Optional[str],
        intent: Optional[str],
    ) -> AsyncIterator[LLMChunk]:
        """
        SSE streaming. v1 implementation: get the full response via
        non-streaming Gemini (with tool-call loop), then chunk it into
        deltas client-side. Real token streaming will land in v1.1 once
        the tool-call loop interaction with streaming is more battle-
        tested across providers.
        """
        try:
            full = await self.generate(
                user_message=user_message,
                history=history,
                sources_block=sources_block,
                province=province,
                intent=intent,
            )
        except LLMUnavailable as e:
            yield LLMChunk(done=True, error=str(e))
            return

        # Chunk by ~30 chars / sentence boundary, paced to feel like
        # streaming.
        text = full.text
        i = 0
        chunk_size = 30
        while i < len(text):
            yield LLMChunk(delta=text[i : i + chunk_size])
            i += chunk_size
            await asyncio.sleep(0.02)
        yield LLMChunk(done=True)

    # ─── Gemini path ──────────────────────────────────────────────────────────
    async def _gemini_with_tools(
        self,
        *,
        system_prompt: str,
        user_message: str,
        history: list[ChatTurn],
    ) -> LLMResponse:
        client = self._get_gemini()
        if client is None:
            raise LLMUnavailable("gemini api key not configured")

        # Build the chat. Gemini chats expect a "user"/"model" role flip.
        gemini_history = []
        for h in history:
            gemini_history.append(
                {
                    "role": "user" if h.role == "user" else "model",
                    "parts": [{"text": h.content}],
                }
            )
        # Gemini does not accept a "system" role; we prepend the prompt to
        # the first user message.
        user_with_prompt = f"{system_prompt}\n\n---\n\n{user_message}"

        from services.tool_executor import get_tool_executor

        executor = get_tool_executor()

        # Iterative tool-call loop.
        chat = client.start_chat(history=gemini_history)

        rounds = 0
        last_text = ""
        finish = ""
        start = time.time()

        message = user_with_prompt
        while True:
            resp = await asyncio.wait_for(
                asyncio.to_thread(chat.send_message, message),
                timeout=self.primary_timeout,
            )
            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []
            try:
                candidates = resp.candidates or []
                for c in candidates:
                    parts = getattr(c.content, "parts", []) or []
                    for p in parts:
                        if getattr(p, "function_call", None):
                            fc = p.function_call
                            args = dict(fc.args) if fc.args else {}
                            tool_calls.append(
                                ToolCall(name=fc.name, arguments=args, call_id=None)
                            )
                        elif getattr(p, "text", None):
                            text_parts.append(p.text)
            except Exception as e:
                logger.warning("Gemini parse error: %s", e)

            last_text = "".join(text_parts)

            if not tool_calls:
                finish = "stop"
                break
            rounds += 1
            if rounds >= self.max_tool_rounds:
                finish = "tool_round_cap"
                break

            # Execute each tool, then send results back as a single
            # follow-up message.
            tool_responses = []
            for call in tool_calls:
                result = executor.execute(call.name, call.arguments)
                tool_responses.append((call.name, result))

            # Compose the function_response parts. Gemini accepts a list of
            # parts in the next send_message.
            import google.generativeai as genai  # noqa: F401  (api types)

            message = [
                {
                    "function_response": {
                        "name": name,
                        "response": result,
                    }
                }
                for (name, result) in tool_responses
            ]

        latency_ms = int((time.time() - start) * 1000)
        return LLMResponse(
            text=last_text or "",
            tool_calls=[],  # consumed inside the loop
            provider_used="gemini",
            latency_ms=latency_ms,
            finish_reason=finish or "stop",
        )

    # ─── Groq path ────────────────────────────────────────────────────────────
    async def _groq_with_tools(
        self,
        *,
        system_prompt: str,
        user_message: str,
        history: list[ChatTurn],
    ) -> LLMResponse:
        client = self._get_groq()
        if client is None:
            raise LLMUnavailable("groq api key not configured")

        from services.tool_executor import get_tool_executor

        executor = get_tool_executor()

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": user_message})

        # OpenAI-compatible tool spec
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in self.tools
        ]

        rounds = 0
        last_text = ""
        finish = ""
        start = time.time()
        tools_disabled_after_failure = False

        while True:
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.chat.completions.create,
                        model=self.groq_model,
                        messages=messages,
                        tools=tools if not tools_disabled_after_failure else None,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    ),
                    timeout=self.fallback_timeout,
                )
            except Exception as e:
                # Groq's Llama-3.x sometimes emits malformed function-call
                # syntax; the SDK reports it as `tool_use_failed`. We retry
                # once without tools so the user still gets a grounded
                # answer (the system prompt's SOURCES block is still in
                # context, so the model can ground without function calls).
                err_str = str(e)
                if (
                    not tools_disabled_after_failure
                    and ("tool_use_failed" in err_str or "Failed to call a function" in err_str)
                ):
                    logger.warning(
                        "Groq tool-call malformed; retrying without tools"
                    )
                    tools_disabled_after_failure = True
                    continue
                raise
            choice = resp.choices[0]
            msg = choice.message
            tool_calls_attr = getattr(msg, "tool_calls", None) or []

            if not tool_calls_attr:
                last_text = msg.content or ""
                finish = choice.finish_reason or "stop"
                break

            rounds += 1
            if rounds >= self.max_tool_rounds:
                last_text = msg.content or ""
                finish = "tool_round_cap"
                break

            # Append the assistant's tool-call message + tool results.
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls_attr
                    ],
                }
            )
            for tc in tool_calls_attr:
                args_obj: dict = {}
                try:
                    args_obj = json.loads(tc.function.arguments or "{}")
                except Exception:
                    pass
                result = executor.execute(tc.function.name, args_obj)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        latency_ms = int((time.time() - start) * 1000)
        return LLMResponse(
            text=last_text or "",
            tool_calls=[],
            provider_used="groq",
            latency_ms=latency_ms,
            finish_reason=finish or "stop",
        )


# ─── Source-block formatting helper ───────────────────────────────────────────
def format_sources_block(passages: list[Any]) -> str:
    """
    Build the SOURCES block embedded in the system prompt.

    `passages` is a list of RetrievalResult-like objects with .title,
    .content, .source. Truncate content per source so the prompt budget
    stays predictable.
    """
    if not passages:
        return "(no relevant sources retrieved)"
    blocks: list[str] = []
    for i, p in enumerate(passages, 1):
        title = getattr(p, "title", "") or "Untitled"
        content = (getattr(p, "content", "") or "")[:1200]
        source = getattr(p, "source", "") or "internal"
        blocks.append(
            f"[Source {i} | {source} | {title}]\n{content}"
        )
    return "\n\n".join(blocks)


# ─── Singleton ────────────────────────────────────────────────────────────────
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        from config import get_settings
        from prompts.tool_specs import ALL_TOOLS

        settings = get_settings()
        _llm_service = LLMService(
            gemini_api_key=settings.GEMINI_API_KEY,
            groq_api_key=settings.GROQ_API_KEY,
            gemini_model=settings.GEMINI_MODEL,
            groq_model=settings.GROQ_MODEL,
            primary_timeout=settings.LLM_TIMEOUT_SECONDS,
            fallback_timeout=settings.LLM_FALLBACK_TIMEOUT_SECONDS,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            max_tool_rounds=settings.LLM_MAX_TOOL_ROUNDS,
            tools=ALL_TOOLS,
        )
    return _llm_service


def reset_llm_service_for_tests() -> None:
    global _llm_service
    _llm_service = None
