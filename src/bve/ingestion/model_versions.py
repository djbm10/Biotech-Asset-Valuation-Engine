"""
Version constants for the scoring pipeline.

Bump the appropriate version whenever you change:
  CLASSIFIER_VERSION   — event taxonomy, pattern library, or phase detection
  DELTA_MAP_VERSION    — SCORE_DELTA_MAP values or MAX_SINGLE_EVENT_DELTA
  MATERIALITY_VERSION  — BASE_MATERIALITY or event-specific modifiers
  CONTEXT_VERSION      — CONTEXT_MULTIPLIERS or sign-aware logic
  BASELINE_VERSION     — phase priors, validation modifiers, or baseline tables
  PAIR_SCORER_VERSION  — logit weights or PairFeatures definition
  SCHEMA_VERSION       — EvidenceRecord field additions or removals

Without version stamps, historical backtest replays cannot detect when old events
were scored under different rules — a silent data contamination risk.
"""
from __future__ import annotations

CLASSIFIER_VERSION = "v2.1"
DELTA_MAP_VERSION = "v2.1"
MATERIALITY_VERSION = "v1.0"
CONTEXT_VERSION = "v1.0"
BASELINE_VERSION = "v1.0"
PAIR_SCORER_VERSION = "v2.0"
SCHEMA_VERSION = "v1.2"

# Composite identifier for the full scoring pipeline run
PIPELINE_VERSION = f"{CLASSIFIER_VERSION}/{DELTA_MAP_VERSION}/{SCHEMA_VERSION}"

# All versions as a dict — useful for stamping on outputs / audit logs
ALL_VERSIONS: dict[str, str] = {
    "classifier": CLASSIFIER_VERSION,
    "delta_map": DELTA_MAP_VERSION,
    "materiality": MATERIALITY_VERSION,
    "context": CONTEXT_VERSION,
    "baseline": BASELINE_VERSION,
    "pair_scorer": PAIR_SCORER_VERSION,
    "schema": SCHEMA_VERSION,
}
