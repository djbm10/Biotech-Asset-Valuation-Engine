"""
Phase 1: Ingestion and Extraction layer.

Public surface
--------------
``RawDocument`` / ``EntityHints``
    Normalized document schema produced by every source connector.

``ExtractionResult`` / ``ExtractionStatus``
    Typed outcome of one extraction attempt (success or failure).

``SignalExtractor``
    Orchestrator: ``RawDocument`` → ``ExtractionResult``.

``LLMClient`` (Protocol) / ``AnthropicClient`` / ``OpenAIClient`` / ``FakeLLMClient``
    LLM backend abstractions.

``PromptBuilder``
    Stateless prompt constructor.

``ExtractionValidator``
    Single trust boundary between LLM JSON and ``StructuredSignal``.

Isolation guarantee
-------------------
Nothing in this package imports from ``bve.intelligence.mapping``,
``bve.intelligence.schemas.proposals``, ``bve.intelligence.schemas.runs``,
``bve.valuation.*``, or ``bve.models.*``.  Phase 1 ends at a validated
``StructuredSignal``.
"""
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.extraction.extractor import SignalExtractor
from bve.intelligence.extraction.llm_client import (
    LLMClient,
    LLMResponse,
    LLMClientError,
    LLMRateLimitError,
    LLMRefusalError,
    AnthropicClient,
    OpenAIClient,
    FakeLLMClient,
)
from bve.intelligence.extraction.prompt_builder import PromptBuilder, CURRENT_PROMPT_VERSION
from bve.intelligence.extraction.validation import ExtractionValidator

__all__ = [
    # Documents
    "EntityHints",
    "RawDocument",
    # Results
    "ExtractionResult",
    "ExtractionStatus",
    # Extractor
    "SignalExtractor",
    # LLM clients
    "LLMClient",
    "LLMResponse",
    "LLMClientError",
    "LLMRateLimitError",
    "LLMRefusalError",
    "AnthropicClient",
    "OpenAIClient",
    "FakeLLMClient",
    # Prompt & validation
    "PromptBuilder",
    "CURRENT_PROMPT_VERSION",
    "ExtractionValidator",
]
