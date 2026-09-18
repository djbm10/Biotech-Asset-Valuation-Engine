"""A run's retrieval plan is only reproducible if its probe decisions are.

Alias admission makes the search plan adaptive: which terms a query issues depends on what
a live coherence probe measured at run time. That means a sealed corpus is not by itself
enough to replay a run. Replaying re-probes nothing -- the network is blocked, and
re-probing later would measure a different registry anyway -- so without the recorded
decisions a replay falls back to the fail-closed sole-claimant vocabulary and silently
becomes a *different run* against the same bytes.

These tests cover the round trip that makes a replayed remediation benchmark comparable to
the zero-shot run it is being compared against, and the fail-closed default that applies
when no decisions are supplied.
"""

from __future__ import annotations

import json

from bve.se.discovery.alias_admission import (
    AdmissionRegistry,
    Decision,
    ProbeRecord,
    active_registry,
    admitted_shared_aliases,
    install_registry,
    load_probe_registry,
)


def _probe(alias: str, target_id: str, decision: str) -> ProbeRecord:
    return ProbeRecord(
        alias=alias,
        target_id=target_id,
        all_claimants=[target_id, "TARGET:OTHER"],
        probe_query=alias,
        as_of_date="2026-08-20",
        source="clinicaltrials_gov",
        source_release="2026-08-20",
        document_hashes=["abc123"],
        anchor_sets={target_id: [alias], "TARGET:OTHER": ["other"]},
        support_counts={target_id: 9, "TARGET:OTHER": 0},
        documents_supporting_any_claimant=9,
        decision=decision,
        reason="test fixture",
    )


def test_sealed_probe_decisions_round_trip_exactly(tmp_path) -> None:
    """What is written must be what is read back, field for field.

    The artifact is the only durable record of why a plan issued the terms it issued.
    """

    original = AdmissionRegistry()
    original.record(_probe("SHARED", "TARGET:A", Decision.ACTIVE_PROBE_ADMITTED))
    original.record(_probe("CONTESTED", "TARGET:A", Decision.RETRIEVAL_AMBIGUOUS))
    path = tmp_path / "probes.json"
    path.write_text(
        json.dumps([vars(probe) for probe in original.probes()], indent=2, default=str)
    )

    restored = load_probe_registry(path)

    assert [vars(p) for p in restored.probes()] == [vars(p) for p in original.probes()]
    assert restored.admitted_aliases("TARGET:A") == ("SHARED",)


def test_a_refused_alias_stays_refused_on_replay(tmp_path) -> None:
    """Replay must not quietly re-admit what the sealed run refused.

    In the M15 HRH1 run the probe refused the target's own gene symbol. A replay that
    admitted it would be measuring a vocabulary the zero-shot run never had.
    """

    path = tmp_path / "probes.json"
    path.write_text(
        json.dumps([vars(_probe("HRH1", "TARGET:HRH1", Decision.RETRIEVAL_AMBIGUOUS))], default=str)
    )
    previous = install_registry(load_probe_registry(path))
    try:
        assert admitted_shared_aliases("TARGET:HRH1") == ()
    finally:
        install_registry(previous)


def test_no_installed_decisions_means_no_shared_alias_is_searchable() -> None:
    """The fail-closed default: a measurement that did not happen is not evidence."""

    previous = install_registry(AdmissionRegistry())
    try:
        assert active_registry().probes() == []
        assert admitted_shared_aliases("TARGET:ANYTHING") == ()
    finally:
        install_registry(previous)
