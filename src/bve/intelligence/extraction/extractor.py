"""
SignalExtractor — orchestrator for the raw-document → StructuredSignal pipeline.

``SignalExtractor.extract()`` is the primary entry point.  It coordinates
``PromptBuilder``, the injected ``LLMClient``, and ``ExtractionValidator`` in
that order and returns an ``ExtractionResult`` regardless of outcome.

Isolation guarantee
-------------------
This module has ZERO imports from:
  - ``bve.intelligence.mapping``      (no rules_for, auto_rules)
  - ``bve.intelligence.schemas.proposals``  (no AssumptionChangeProposal)
  - ``bve.intelligence.schemas.runs``       (no ValuationRun)
  - ``bve.valuation.*`` or ``bve.models.*`` (no engine calls)

Phase 1 ends at a validated ``StructuredSignal``.  Mapping and revaluation
are Phase 2 responsibilities.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from bve.intelligence.extraction.llm_client import (
    LLMClient,
    LLMClientError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMResponse,
)
from bve.intelligence.extraction.prompt_builder import PromptBuilder
from bve.intelligence.extraction.raw_document import RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.extraction.validation import ExtractionValidator


class SignalExtractor:
    """
    Orchestrates the full extraction pipeline for a single ``RawDocument``.

    Parameters
    ----------
    llm_client:
        Any object satisfying the ``LLMClient`` protocol.  In production,
        use ``AnthropicClient`` or ``OpenAIClient``; in tests, inject a
        ``FakeLLMClient``.
    prompt_version:
        Version tag recorded in every ``ExtractionResult``.  Defaults to
        ``PromptBuilder.CURRENT_VERSION``.

    Usage
    -----
    >>> extractor = SignalExtractor(llm_client=AnthropicClient())
    >>> result = extractor.extract(document, event_id="evt-001")
    >>> if result.status == ExtractionStatus.SUCCESS:
    ...     print(result.signal.event_type)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_version: Optional[str] = None,
    ) -> None:
        self._llm       = llm_client
        self._builder   = PromptBuilder()
        self._validator = ExtractionValidator()
        self._version   = prompt_version or PromptBuilder.CURRENT_VERSION

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        document: RawDocument,
        event_id: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Run the full extraction pipeline for one document.

        This method never raises.  All failure modes return an
        ``ExtractionResult`` with a non-SUCCESS status and the raw LLM
        response preserved for debugging.

        Parameters
        ----------
        document:
            Normalized source document from any ``SourceConnector``.
        event_id:
            FK → ``Event.id`` embedded in the resulting ``StructuredSignal``.
            When ``None``, a new UUIDv4 is generated as a placeholder.

        Returns
        -------
        ExtractionResult
            Status-tagged result; ``signal`` is set only on ``SUCCESS``.
        """
        if event_id is None:
            event_id = str(uuid.uuid4())

        extracted_at = datetime.now(timezone.utc)

        # Step 1: Build prompts
        system_prompt = self._builder.build_system_prompt()
        user_prompt   = self._builder.build_user_prompt(document)

        # Step 2: Call LLM
        llm_response, status = self._call_llm(system_prompt, user_prompt)
        if status is not None:
            # LLM call failed — return immediately with error status
            return self._failure_result(
                document=document,
                status=status,
                raw_response=str(llm_response) if llm_response else "",
                extracted_at=extracted_at,
            )

        assert llm_response is not None
        raw_text   = llm_response.content
        latency_ms = llm_response.latency_ms

        # Step 3: Parse JSON
        parsed_json, parse_error = self._validator.parse_llm_response(raw_text)
        if parsed_json is None:
            return ExtractionResult(
                document_id=document.id,
                asset_id=document.entity_hints.asset_id,
                company_id=document.entity_hints.company_id,
                source_url=document.source_url,
                status=ExtractionStatus.PARSE_ERROR,
                raw_llm_response=raw_text,
                raw_llm_json=None,
                validation_errors=[parse_error or "Unknown parse error"],
                extraction_model=self._llm.model_id,
                prompt_version=self._version,
                latency_ms=latency_ms,
                extracted_at=extracted_at,
            )

        # Step 4: Pull quality metadata from the JSON (not passed to StructuredSignal)
        confidence    = float(parsed_json.get("confidence", 0.0))
        ambiguity     = bool(parsed_json.get("ambiguity_flag", False))
        rationale     = str(parsed_json.get("rationale", ""))
        event_type_raw = parsed_json.get("event_type")

        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))

        # Step 5: Build and validate StructuredSignal
        signal, validation_errors = self._validator.build_signal(
            llm_json=parsed_json,
            document=document,
            event_id=event_id,
            extraction_model=self._llm.model_id,
            extracted_at=extracted_at,
        )

        if signal is None:
            return ExtractionResult(
                document_id=document.id,
                asset_id=document.entity_hints.asset_id,
                company_id=document.entity_hints.company_id,
                source_url=document.source_url,
                status=ExtractionStatus.VALIDATION_ERROR,
                event_type_detected=str(event_type_raw) if event_type_raw else None,
                raw_llm_response=raw_text,
                raw_llm_json=parsed_json,
                validation_errors=validation_errors,
                ambiguity_flag=ambiguity,
                extraction_confidence=confidence,
                rationale=rationale,
                extraction_model=self._llm.model_id,
                prompt_version=self._version,
                latency_ms=latency_ms,
                extracted_at=extracted_at,
            )

        return ExtractionResult(
            document_id=document.id,
            asset_id=document.entity_hints.asset_id,
            company_id=document.entity_hints.company_id,
            source_url=document.source_url,
            status=ExtractionStatus.SUCCESS,
            signal=signal,
            event_type_detected=signal.event_type.value,
            raw_llm_response=raw_text,
            raw_llm_json=parsed_json,
            ambiguity_flag=ambiguity,
            extraction_confidence=confidence,
            rationale=rationale,
            extraction_model=self._llm.model_id,
            prompt_version=self._version,
            latency_ms=latency_ms,
            extracted_at=extracted_at,
        )

    def extract_batch(
        self,
        documents: list[RawDocument],
        event_ids: Optional[list[str]] = None,
    ) -> list[ExtractionResult]:
        """
        Extract signals from multiple documents sequentially.

        Maintains positional alignment: ``result[i]`` corresponds to
        ``documents[i]``.  Does not parallelize — callers control concurrency.

        Parameters
        ----------
        documents:
            List of normalized documents to process.
        event_ids:
            Optional list of pre-assigned event IDs (must match ``len(documents)``
            if provided).  When ``None``, a UUID is generated for each document.
        """
        if event_ids is not None and len(event_ids) != len(documents):
            raise ValueError(
                f"event_ids length ({len(event_ids)}) must match "
                f"documents length ({len(documents)})"
            )
        ids = event_ids or [None] * len(documents)
        return [self.extract(doc, eid) for doc, eid in zip(documents, ids)]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[Optional[LLMResponse], Optional[ExtractionStatus]]:
        """
        Call the LLM; translate exceptions to ``ExtractionStatus`` values.

        Returns ``(response, None)`` on success or ``(None, status)`` on error.
        """
        try:
            response = self._llm.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=1024,
            )
            if not response.content or not response.content.strip():
                return None, ExtractionStatus.LLM_REFUSED
            return response, None
        except LLMRateLimitError:
            return None, ExtractionStatus.LLM_ERROR
        except LLMRefusalError:
            return None, ExtractionStatus.LLM_REFUSED
        except LLMClientError:
            return None, ExtractionStatus.LLM_ERROR
        except Exception:
            return None, ExtractionStatus.LLM_ERROR

    def _failure_result(
        self,
        document: RawDocument,
        status: ExtractionStatus,
        raw_response: str,
        extracted_at: datetime,
    ) -> ExtractionResult:
        return ExtractionResult(
            document_id=document.id,
            asset_id=document.entity_hints.asset_id,
            company_id=document.entity_hints.company_id,
            source_url=document.source_url,
            status=status,
            raw_llm_response=raw_response,
            extraction_model=self._llm.model_id,
            prompt_version=self._version,
            extracted_at=extracted_at,
        )
