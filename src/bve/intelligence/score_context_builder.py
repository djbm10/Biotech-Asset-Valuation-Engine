"""Build ``CompositeScoreContext`` per asset from stored signals.

Commit 1 of the live scanner score-update contract. Today the weekly scanner
(`ops/weekly_runner.cmd_report`) scores candidates with ``contexts=None``, so the
signal-driven ``CompositeScorer`` path is never fed and live events do not move the
scanner score. This module closes that gap: for each asset it reads recent
``StructuredSignal`` records from the ``KnowledgeStore`` and maps the highest-signal
fields onto a ``CompositeScoreContext`` (catalyst strength, endpoint z, enrollment
flags); everything else is left neutral until validated in a later commit.

It also returns the contributing signal/event IDs so the caller can persist an
auditable ``score_update`` record (source → fact → score impact lineage).

Pure over an injected store object exposing ``get_structured_signals(...)`` — no
network, fully offline-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist
from typing import Optional, Protocol

from bve.intelligence.composite_scorer import CompositeScoreContext
from bve.intelligence.schemas.signals import StructuredSignal

_DEFAULT_LOOKBACK_DAYS = 120

# Catalyst signal strength is clipped to ±1 by CompositeScorer; use that scale.
# FDA action dominates, then severe safety, then the binary endpoint outcome.
_FDA_STRENGTH: dict[str, float] = {
    "approval": 1.0,
    "hold_lifted": 0.6,
    "hold": -0.6,
    "crl": -1.0,
}
_ENDPOINT_MET_STRENGTH = 0.6
_SEVERE_SAFETY_STRENGTH = -0.8
_SEVERE_SAFETY_GRADE = 4

# Enrollment statuses that constitute a negative enrollment event.
_STOPPED_ENROLLMENT = {"terminated", "withdrawn"}

_NORM = NormalDist()


class _SignalSource(Protocol):
    def get_structured_signals(self, **kwargs) -> list: ...  # pragma: no cover


@dataclass(frozen=True)
class AssetScoreContext:
    """A built context plus the signal/event IDs that explain it (for audit)."""

    context: CompositeScoreContext
    contributing_signal_ids: tuple[str, ...]
    contributing_event_ids: tuple[str, ...]


def _catalyst_strength(sig: StructuredSignal) -> Optional[float]:
    """Coarse catalyst signal strength in ~[-1, 1] from a readout/FDA/safety signal."""
    if sig.fda_action_type and sig.fda_action_type in _FDA_STRENGTH:
        return _FDA_STRENGTH[sig.fda_action_type]
    if sig.safety_grade is not None and sig.safety_grade >= _SEVERE_SAFETY_GRADE:
        return _SEVERE_SAFETY_STRENGTH
    if sig.primary_endpoint_met is True:
        return _ENDPOINT_MET_STRENGTH
    if sig.primary_endpoint_met is False:
        return -_ENDPOINT_MET_STRENGTH
    return None


def _endpoint_z(sig: StructuredSignal) -> Optional[float]:
    """Signed endpoint z-score from the reported p-value (one-sided), direction-aware."""
    if sig.p_value is None:
        return None
    p = min(max(sig.p_value, 1e-6), 1.0 - 1e-6)
    z = _NORM.inv_cdf(1.0 - p)  # positive magnitude for a small p-value
    missed = sig.primary_endpoint_met is False
    negative_effect = sig.estimated_effect_size is not None and sig.estimated_effect_size < 0
    if missed or negative_effect:
        z = -z
    return z


def _is_stopped_enrollment(sig: StructuredSignal) -> bool:
    return sig.enrollment_status in _STOPPED_ENROLLMENT


def _signals_for(store: _SignalSource, asset_id: str, date_from: date, date_to: date) -> list[StructuredSignal]:
    """Load + parse recent structured signals for one asset, newest first."""
    records = store.get_structured_signals(
        asset_id=asset_id, date_from=date_from, date_to=date_to, limit=200
    )
    signals: list[StructuredSignal] = []
    for rec in records:
        payload = getattr(rec, "payload_json", None)
        if not isinstance(payload, dict):
            continue
        try:
            signals.append(StructuredSignal.model_validate(payload))
        except Exception:
            continue  # skip malformed/partial payloads — never break the scan
    signals.sort(key=lambda s: s.signal_date, reverse=True)
    return signals


def build_asset_context(signals: list[StructuredSignal]) -> Optional[AssetScoreContext]:
    """Map an asset's recent signals → a context (pure). None when no usable signal.

    Selection: the strongest-magnitude catalyst, the most recent endpoint z, and the
    most recent stopped-enrollment flag. Missing fields stay neutral.
    """
    sig_ids: list[str] = []
    evt_ids: list[str] = []

    best_catalyst: Optional[tuple[float, StructuredSignal]] = None
    for s in signals:
        strength = _catalyst_strength(s)
        if strength is not None and (best_catalyst is None or abs(strength) > abs(best_catalyst[0])):
            best_catalyst = (strength, s)

    catalyst_strength: Optional[float] = None
    if best_catalyst is not None:
        catalyst_strength = best_catalyst[0]
        sig_ids.append(best_catalyst[1].id)
        evt_ids.append(best_catalyst[1].event_id)

    endpoint_z: Optional[float] = None
    for s in signals:  # newest first
        z = _endpoint_z(s)
        if z is not None:
            endpoint_z = z
            sig_ids.append(s.id)
            evt_ids.append(s.event_id)
            break

    slippage = False
    for s in signals:
        if _is_stopped_enrollment(s):
            slippage = True
            sig_ids.append(s.id)
            evt_ids.append(s.event_id)
            break

    if catalyst_strength is None and endpoint_z is None and not slippage:
        return None

    context = CompositeScoreContext(
        catalyst_signal_strength=catalyst_strength,
        endpoint_z_score=endpoint_z,
        enrollment_slippage_alert=slippage,
    )
    return AssetScoreContext(
        context=context,
        contributing_signal_ids=tuple(dict.fromkeys(sig_ids)),
        contributing_event_ids=tuple(dict.fromkeys(evt_ids)),
    )


def build_score_contexts(
    store: _SignalSource,
    asset_ids: list[str],
    *,
    as_of: Optional[date] = None,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> dict[str, AssetScoreContext]:
    """Build ``CompositeScoreContext`` (+ contributing IDs) for each asset with signals.

    Assets with no usable signal in the lookback window are omitted (the scanner then
    scores them neutrally, exactly as today).
    """
    as_of = as_of or date.today()
    date_from = as_of - timedelta(days=lookback_days)
    out: dict[str, AssetScoreContext] = {}
    for asset_id in asset_ids:
        signals = _signals_for(store, asset_id, date_from, as_of)
        built = build_asset_context(signals)
        if built is not None:
            out[asset_id] = built
    return out
