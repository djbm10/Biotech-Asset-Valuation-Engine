"""Generic source acquisition and corpus construction for buyer-specific S&E.

This package builds the *public evidence corpus* that discovery later searches. Acquisition is
deliberately generic: connectors query only for the buyer's canonical target and modality terms,
never for benchmark or reference asset names. The benchmark may verify which documents were found,
but its asset names must never become production search seeds.

The decisive readiness metric for this layer is **corpus evidence coverage** (see
``bve.se.evaluation.corpus_coverage``), not ranking or discovery recall.
"""

from bve.se.acquisition.corpus_store import (
    CorpusDocument,
    CorpusStore,
    IndexStatus,
    ParserStatus,
)
from bve.se.acquisition.source_health import SourceHealth, SourceHealthReport

__all__ = [
    "CorpusDocument",
    "CorpusStore",
    "IndexStatus",
    "ParserStatus",
    "SourceHealth",
    "SourceHealthReport",
]
