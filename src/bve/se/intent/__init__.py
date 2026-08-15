"""Natural-language search intent layer (M9C)."""

from bve.se.intent.compiler import (
    UNSPECIFIED_THERAPEUTIC_AREA,
    IntentNotCompilable,
    build_buyer_identity,
    compile_intent,
    intent_to_trial_query,
)
from bve.se.intent.intent import (
    INTENT_COMPILER_VERSION,
    IntentSpan,
    SearchIntent,
    SpanKind,
)
from bve.se.intent.parser import modality_surface_forms, parse_query, supported_modalities

__all__ = [
    "INTENT_COMPILER_VERSION",
    "IntentNotCompilable",
    "IntentSpan",
    "SearchIntent",
    "SpanKind",
    "UNSPECIFIED_THERAPEUTIC_AREA",
    "build_buyer_identity",
    "compile_intent",
    "intent_to_trial_query",
    "modality_surface_forms",
    "parse_query",
    "supported_modalities",
]
