"""bve-discover — autonomous ticker + lead-asset discovery.

Slice 1 (this package): given a company, parse its CT.gov trials, cluster them
into candidate programs, rank the likely lead asset, and backtest that ranker
against the hand-authored universe seeds. Read-only: nothing here writes to the
registry, review queue, or any live store.
"""
from __future__ import annotations

from bve.discovery.lead_ranker import RankedLead, rank_leads, score_program
from bve.discovery.program_cluster import CandidateProgram, cluster_programs
from bve.discovery.sponsor_trials import (
    TrialRecord,
    fetch_sponsor_trials,
    parse_protocol,
)

__all__ = [
    "TrialRecord",
    "parse_protocol",
    "fetch_sponsor_trials",
    "CandidateProgram",
    "cluster_programs",
    "RankedLead",
    "rank_leads",
    "score_program",
]
