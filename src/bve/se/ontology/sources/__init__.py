"""Bulk upstream parsers that emit source-fidelity ontology records."""

from bve.se.ontology.sources.chembl import parse_chembl_target
from bve.se.ontology.sources.open_targets import parse_open_targets_target

__all__ = ["parse_chembl_target", "parse_open_targets_target"]
