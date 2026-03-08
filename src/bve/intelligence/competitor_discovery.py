"""
Wave 2B — Competitor Program Discovery.

Queries ClinicalTrials.gov by indication keyword, extracts structured
competitor program records, persists them, and adds competes_with edges
to the knowledge graph.

Design constraints
------------------
- No direct valuation changes.  Discovery produces CompetitorDiscoveryResult
  which callers route through ReviewQueue for human approval before any
  competition model YAML is updated.
- Idempotent: re-running discovery for the same (asset_id, nct_id) pair
  does not duplicate rows or edges (INSERT OR IGNORE / ON CONFLICT).
- Network calls are isolated in discover() so the engine is fully testable
  by injecting a mock search function.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CompetitorProgram(BaseModel):
    """Structured record for one competitor program discovered on ClinicalTrials.gov."""

    program_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str           # watched asset this program competes with
    company: Optional[str] = None
    drug_name: str
    nct_id: Optional[str] = None
    phase: Optional[str] = None
    status: Optional[str] = None
    primary_endpoint_type: Optional[str] = None
    indication: str
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompetitorDiscoveryResult(BaseModel):
    """Summary of one discovery pass for an asset / indication pair."""

    asset_id: str
    indication: str
    programs_found: list[CompetitorProgram] = Field(default_factory=list)
    kg_edges_added: int = 0
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery engine
# ---------------------------------------------------------------------------

# Type alias for the injectable search function
SearchFn = Callable[..., list[dict[str, Any]]]

# ClinicalTrials.gov statuses considered active enough to monitor
_ACTIVE_STATUSES = {
    "NOT_YET_RECRUITING",
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
}


def _extract_program(
    proto: dict[str, Any],
    asset_id: str,
    indication: str,
    now: datetime,
) -> Optional[CompetitorProgram]:
    """
    Parse one ClinicalTrials.gov protocolSection into a CompetitorProgram.

    Returns None when the record lacks the minimum required fields (drug_name).
    """
    id_mod      = proto.get("identificationModule", {})
    stat_mod    = proto.get("statusModule", {})
    design_mod  = proto.get("designModule", {})
    arms_mod    = proto.get("armsInterventionsModule", {})
    outcomes_mod = proto.get("outcomesModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})

    nct_id  = id_mod.get("nctId") or None
    status  = stat_mod.get("overallStatus")
    phases  = design_mod.get("phases", [])
    phase   = phases[0] if phases else None

    # Drug name: first DRUG-type intervention, else brief title
    interventions = arms_mod.get("interventions", [])
    drug_names = [
        i.get("name", "")
        for i in interventions
        if i.get("interventionType", "").upper() == "DRUG"
    ]
    drug_name = drug_names[0] if drug_names else id_mod.get("briefTitle", "")
    if not drug_name:
        return None

    # Company: lead sponsor name
    company = sponsor_mod.get("leadSponsor", {}).get("name")

    # Primary endpoint type — map first primary outcome measure to a category
    primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
    ep_text = (primary_outcomes[0].get("measure", "") if primary_outcomes else "").lower()
    if "overall survival" in ep_text or " os " in ep_text:
        primary_endpoint_type = "os"
    elif "progression" in ep_text or "pfs" in ep_text:
        primary_endpoint_type = "pfs"
    elif ep_text:
        primary_endpoint_type = "surrogate"
    else:
        primary_endpoint_type = None

    return CompetitorProgram(
        asset_id=asset_id,
        company=company,
        drug_name=drug_name,
        nct_id=nct_id,
        phase=phase,
        status=status,
        primary_endpoint_type=primary_endpoint_type,
        indication=indication,
        discovered_at=now,
    )


class CompetitorDiscoveryEngine:
    """
    Discovers competitor programs for a watched asset by indication keyword.

    Parameters
    ----------
    store:
        KnowledgeStore instance (must already be open).
    max_results:
        Upper bound on trials fetched per discovery run.
    search_fn:
        Injectable search function for testing.  Defaults to
        ``bve.ingestion.clinicaltrials_gov.search_studies``.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        max_results: int = 50,
        search_fn: Optional[SearchFn] = None,
    ) -> None:
        self._store = store
        self._max_results = max_results
        self._search_fn = search_fn  # resolved lazily if None

    def _get_search_fn(self) -> SearchFn:
        if self._search_fn is not None:
            return self._search_fn
        from bve.ingestion.clinicaltrials_gov import search_studies
        return search_studies

    def discover(
        self,
        asset_id: str,
        asset_node_id: str,
        indication: str,
    ) -> CompetitorDiscoveryResult:
        """
        Run one discovery pass for *asset_id* against *indication*.

        Steps
        -----
        1. Search ClinicalTrials.gov by condition keyword.
        2. Parse each result into a CompetitorProgram.
        3. Persist to competitor_programs table (idempotent).
        4. Upsert a KG node for each program.
        5. Add a competes_with KG edge (asset → program).
        6. Return CompetitorDiscoveryResult (no valuation changes).

        Callers should route the result through ReviewQueue before
        updating any competition model configuration.
        """
        now = datetime.now(timezone.utc)
        result = CompetitorDiscoveryResult(asset_id=asset_id, indication=indication)

        try:
            search = self._get_search_fn()
            raw_studies = search(
                condition=indication,
                page_size=self._max_results,
            )
        except Exception as exc:
            result.errors.append(f"search_studies failed: {exc}")
            return result

        edges_added = 0

        for raw in raw_studies:
            proto = raw.get("protocolSection", raw)
            try:
                program = _extract_program(proto, asset_id, indication, now)
                if program is None:
                    continue

                # Skip statuses we don't care about
                if program.status and program.status not in _ACTIVE_STATUSES:
                    continue

                # Persist program
                self._store.add_competitor_program(program)
                result.programs_found.append(program)

                # Upsert KG node for this competitor program
                node = KGNode(
                    node_type=NodeType.COMPETITOR_PROGRAM,
                    name=program.drug_name,
                    external_id=program.nct_id,
                    properties={
                        "company": program.company,
                        "phase": program.phase,
                        "status": program.status,
                        "indication": indication,
                        "primary_endpoint_type": program.primary_endpoint_type,
                    },
                )
                self._store.upsert_node(node)

                # Add competes_with edge (asset node → competitor program node)
                edge = KGEdge(
                    source_node_id=asset_node_id,
                    target_node_id=node.node_id,
                    edge_type=EdgeType.COMPETES_WITH,
                    confidence=1.0,
                    properties={"indication": indication, "discovered_at": now.isoformat()},
                )
                self._store.add_edge(edge)
                edges_added += 1

            except Exception as exc:
                result.errors.append(f"parse/store error: {exc}")

        result.kg_edges_added = edges_added
        return result
