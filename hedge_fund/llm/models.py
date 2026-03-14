"""Multi-provider LLM factory and structured-output call helper.

Supports: OpenAI, Anthropic, Google (Gemini), Groq, DeepSeek, and Ollama.

Usage::

    from hedge_fund.llm.models import get_llm, call_llm
    from hedge_fund.data.models import AnalystSignal

    # Direct LangChain chat model
    llm = get_llm(provider="openai", model="gpt-4.1")
    response = llm.invoke([{"role": "user", "content": "Hello"}])

    # Structured output with retry
    signal = call_llm(
        prompt="Analyse AAPL fundamentals ...",
        response_model=AnalystSignal,
        agent_name="fundamentals_analyst",
    )
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional, Type, TypeVar, overload

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from hedge_fund.config import LLMProvider, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Number of retries for structured-output calls before giving up.
_MAX_RETRIES = 3
# Base sleep between retries (seconds).
_RETRY_BACKOFF = 1.0


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def get_llm(
    provider: Optional[str | LLMProvider] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create and return a LangChain chat model for the requested provider.

    When arguments are ``None`` the values from :func:`~hedge_fund.config.get_settings`
    are used as defaults.

    Args:
        provider: LLM provider name (e.g. ``"openai"``, ``"anthropic"``).
        model: Model identifier (e.g. ``"gpt-4.1"``, ``"claude-sonnet-4-20250514"``).
        temperature: Sampling temperature.
        **kwargs: Extra keyword arguments forwarded to the LangChain constructor.

    Returns:
        A :class:`BaseChatModel` instance ready for ``.invoke()`` / ``.ainvoke()``.

    Raises:
        ValueError: If the provider is not recognised.
    """
    settings = get_settings()

    # Resolve provider enum.
    if provider is None:
        prov = settings.llm_provider
    elif isinstance(provider, str):
        prov = LLMProvider(provider.strip().lower())
    else:
        prov = provider

    resolved_model = model or settings.resolved_model
    temp = temperature if temperature is not None else settings.llm_temperature
    api_key = settings.get_api_key_for_provider(prov)

    if prov == LLMProvider.OPENAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=resolved_model,
            temperature=temp,
            api_key=api_key,  # type: ignore[arg-type]
            **kwargs,
        )

    if prov == LLMProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=resolved_model,  # type: ignore[arg-type]
            temperature=temp,
            api_key=api_key,  # type: ignore[arg-type]
            **kwargs,
        )

    if prov == LLMProvider.GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=resolved_model,
            temperature=temp,
            google_api_key=api_key,  # type: ignore[arg-type]
            **kwargs,
        )

    if prov == LLMProvider.GROQ:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=resolved_model,
            temperature=temp,
            api_key=api_key,  # type: ignore[arg-type]
            base_url="https://api.groq.com/openai/v1",
            **kwargs,
        )

    if prov == LLMProvider.DEEPSEEK:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=resolved_model,
            temperature=temp,
            api_key=api_key,  # type: ignore[arg-type]
            base_url="https://api.deepseek.com/v1",
            **kwargs,
        )

    if prov == LLMProvider.OLLAMA:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=resolved_model,
            temperature=temp,
            api_key="ollama",  # type: ignore[arg-type]
            base_url="http://localhost:11434/v1",
            **kwargs,
        )

    raise ValueError(f"Unsupported LLM provider: {prov!r}")


# ---------------------------------------------------------------------------
# Structured output caller
# ---------------------------------------------------------------------------


@overload
def call_llm(
    prompt: str,
    *,
    response_model: Type[T],
    system_message: str = ...,
    agent_name: str = ...,
    provider: Optional[str | LLMProvider] = ...,
    model: Optional[str] = ...,
    temperature: Optional[float] = ...,
    llm: Optional[BaseChatModel] = ...,
) -> T: ...


@overload
def call_llm(
    prompt: str,
    *,
    response_model: None = ...,
    system_message: str = ...,
    agent_name: str = ...,
    provider: Optional[str | LLMProvider] = ...,
    model: Optional[str] = ...,
    temperature: Optional[float] = ...,
    llm: Optional[BaseChatModel] = ...,
) -> str: ...


def call_llm(
    prompt: str,
    *,
    response_model: Optional[Type[T]] = None,
    system_message: str = "",
    agent_name: str = "unknown",
    provider: Optional[str | LLMProvider] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    llm: Optional[BaseChatModel] = None,
) -> T | str:
    """Invoke an LLM with optional structured-output parsing and retry logic.

    This is the primary high-level function used by agent nodes to call any
    supported LLM.  When *response_model* is provided the function:

    1. Attempts ``with_structured_output`` (native tool-call / JSON mode).
    2. On failure, tries to extract JSON from markdown code blocks in the
       raw text response and parse it through the Pydantic model.
    3. After ``_MAX_RETRIES`` total failures, returns a *default neutral
       signal* (only when the response model is :class:`AnalystSignal`).

    Args:
        prompt: The user / main prompt text.
        response_model: Pydantic model class for structured output.  When
            ``None`` the raw text response is returned.
        system_message: Optional system prompt.
        agent_name: Name of the calling agent (for logging / signal tagging).
        provider: Override the default LLM provider.
        model: Override the default model.
        temperature: Override the default temperature.
        llm: Supply a pre-built LangChain chat model.  When provided,
            *provider*, *model*, and *temperature* are ignored.

    Returns:
        An instance of *response_model* or a plain string.

    Raises:
        RuntimeError: If all retries are exhausted and no default is available.
    """
    if llm is None:
        llm = get_llm(provider=provider, model=model, temperature=temperature)

    messages: list[dict[str, str]] = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    # ------------------------------------------------------------------
    # Plain text call (no structured output)
    # ------------------------------------------------------------------
    if response_model is None:
        try:
            result = llm.invoke(messages)
            return str(result.content)
        except Exception:
            logger.exception("[%s] LLM plain-text call failed", agent_name)
            raise

    # ------------------------------------------------------------------
    # Structured output with retry
    # ------------------------------------------------------------------
    last_exc: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            # --- Attempt 1: native structured output -----------------
            structured_llm = llm.with_structured_output(response_model)
            result = structured_llm.invoke(messages)
            if isinstance(result, response_model):
                return result
            # Some providers return a dict instead of the model instance.
            if isinstance(result, dict):
                return response_model.model_validate(result)

        except Exception as exc:
            logger.warning(
                "[%s] Structured output attempt %d/%d failed: %s",
                agent_name,
                attempt,
                _MAX_RETRIES,
                exc,
            )
            last_exc = exc

            # --- Attempt 2: fallback JSON extraction -----------------
            try:
                raw_result = llm.invoke(messages)
                raw_text = str(raw_result.content)
                parsed = _extract_json_from_text(raw_text)
                if parsed is not None:
                    return response_model.model_validate(parsed)
            except Exception as fallback_exc:
                logger.warning(
                    "[%s] Fallback JSON extraction attempt %d/%d failed: %s",
                    agent_name,
                    attempt,
                    _MAX_RETRIES,
                    fallback_exc,
                )
                last_exc = fallback_exc

            if attempt < _MAX_RETRIES:
                sleep_time = _RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.info("[%s] Sleeping %.1fs before retry", agent_name, sleep_time)
                time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # All retries exhausted -- return a safe default if possible
    # ------------------------------------------------------------------
    default = _make_default_signal(response_model, agent_name)
    if default is not None:
        logger.error(
            "[%s] All %d structured-output attempts failed; returning default neutral signal",
            agent_name,
            _MAX_RETRIES,
        )
        return default

    raise RuntimeError(
        f"[{agent_name}] All {_MAX_RETRIES} LLM structured-output attempts failed"
    ) from last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json_from_text(text: str) -> Optional[dict[str, Any]]:
    """Try to extract a JSON object from markdown code blocks or raw text.

    Looks for ````` ```json ... ``` ````` or ````` ``` ... ``` ````` fences first,
    then falls back to finding the outermost ``{...}`` substring.

    Returns:
        A parsed dictionary, or ``None`` if no valid JSON is found.
    """
    # Try fenced code blocks first.
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
    for match in fence_pattern.finditer(text):
        try:
            return json.loads(match.group(1))  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            continue

    # Fallback: find outermost { ... } pair.
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    return None


def _make_default_signal(
    response_model: Type[Any],
    agent_name: str,
) -> Any | None:
    """Return a safe neutral default if *response_model* is AnalystSignal.

    For all other model types there is no sensible default so ``None`` is
    returned, causing the caller to raise.
    """
    # Import here to avoid circular dependency.
    from hedge_fund.data.models import AnalystSignal

    if response_model is AnalystSignal:
        return AnalystSignal(
            signal="neutral",
            confidence=0.0,
            reasoning={"error": "LLM call failed after all retries"},
            agent_name=agent_name,
        )
    return None
