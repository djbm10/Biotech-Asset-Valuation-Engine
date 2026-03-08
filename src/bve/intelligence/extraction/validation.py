"""
Post-LLM validation guard for the extraction pipeline.

``ExtractionValidator`` is the single trust boundary between raw LLM text and
typed ``StructuredSignal`` objects.  Every call to ``StructuredSignal.model_validate``
with LLM-originated data happens in this module, and only here.

Design invariant
----------------
``build_signal()`` is the only code path that constructs a ``StructuredSignal``
from LLM output.  Callers (``SignalExtractor``) must not call
``StructuredSignal.model_validate()`` directly.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import ValidationError

from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.extraction.raw_document import RawDocument


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

# Patterns for common LLM artifacts that wrap the JSON payload
_CODE_FENCE_RE  = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_LEADING_PROSE  = re.compile(r"^[^{[]*({[\s\S]*})[^}]*$", re.DOTALL)


def _strip_llm_artifacts(raw: str) -> str:
    """
    Remove common LLM output artifacts so json.loads() can parse the result.

    Handles:
    - Markdown code fences (```json ... ``` or ``` ... ```)
    - Leading prose before the JSON object
    - Trailing explanation text after the closing brace
    """
    # 1. Try to extract content from code fences
    fence_match = _CODE_FENCE_RE.search(raw)
    if fence_match:
        return fence_match.group(1).strip()

    # 2. Try to extract first {...} block from surrounding prose
    prose_match = _LEADING_PROSE.match(raw.strip())
    if prose_match:
        return prose_match.group(1).strip()

    return raw.strip()


class ExtractionValidator:
    """
    Stateless validator for LLM extraction output.

    All methods are pure (no side effects, no I/O).
    """

    def parse_llm_response(
        self, raw_text: str
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """
        Attempt to parse a raw LLM response as a JSON object.

        Parameters
        ----------
        raw_text:
            The literal string returned by the LLM.

        Returns
        -------
        (parsed_dict, None)
            When parsing succeeds.
        (None, error_message)
            When parsing fails.
        """
        if not raw_text or not raw_text.strip():
            return None, "LLM returned an empty response"

        cleaned = _strip_llm_artifacts(raw_text)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return None, f"JSON parse error: {exc}"

        if not isinstance(parsed, dict):
            return None, f"Expected a JSON object, got {type(parsed).__name__}"

        return parsed, None

    def build_signal(
        self,
        llm_json: dict[str, Any],
        document: RawDocument,
        event_id: str,
        extraction_model: str,
        extracted_at: datetime,
    ) -> tuple[Optional[StructuredSignal], list[str]]:
        """
        Merge LLM-extracted fields with caller-provided identity fields and
        validate through ``StructuredSignal.model_validate()``.

        Parameters
        ----------
        llm_json:
            Parsed JSON dict from the LLM.  May contain extra keys; only
            recognized ``StructuredSignal`` fields are passed through.
        document:
            The source document; provides ``asset_id``, ``company_id``,
            and ``published_at`` (fallback for ``signal_date``).
        event_id:
            FK → ``Event.id``.  Assigned by the caller before extraction.
        extraction_model:
            Model identifier string.
        extracted_at:
            UTC timestamp of extraction completion.

        Returns
        -------
        (signal, [])
            When Pydantic validation passes.
        (None, [error_strings])
            When validation fails.

        Notes
        -----
        Identity fields (``id``, ``event_id``, ``asset_id``, ``company_id``,
        ``created_at``, ``extraction_model``) are always taken from the
        caller context, never from the LLM JSON.
        """
        # Determine signal_date: prefer LLM-extracted date, fall back to
        # document.published_at, then today
        signal_date_raw = llm_json.get("signal_date")
        signal_date: Optional[date] = None
        if signal_date_raw:
            try:
                signal_date = date.fromisoformat(str(signal_date_raw)[:10])
            except (ValueError, TypeError):
                pass
        if signal_date is None:
            if document.published_at:
                signal_date = document.published_at.date()
            else:
                signal_date = extracted_at.date()

        # Fields the LLM supplies (only signal-domain fields; metadata excluded)
        _LLM_KEYS = {
            "event_type", "trial_phase", "trial_nct_id",
            "primary_endpoint_met", "interim_flag",
            "hazard_ratio", "p_value", "response_rate", "safety_grade",
            "fda_action_type", "designation_type",
            "deal_value_millions", "deal_type", "payer_name",
        }

        signal_fields: dict[str, Any] = {
            k: v for k, v in llm_json.items()
            if k in _LLM_KEYS and v is not None
        }

        # Inject caller-controlled identity / provenance fields
        signal_fields.update({
            "id":                    str(uuid.uuid4()),
            "event_id":              event_id,
            "asset_id":              document.entity_hints.asset_id,
            "company_id":            document.entity_hints.company_id,
            "signal_date":           signal_date,
            "extraction_model":      extraction_model,
            "extraction_confidence": float(llm_json.get("confidence", 0.0)),
            "created_at":            extracted_at,
        })

        # Clamp extraction_confidence to [0, 1]
        ec = signal_fields["extraction_confidence"]
        signal_fields["extraction_confidence"] = max(0.0, min(1.0, float(ec)))

        try:
            signal = StructuredSignal.model_validate(signal_fields)
            return signal, []
        except ValidationError as exc:
            errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
            return None, errors
