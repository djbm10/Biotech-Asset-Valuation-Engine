"""Claim-level evidence storage and normalization."""

from bve.se.evidence.ledger import EvidenceLedger
from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.evidence.entailment import check_structured_entailment
from bve.se.evidence.pubmed import PubMedEvidenceExtractor

__all__ = [
    "ClinicalTrialsEvidenceExtractor",
    "EvidenceLedger",
    "PubMedEvidenceExtractor",
    "check_structured_entailment",
]
