"""Canonical asset graph helpers for Phase B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.dossier.builder import DossierBuilder
from bve.dossier.dossier import AssetDossier, TrialSummary
from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.normalization.normalizer import IndicationNormalizer, MOANormalizer, TargetNormalizer
from bve.normalization.types import NormalizationConfidence, NormalizationResult

_FUZZY_ALIAS_ACCEPT = 88


def _today() -> date:
    return date.today()


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _coerce_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for parser in (date.fromisoformat,):
        try:
            return parser(text[:10])
        except ValueError:
            continue
    return None


def _field_source(properties: dict[str, Any], default: str) -> str:
    return str(properties.get("source") or default)


def _field_confidence(properties: dict[str, Any], default: float = 0.8) -> float:
    try:
        parsed = float(properties.get("confidence", default))
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _field_verified_date(properties: dict[str, Any]) -> date:
    return _coerce_date(properties.get("last_verified")) or _coerce_date(
        properties.get("as_of")
    ) or _today()


def _edge_matches(edge: KGEdge, *, source_node_id: str, edge_type: EdgeType) -> bool:
    return edge.source_node_id == source_node_id and edge.edge_type == edge_type


def _slugify(value: str) -> str:
    normalized = _normalize_text(value)
    chars = [ch if ch.isalnum() else "_" for ch in normalized]
    collapsed = "".join(chars)
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    return collapsed.strip("_") or "unknown"


def _fuzzy_candidates(query: str, choices: list[str], limit: int = 3) -> list[tuple[str, float]]:
    scored = [
        (choice, round(SequenceMatcher(None, query, choice).ratio() * 100.0, 2))
        for choice in choices
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


class AliasRecord(BaseModel):
    alias: str
    normalized_alias: str
    node_type: NodeType
    canonical_name: str
    external_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str


class AliasResolution(BaseModel):
    alias: str
    node_type: NodeType
    external_id: Optional[str] = None
    canonical_name: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    method: str = "none"
    alternatives: list[tuple[str, float]] = Field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.external_id is not None


@dataclass
class AssetGraphBundle:
    company_node: KGNode
    asset_node: KGNode
    trial_nodes: list[KGNode]
    created_edges: list[KGEdge]


class AliasTable:
    """Explicit alias table for company names, drug names, and normalized concepts."""

    def __init__(self) -> None:
        self._records_by_key: dict[tuple[str, NodeType], AliasRecord] = {}

    def register(
        self,
        *,
        alias: str,
        node_type: NodeType,
        canonical_name: str,
        external_id: str,
        confidence: float,
        source: str,
    ) -> AliasRecord:
        normalized = _normalize_text(alias)
        record = AliasRecord(
            alias=alias,
            normalized_alias=normalized,
            node_type=node_type,
            canonical_name=canonical_name,
            external_id=external_id,
            confidence=confidence,
            source=source,
        )
        self._records_by_key[(normalized, node_type)] = record
        return record

    def records(self, node_type: Optional[NodeType] = None) -> list[AliasRecord]:
        records = list(self._records_by_key.values())
        if node_type is None:
            return sorted(records, key=lambda item: (item.node_type.value, item.normalized_alias))
        return sorted(
            [record for record in records if record.node_type == node_type],
            key=lambda item: item.normalized_alias,
        )

    def resolve(self, alias: str, node_type: NodeType) -> AliasResolution:
        normalized = _normalize_text(alias)
        exact = self._records_by_key.get((normalized, node_type))
        if exact is not None:
            return AliasResolution(
                alias=alias,
                node_type=node_type,
                external_id=exact.external_id,
                canonical_name=exact.canonical_name,
                confidence=exact.confidence,
                method="exact",
            )

        choices = [record.normalized_alias for record in self.records(node_type)]
        if not choices:
            return AliasResolution(alias=alias, node_type=node_type)

        ranked = _fuzzy_candidates(normalized, choices, limit=3)
        if not ranked:
            return AliasResolution(alias=alias, node_type=node_type)
        matched_alias, score = ranked[0]
        alternatives = [
            (record.canonical_name, float(item_score))
            for item_alias, item_score in ranked
            for record in [self._records_by_key[(item_alias, node_type)]]
        ]
        if score < _FUZZY_ALIAS_ACCEPT:
            return AliasResolution(
                alias=alias,
                node_type=node_type,
                confidence=min(float(score) / 100.0, 1.0),
                method="fuzzy_low",
                alternatives=alternatives,
            )
        record = self._records_by_key[(matched_alias, node_type)]
        return AliasResolution(
            alias=alias,
            node_type=node_type,
            external_id=record.external_id,
            canonical_name=record.canonical_name,
            confidence=min(float(score) / 100.0, record.confidence),
            method="fuzzy",
            alternatives=alternatives,
        )


class EntityResolver:
    """Combines the explicit alias table with existing concept normalizers."""

    def __init__(self, alias_table: Optional[AliasTable] = None) -> None:
        self.alias_table = alias_table or AliasTable()
        self._indication = IndicationNormalizer()
        self._target = TargetNormalizer()
        self._moa = MOANormalizer()

    def seed_company_asset(self, company: Company, asset: Asset) -> None:
        self.alias_table.register(
            alias=company.name,
            node_type=NodeType.COMPANY,
            canonical_name=company.name,
            external_id=company.id,
            confidence=1.0,
            source="company_model",
        )
        if company.ticker:
            self.alias_table.register(
                alias=company.ticker,
                node_type=NodeType.COMPANY,
                canonical_name=company.name,
                external_id=company.id,
                confidence=0.99,
                source="ticker",
            )
        self.alias_table.register(
            alias=asset.name,
            node_type=NodeType.ASSET,
            canonical_name=asset.name,
            external_id=asset.id,
            confidence=1.0,
            source="asset_model",
        )
        if asset.id != asset.name:
            self.alias_table.register(
                alias=asset.id,
                node_type=NodeType.ASSET,
                canonical_name=asset.name,
                external_id=asset.id,
                confidence=0.99,
                source="asset_id",
            )

    def resolve_graph_entity(self, alias: str, node_type: NodeType) -> AliasResolution:
        return self.alias_table.resolve(alias, node_type)

    def resolve_target(self, raw: str) -> NormalizationResult:
        return self._target.normalize(raw)

    def resolve_indication(self, raw: str) -> NormalizationResult:
        return self._indication.normalize(raw)

    def resolve_mechanism(self, raw: str) -> NormalizationResult:
        return self._moa.normalize(raw)


class CanonicalAssetGraph:
    """Builds and queries the canonical asset graph on top of KnowledgeStore."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        resolver: Optional[EntityResolver] = None,
    ) -> None:
        self.store = store
        self.resolver = resolver or EntityResolver()

    def _upsert_node(
        self,
        *,
        node_type: NodeType,
        name: str,
        external_id: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> KGNode:
        existing = self.store.find_node_by_external_id(node_type, external_id)
        payload_kwargs: dict[str, Any] = {
            "node_type": node_type,
            "name": name,
            "external_id": external_id,
            "properties": properties or {},
            "created_at": existing.created_at if existing else datetime.now().astimezone(),
        }
        if existing is not None:
            payload_kwargs["node_id"] = existing.node_id
        payload = KGNode(**payload_kwargs)
        return self.store.upsert_node(payload)

    def _connect(
        self,
        source: KGNode,
        target: KGNode,
        edge_type: EdgeType,
        *,
        confidence: float = 1.0,
        properties: Optional[dict[str, Any]] = None,
    ) -> KGEdge:
        edge = KGEdge(
            source_node_id=source.node_id,
            target_node_id=target.node_id,
            edge_type=edge_type,
            confidence=confidence,
            properties=properties or {},
        )
        return self.store.add_edge(edge)

    def upsert_asset_bundle(
        self,
        *,
        company: Company,
        asset: Asset,
        trials: list[ClinicalTrial],
        management_team: Optional[str] = None,
        thesis_summary: Optional[str] = None,
    ) -> AssetGraphBundle:
        self.resolver.seed_company_asset(company, asset)

        company_node = self._upsert_node(
            node_type=NodeType.COMPANY,
            name=company.name,
            external_id=company.id,
            properties={
                "ticker": company.ticker,
                "cash_millions": company.cash_millions,
                "debt_millions": company.debt_millions,
                "shares_outstanding_millions": company.shares_outstanding_millions,
                "burn_rate_millions_per_quarter": company.burn_rate_millions_per_quarter,
                "source": "company_model",
                "confidence": 0.95,
                "last_verified": _today().isoformat(),
                "aliases": [company.name, company.ticker] if company.ticker else [company.name],
            },
        )
        asset_node = self._upsert_node(
            node_type=NodeType.ASSET,
            name=asset.name,
            external_id=asset.id,
            properties={
                "stage": asset.stage.value,
                "indication": asset.indication,
                "modality": asset.modality.value,
                "mechanism_of_action": asset.mechanism_of_action,
                "biological_target": asset.biological_target,
                "therapeutic_area": asset.therapeutic_area.value,
                "differentiation_notes": asset.differentiation_notes,
                "source": "asset_model",
                "confidence": 0.95,
                "last_verified": _today().isoformat(),
                "aliases": [asset.name, asset.id],
            },
        )

        edges: list[KGEdge] = [
            self._connect(company_node, asset_node, EdgeType.COMPANY_OWNS_ASSET),
        ]

        indication_result = self.resolver.resolve_indication(asset.indication)
        indication_external_id = indication_result.canonical_id or f"IND_{_slugify(asset.indication)}"
        indication_node = self._upsert_node(
            node_type=NodeType.INDICATION,
            name=indication_result.canonical_name or asset.indication,
            external_id=indication_external_id,
            properties={
                "raw_name": asset.indication,
                "normalization_method": indication_result.method,
                "confidence": 0.99
                if indication_result.confidence == NormalizationConfidence.HIGH
                else 0.8,
                "source": "indication_normalizer"
                if indication_result.canonical_id
                else "asset_model",
                "last_verified": _today().isoformat(),
            },
        )
        edges.append(
            self._connect(
                asset_node,
                indication_node,
                EdgeType.ASSET_TREATS_INDICATION,
                confidence=0.99 if indication_result.is_trustworthy else 0.7,
            )
        )

        if asset.biological_target:
            target_result = self.resolver.resolve_target(asset.biological_target)
            target_node = self._upsert_node(
                node_type=NodeType.TARGET,
                name=target_result.canonical_name or asset.biological_target,
                external_id=target_result.canonical_id or f"TGT_{_slugify(asset.biological_target)}",
                properties={
                    "raw_name": asset.biological_target,
                    "normalization_method": target_result.method,
                    "confidence": 0.99 if target_result.is_trustworthy else 0.75,
                    "source": "target_normalizer" if target_result.canonical_id else "asset_model",
                    "last_verified": _today().isoformat(),
                },
            )
            edges.append(
                self._connect(
                    asset_node,
                    target_node,
                    EdgeType.ASSET_TARGETS_TARGET,
                    confidence=0.99 if target_result.is_trustworthy else 0.75,
                )
            )
            self.resolver.alias_table.register(
                alias=asset.biological_target,
                node_type=NodeType.TARGET,
                canonical_name=target_node.name,
                external_id=target_node.external_id or target_node.node_id,
                confidence=_field_confidence(target_node.properties),
                source="target_normalizer",
            )

        if asset.mechanism_of_action:
            moa_result = self.resolver.resolve_mechanism(asset.mechanism_of_action)
            mechanism_node = self._upsert_node(
                node_type=NodeType.MECHANISM,
                name=moa_result.canonical_name or asset.mechanism_of_action,
                external_id=moa_result.canonical_id or f"MOA_{_slugify(asset.mechanism_of_action)}",
                properties={
                    "raw_name": asset.mechanism_of_action,
                    "normalization_method": moa_result.method,
                    "confidence": 0.99 if moa_result.is_trustworthy else 0.75,
                    "source": "moa_normalizer" if moa_result.canonical_id else "asset_model",
                    "last_verified": _today().isoformat(),
                },
            )
            edges.append(self._connect(asset_node, mechanism_node, EdgeType.HAS_MECHANISM))

        modality_node = self._upsert_node(
            node_type=NodeType.MODALITY,
            name=asset.modality.value,
            external_id=f"MOD_{asset.modality.value}",
            properties={
                "source": "asset_model",
                "confidence": 1.0,
                "last_verified": _today().isoformat(),
            },
        )
        edges.append(self._connect(asset_node, modality_node, EdgeType.HAS_MODALITY, confidence=1.0))

        financing_node = self._upsert_node(
            node_type=NodeType.FINANCING_STATE,
            name=f"{company.name} financing state",
            external_id=f"financing:{company.id}",
            properties={
                "cash_millions": company.cash_millions,
                "debt_millions": company.debt_millions,
                "burn_rate_millions_per_quarter": company.burn_rate_millions_per_quarter,
                "months_of_runway": (
                    round((company.cash_runway_quarters or 0.0) * 3.0, 2)
                    if company.cash_runway_quarters is not None
                    else None
                ),
                "source": "company_model",
                "confidence": 0.95,
                "last_verified": _today().isoformat(),
            },
        )
        edges.append(
            self._connect(company_node, financing_node, EdgeType.FINANCING_APPLIES_TO_COMPANY)
        )

        if management_team:
            management_node = self._upsert_node(
                node_type=NodeType.MANAGEMENT_TEAM,
                name=management_team,
                external_id=f"mgmt:{company.id}",
                properties={
                    "source": "manual",
                    "confidence": 0.8,
                    "last_verified": _today().isoformat(),
                },
            )
            edges.append(self._connect(management_node, company_node, EdgeType.MANAGEMENT_RUNS_COMPANY))

        if thesis_summary:
            thesis_node = self._upsert_node(
                node_type=NodeType.THESIS_SNAPSHOT,
                name=f"{asset.name} thesis",
                external_id=f"thesis:{asset.id}",
                properties={
                    "summary": thesis_summary,
                    "source": "manual",
                    "confidence": 0.8,
                    "last_verified": _today().isoformat(),
                },
            )
            edges.append(
                self._connect(thesis_node, asset_node, EdgeType.THESIS_SNAPSHOT_FOR_ASSET, confidence=0.8)
            )

        trial_nodes: list[KGNode] = []
        for trial in trials:
            trial_external_id = trial.nct_id or f"{asset.id}:{trial.phase.value}:{len(trial_nodes)}"
            trial_node = self._upsert_node(
                node_type=NodeType.TRIAL,
                name=trial.title or trial_external_id,
                external_id=trial_external_id,
                properties={
                    "phase": trial.phase.value,
                    "status": trial.status.value,
                    "primary_endpoint": trial.primary_endpoint,
                    "endpoint_type": trial.endpoint_type.value,
                    "enrollment": trial.enrollment,
                    "success_probability": trial.success_probability,
                    "source": trial.data_source,
                    "confidence": 0.99 if trial.data_source == "clinicaltrials_gov" else 0.85,
                    "last_verified": _coerce_date(trial.primary_completion_date or trial.start_date or _today())
                    .isoformat(),
                    "primary_completion_date": trial.primary_completion_date,
                },
            )
            trial_nodes.append(trial_node)
            edges.append(self._connect(trial_node, asset_node, EdgeType.TRIAL_BELONGS_TO_ASSET))

        for index, competitor_name in enumerate(asset.competitor_assets):
            competitor_node = self._upsert_node(
                node_type=NodeType.COMPETITOR_PROGRAM,
                name=competitor_name,
                external_id=f"competitor:{_slugify(competitor_name)}",
                properties={
                    "source": "asset_model",
                    "confidence": 0.7,
                    "last_verified": _today().isoformat(),
                },
            )
            edges.append(
                self._connect(
                    asset_node,
                    competitor_node,
                    EdgeType.COMPETITOR_OVERLAPS_ASSET,
                    confidence=max(0.5, 0.8 - (0.05 * index)),
                )
            )

        for catalyst in asset.upcoming_catalysts:
            catalyst_external_id = f"catalyst:{asset.id}:{_slugify(catalyst.description)}"
            catalyst_node = self._upsert_node(
                node_type=NodeType.CATALYST,
                name=catalyst.description,
                external_id=catalyst_external_id,
                properties={
                    "expected_date": catalyst.expected_date,
                    "catalyst_type": catalyst.catalyst_type,
                    "probability_positive": catalyst.probability_positive,
                    "source": "asset_model",
                    "confidence": 0.8,
                    "last_verified": _today().isoformat(),
                },
            )
            edges.append(self._connect(catalyst_node, asset_node, EdgeType.CATALYST_FOR_ASSET, confidence=0.8))

        return AssetGraphBundle(
            company_node=company_node,
            asset_node=asset_node,
            trial_nodes=trial_nodes,
            created_edges=edges,
        )


class AssetGraphQueryService:
    """Query layer over the canonical asset graph."""

    def __init__(self, store: KnowledgeStore, resolver: Optional[EntityResolver] = None) -> None:
        self.store = store
        self.resolver = resolver or EntityResolver()

    def resolve_asset_node(self, asset_ref: str) -> Optional[KGNode]:
        direct = self.store.find_node_by_external_id(NodeType.ASSET, asset_ref)
        if direct is not None:
            return direct
        by_name = next(
            (
                node
                for node in self.store.find_by_type(NodeType.ASSET)
                if node.name.strip().lower() == asset_ref.strip().lower()
            ),
            None,
        )
        if by_name is not None:
            return by_name
        resolution = self.resolver.resolve_graph_entity(asset_ref, NodeType.ASSET)
        if resolution.found and resolution.external_id:
            return self.store.find_node_by_external_id(NodeType.ASSET, resolution.external_id)
        return None

    def resolve_company_node(self, company_ref: str) -> Optional[KGNode]:
        direct = self.store.find_node_by_external_id(NodeType.COMPANY, company_ref)
        if direct is not None:
            return direct
        resolution = self.resolver.resolve_graph_entity(company_ref, NodeType.COMPANY)
        if resolution.found and resolution.external_id:
            return self.store.find_node_by_external_id(NodeType.COMPANY, resolution.external_id)
        return None

    def get_subgraph(self, node_id: str, depth: int = 2) -> tuple[dict[str, KGNode], list[KGEdge]]:
        graph = self.store.get_subgraph(node_id, depth=depth)
        nodes = {node.node_id: node for node in graph["nodes"]}
        return nodes, list(graph["edges"])

    def related_nodes(
        self,
        source_node_id: str,
        edge_type: EdgeType,
        target_type: Optional[NodeType] = None,
        *,
        direction: str = "outgoing",
    ) -> list[KGNode]:
        nodes, edges = self.get_subgraph(source_node_id, depth=1)
        matches: list[KGNode] = []
        for edge in edges:
            candidate_ids: list[str] = []
            if direction in {"outgoing", "both"} and _edge_matches(
                edge, source_node_id=source_node_id, edge_type=edge_type
            ):
                candidate_ids.append(edge.target_node_id)
            if (
                direction in {"incoming", "both"}
                and edge.target_node_id == source_node_id
                and edge.edge_type == edge_type
            ):
                candidate_ids.append(edge.source_node_id)
            for candidate_id in candidate_ids:
                candidate = nodes.get(candidate_id)
                if candidate is None:
                    continue
                if target_type is not None and candidate.node_type != target_type:
                    continue
                matches.append(candidate)
        return matches

    def company_for_asset(self, asset_node_id: str) -> Optional[KGNode]:
        nodes, edges = self.get_subgraph(asset_node_id, depth=1)
        for edge in edges:
            if edge.target_node_id == asset_node_id and edge.edge_type == EdgeType.COMPANY_OWNS_ASSET:
                node = nodes.get(edge.source_node_id)
                if node is not None and node.node_type == NodeType.COMPANY:
                    return node
        return None


class GraphBackedDossierBuilder:
    """Auto-builds an AssetDossier from graph entities and relationships."""

    def __init__(self, store: KnowledgeStore, *, resolver: Optional[EntityResolver] = None) -> None:
        self.store = store
        self.resolver = resolver or EntityResolver()
        self.query = AssetGraphQueryService(store, self.resolver)

    def _set_from_node_property(
        self,
        builder: DossierBuilder,
        field_name: str,
        node: Optional[KGNode],
        property_name: Optional[str] = None,
        *,
        fallback_value: Any = None,
    ) -> None:
        if node is None and fallback_value is None:
            return
        if node is None:
            value = fallback_value
            source = "graph_fallback"
            confidence = 0.6
            verified_at = _today()
            last_verified = None
        else:
            properties = node.properties
            value = properties.get(property_name or "value", node.name)
            if value is None and fallback_value is None:
                return
            if value is None:
                value = fallback_value
            source = _field_source(properties, f"graph:{node.node_type.value}")
            confidence = _field_confidence(properties)
            verified_at = _field_verified_date(properties)
            last_verified = verified_at
        builder.set_field(
            field_name,
            value,
            source=source,
            confidence=confidence,
            extracted_at=verified_at,
            last_verified=last_verified,
        )

    def build(self, asset_ref: str) -> AssetDossier:
        asset_node = self.query.resolve_asset_node(asset_ref)
        if asset_node is None:
            raise ValueError(f"Unable to resolve asset from {asset_ref!r}")

        company_node = self.query.company_for_asset(asset_node.node_id)
        builder = DossierBuilder(
            asset_node.external_id or asset_node.node_id,
            asset_node.name,
            company_node.name if company_node else "Unknown Company",
        )
        builder.set_created_at(_today())

        self._set_from_node_property(
            builder,
            "mechanism_of_action",
            None,
            fallback_value=asset_node.properties.get("mechanism_of_action"),
        )
        self._set_from_node_property(
            builder,
            "modality",
            None,
            fallback_value=asset_node.properties.get("modality"),
        )
        self._set_from_node_property(
            builder,
            "current_phase",
            None,
            fallback_value=asset_node.properties.get("stage"),
        )

        indication_nodes = self.query.related_nodes(
            asset_node.node_id, EdgeType.ASSET_TREATS_INDICATION, NodeType.INDICATION
        )
        if indication_nodes:
            self._set_from_node_property(builder, "indication", indication_nodes[0], fallback_value=indication_nodes[0].name)
        elif asset_node.properties.get("indication"):
            self._set_from_node_property(
                builder,
                "indication",
                None,
                fallback_value=asset_node.properties.get("indication"),
            )

        target_nodes = self.query.related_nodes(
            asset_node.node_id, EdgeType.ASSET_TARGETS_TARGET, NodeType.TARGET
        )
        if target_nodes:
            self._set_from_node_property(builder, "target", target_nodes[0], fallback_value=target_nodes[0].name)

        mechanism_nodes = self.query.related_nodes(
            asset_node.node_id, EdgeType.HAS_MECHANISM, NodeType.MECHANISM
        )
        if mechanism_nodes:
            self._set_from_node_property(
                builder, "mechanism_of_action", mechanism_nodes[0], fallback_value=mechanism_nodes[0].name
            )

        trial_nodes = self.query.related_nodes(
            asset_node.node_id,
            EdgeType.TRIAL_BELONGS_TO_ASSET,
            NodeType.TRIAL,
            direction="incoming",
        )
        for trial_node in trial_nodes:
            props = trial_node.properties
            trial_summary = TrialSummary(
                nct_id=trial_node.external_id or trial_node.name,
                phase=str(props.get("phase") or "unknown"),
                status=str(props.get("status") or "unknown"),
                primary_endpoint=str(props.get("primary_endpoint") or "unknown"),
                enrollment_target=int(props.get("enrollment") or 0),
                estimated_completion=props.get("primary_completion_date"),
            )
            if trial_summary.status in {"completed", "terminated", "withdrawn"}:
                builder.add_prior_trial(trial_summary)
            else:
                builder.add_active_trial(trial_summary)

        if trial_nodes:
            latest_trial = sorted(
                trial_nodes,
                key=lambda node: str(node.properties.get("phase") or ""),
                reverse=True,
            )[0]
            self._set_from_node_property(
                builder,
                "endpoint_type",
                None,
                fallback_value=latest_trial.properties.get("endpoint_type"),
            )

        competitor_nodes = self.query.related_nodes(
            asset_node.node_id, EdgeType.COMPETITOR_OVERLAPS_ASSET, NodeType.COMPETITOR_PROGRAM
        )
        if competitor_nodes:
            names = ", ".join(node.name for node in competitor_nodes[:5])
            self._set_from_node_property(
                builder,
                "competition_summary",
                None,
                fallback_value=f"Live competitor map: {names}",
            )

        financing_nodes = self.query.related_nodes(
            company_node.node_id if company_node else asset_node.node_id,
            EdgeType.FINANCING_APPLIES_TO_COMPANY,
            NodeType.FINANCING_STATE,
        ) if company_node else []
        if financing_nodes and financing_nodes[0].properties.get("quarterly_burn_musd") is not None:
            self._set_from_node_property(
                builder,
                "quarterly_burn_musd",
                financing_nodes[0],
                property_name="quarterly_burn_musd",
            )
        elif company_node is not None and company_node.properties.get("burn_rate_millions_per_quarter") is not None:
            self._set_from_node_property(
                builder,
                "quarterly_burn_musd",
                company_node,
                property_name="burn_rate_millions_per_quarter",
            )
        if financing_nodes:
            self._set_from_node_property(
                builder,
                "cash_runway_months",
                financing_nodes[0],
                property_name="months_of_runway",
            )

        catalyst_nodes = self.query.related_nodes(
            asset_node.node_id,
            EdgeType.CATALYST_FOR_ASSET,
            NodeType.CATALYST,
            direction="incoming",
        )
        if catalyst_nodes:
            catalyst = sorted(
                catalyst_nodes,
                key=lambda node: str(node.properties.get("expected_date") or "9999-12-31"),
            )[0]
            self._set_from_node_property(
                builder,
                "next_catalyst_date",
                catalyst,
                property_name="expected_date",
            )
            self._set_from_node_property(
                builder,
                "next_catalyst_description",
                catalyst,
                fallback_value=catalyst.name,
            )

        thesis_nodes = self.query.related_nodes(
            asset_node.node_id,
            EdgeType.THESIS_SNAPSHOT_FOR_ASSET,
            NodeType.THESIS_SNAPSHOT,
            direction="incoming",
        )
        if thesis_nodes:
            self._set_from_node_property(
                builder,
                "thesis_summary",
                thesis_nodes[0],
                property_name="summary",
            )

        return builder.build()
