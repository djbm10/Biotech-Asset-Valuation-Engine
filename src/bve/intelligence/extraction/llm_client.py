"""
LLM client abstractions for the signal extraction pipeline.

``LLMClient`` is a ``Protocol`` so any conforming object can be injected.
Two concrete backends are provided (``OpenAIClient``, ``AnthropicClient``);
both use optional dependencies so the core library remains importable without
either installed.

``FakeLLMClient`` is a deterministic test double that does not call any API.
It maps prompt substrings to canned JSON strings, enabling full unit-test
coverage of the extraction pipeline without network access.

Exception hierarchy
-------------------
All concrete clients translate backend errors into the three subclasses of
``LLMClientError``.  ``SignalExtractor`` catches these; they are never
propagated to callers.
"""
from __future__ import annotations

import time
from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------

class LLMResponse:
    """Normalized response from any LLM backend."""

    __slots__ = ("content", "model", "latency_ms", "tokens_used")

    def __init__(
        self,
        content: str,
        model: str,
        latency_ms: int,
        tokens_used: Optional[int] = None,
    ) -> None:
        self.content    = content
        self.model      = model
        self.latency_ms = latency_ms
        self.tokens_used = tokens_used

    def __repr__(self) -> str:
        return (
            f"LLMResponse(model={self.model!r}, latency_ms={self.latency_ms}, "
            f"content_len={len(self.content)})"
        )


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class LLMClientError(Exception):
    """Base for all LLM API errors."""


class LLMRateLimitError(LLMClientError):
    """HTTP 429 or equivalent from the LLM provider."""


class LLMRefusalError(LLMClientError):
    """Model refused to answer (content policy, safety filter)."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClient(Protocol):
    """
    Structural protocol for LLM text completion backends.

    Any class with a ``complete()`` method and ``model_id`` property
    satisfies this protocol — no inheritance required.  This design
    allows ``FakeLLMClient`` in tests to avoid importing production
    client classes entirely.
    """

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Issue one completion and return a normalized response.

        Parameters
        ----------
        system_prompt:
            Invariant system instruction (role, output format constraints).
        user_prompt:
            Per-document user message containing the document text + schema.
        temperature:
            Sampling temperature; 0.0 for deterministic / analytical tasks.
        max_tokens:
            Maximum tokens in the response.

        Raises
        ------
        LLMRateLimitError
            When the API returns HTTP 429 or an equivalent signal.
        LLMRefusalError
            When the model refuses the request (content policy).
        LLMClientError
            For all other API-level failures.
        """
        ...

    @property
    def model_id(self) -> str:
        """Model identifier string stored in ``ExtractionResult.extraction_model``."""
        ...


# ---------------------------------------------------------------------------
# Concrete: Anthropic
# ---------------------------------------------------------------------------

class AnthropicClient:
    """
    Anthropic Messages API backend.

    Requires ``anthropic>=0.25`` (optional dependency).
    Falls back to ``ANTHROPIC_API_KEY`` env var when ``api_key`` is ``None``.

    Parameters
    ----------
    model:
        Model identifier.  Defaults to ``"claude-sonnet-4-6"``.
    api_key:
        Explicit API key; ``None`` reads from environment.
    timeout:
        Per-request timeout in seconds.
    max_retries:
        Number of retries on transient errors (not rate limits).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        self._model       = model
        self._api_key     = api_key
        self._timeout     = timeout
        self._max_retries = max_retries
        self._client      = None

    @property
    def model_id(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic  # optional dependency
            except ImportError as exc:
                raise ImportError(
                    "anthropic package is required for AnthropicClient. "
                    "Install with: pip install 'bve[extract]'"
                ) from exc
            kwargs: dict = {"max_retries": self._max_retries, "timeout": float(self._timeout)}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required for AnthropicClient."
            ) from exc

        client = self._get_client()
        t0 = time.monotonic()
        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            content = response.content[0].text if response.content else ""
            tokens_used = (
                (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
                if response.usage else None
            )
            return LLMResponse(
                content=content,
                model=self._model,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
            )
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except anthropic.APIError as exc:
            raise LLMClientError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Concrete: OpenAI
# ---------------------------------------------------------------------------

class OpenAIClient:
    """
    OpenAI chat completions backend.

    Requires ``openai>=1.30`` (optional dependency).
    Falls back to ``OPENAI_API_KEY`` env var when ``api_key`` is ``None``.

    Parameters
    ----------
    model:
        Model identifier.  Defaults to ``"gpt-4o-2024-11-20"``.
    api_key:
        Explicit API key; ``None`` reads from environment.
    timeout:
        Per-request timeout in seconds.
    max_retries:
        Number of retries on transient errors.
    """

    def __init__(
        self,
        model: str = "gpt-4o-2024-11-20",
        api_key: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        self._model       = model
        self._api_key     = api_key
        self._timeout     = timeout
        self._max_retries = max_retries
        self._client      = None

    @property
    def model_id(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None:
            try:
                import openai  # optional dependency
            except ImportError as exc:
                raise ImportError(
                    "openai package is required for OpenAIClient. "
                    "Install with: pip install 'bve[extract]'"
                ) from exc
            kwargs: dict = {"max_retries": self._max_retries, "timeout": float(self._timeout)}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAIClient."
            ) from exc

        client = self._get_client()
        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            choice  = response.choices[0] if response.choices else None
            content = choice.message.content or "" if choice else ""
            tokens_used = (
                response.usage.total_tokens if response.usage else None
            )
            return LLMResponse(
                content=content,
                model=self._model,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except openai.APIError as exc:
            raise LLMClientError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------

class FakeLLMClient:
    """
    Deterministic LLM test double.

    Maps substrings of the *combined* ``system_prompt + user_prompt`` to
    canned JSON strings.  When no key matches, returns ``default_response``.

    Does not require ``openai`` or ``anthropic`` packages.

    Parameters
    ----------
    responses:
        ``{substring: json_string}`` mapping.  Keys are lowercased before
        matching; the combined prompt is also lowercased for comparison.
    default_response:
        Returned when no key in ``responses`` matches.  Defaults to ``"{}"``.
    model:
        Model identifier string for ``ExtractionResult.extraction_model``.
    latency_ms:
        Simulated latency in milliseconds (default: 0).
    """

    def __init__(
        self,
        responses: Optional[dict[str, str]] = None,
        default_response: str = "{}",
        model: str = "fake-llm",
        latency_ms: int = 0,
    ) -> None:
        self._responses       = {k.lower(): v for k, v in (responses or {}).items()}
        self._default         = default_response
        self._model           = model
        self._latency_ms      = latency_ms
        self.call_count: int  = 0
        self.last_system: str = ""
        self.last_user:   str = ""

    @property
    def model_id(self) -> str:
        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self.call_count  += 1
        self.last_system  = system_prompt
        self.last_user    = user_prompt

        combined = (system_prompt + user_prompt).lower()
        for key, response in self._responses.items():
            if key in combined:
                return LLMResponse(
                    content=self._latency_ms and response or response,
                    model=self._model,
                    latency_ms=self._latency_ms,
                )
        return LLMResponse(
            content=self._default,
            model=self._model,
            latency_ms=self._latency_ms,
        )
