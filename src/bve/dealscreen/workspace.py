"""A DealScreen workspace: one directory holding every step's inputs and outputs.

Layout::

    <workspace>/
      inputs/            copies of the landscape, mapping profile, buyer spec (never edited)
      import.json        ImportResult: manifest, raw rows, rejected rows, duplicates, assets
      identity.json      identity flags (shared codes, proposed merges)
      findings.json      agent findings (proposals only)
      decisions.jsonl    analyst decision log (append-only, hash-chained)
      screening.json     latest screening result (deterministic for identical inputs)
      valuation/         per-asset configs and saved valuation.json files
      deliverables/      workbook and memo

Screening is re-run from inputs plus the decision log, so a reloaded workspace reproduces
the same screen and nothing is lost between sessions.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from bve.dealscreen.agent import DiligenceProvider, Question
from bve.dealscreen.buyer import BuyerSpec
from bve.dealscreen.facts import FactBuilder, TargetNormalizer
from bve.dealscreen.identity import DrugAuthority, identity_flags
from bve.dealscreen.importer import import_landscape
from bve.dealscreen.mapping import MappingProfile
from bve.dealscreen.models import AgentFinding, IdentityFlag, ImportResult, LandscapeAsset
from bve.dealscreen.review import DecisionContext, DecisionLog
from bve.dealscreen.screening import ScreeningResult, screen_landscape
from bve.dealscreen.valuation_handoff import (
    Readiness,
    ValuationRun,
    build_config,
    check_readiness,
    run_valuation,
    scenario_check,
)


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def ontology_target_normalizer() -> TargetNormalizer:
    """The S&E target authority (HGNC symbols; ambiguity -> None). Loads lazily (~30 s)."""
    from bve.se.ontology.targets import normalize_target

    return normalize_target


def ontology_drug_authority() -> DrugAuthority:
    from bve.se.ontology.records import EntityType
    from bve.se.ontology.resolver import ResolutionStatus
    from bve.se.ontology.targets import get_resolver

    resolver = get_resolver()

    def resolve(name: str) -> str | None:
        if resolver is None:
            return None
        result = resolver.resolve(name, EntityType.DRUG)
        return result.canonical_id if result.status is ResolutionStatus.RESOLVED else None

    return resolve


class Workspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # -- paths ------------------------------------------------------------------------
    @property
    def inputs(self) -> Path:
        return self.root / "inputs"

    @property
    def decisions_path(self) -> Path:
        return self.root / "decisions.jsonl"

    @property
    def deliverables(self) -> Path:
        return self.root / "deliverables"

    def _input(self, name: str) -> Path:
        matches = sorted(self.inputs.glob(f"{name}.*"))
        if not matches:
            raise FileNotFoundError(f"{self.root}: run `import` first (missing inputs/{name}.*)")
        return matches[0]

    # -- step 1: import ---------------------------------------------------------------
    def import_landscape(
        self, landscape: Path, profile_path: Path, buyer_path: Path, *, sheet: str | None = None,
        drug_authority: DrugAuthority | None = None,
    ) -> ImportResult:
        profile = MappingProfile.from_yaml(profile_path)
        BuyerSpec.from_yaml(buyer_path)  # fail early on a bad spec
        result = import_landscape(landscape, profile, sheet=sheet)
        self.inputs.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(landscape, self.inputs / f"landscape{landscape.suffix.lower()}")
        shutil.copyfile(profile_path, self.inputs / "profile.yaml")
        shutil.copyfile(buyer_path, self.inputs / "buyer.yaml")
        _dump(self.root / "import.json", result.model_dump(mode="json"))
        flags = identity_flags(result.assets, authority=drug_authority)
        _dump(self.root / "identity.json", [f.model_dump(mode="json") for f in flags])
        return result

    # -- loaders ----------------------------------------------------------------------
    def import_result(self) -> ImportResult:
        return ImportResult.model_validate_json((self.root / "import.json").read_text(encoding="utf-8"))

    def profile(self) -> MappingProfile:
        return MappingProfile.from_yaml(self._input("profile"))

    def buyer(self) -> BuyerSpec:
        return BuyerSpec.from_yaml(self._input("buyer"))

    def flags(self) -> list[IdentityFlag]:
        path = self.root / "identity.json"
        return [IdentityFlag(**f) for f in json.loads(path.read_text())] if path.exists() else []

    def findings(self) -> list[AgentFinding]:
        path = self.root / "findings.json"
        return [AgentFinding(**f) for f in json.loads(path.read_text())] if path.exists() else []

    def decision_log(self) -> DecisionLog:
        return DecisionLog(self.decisions_path)

    def assets(self) -> list[LandscapeAsset]:
        return self.import_result().assets

    # -- step 2: screen ---------------------------------------------------------------
    def screen(self, target_normalizer: TargetNormalizer) -> ScreeningResult:
        spec = self.buyer()
        log = self.decision_log()
        review = log.state.review_inputs(self.findings())
        result = screen_landscape(
            self.assets(), spec, FactBuilder(self.profile(), target_normalizer),
            review=review, identity_flags=self.flags(),
        )
        _dump(self.root / "screening.json", result.to_dict())
        return result

    def screening(self) -> dict[str, Any]:
        return json.loads((self.root / "screening.json").read_text(encoding="utf-8"))

    def decision_context(self) -> DecisionContext:
        spec = self.buyer()
        screening = self.screening()
        assets = self.assets()
        return DecisionContext(
            dispositions={s["asset_id"]: s["disposition"] for s in screening["screens"]},
            claim_ids={c.claim_id for a in assets for c in a.claims},
            finding_ids={f.finding_id for f in self.findings()},
            flag_ids={f.flag_id for f in self.flags()},
            max_finalists=spec.max_finalists,
            max_valuations=spec.max_valuations,
        )

    # -- step 3: research -------------------------------------------------------------
    def research(
        self, provider: DiligenceProvider, asset_ids: list[str], questions: list[Question]
    ) -> list[AgentFinding]:
        by_id = {a.asset_id: a for a in self.assets()}
        existing = {f.finding_id: f for f in self.findings()}
        new: list[AgentFinding] = []
        for asset_id in asset_ids:
            if asset_id not in by_id:
                raise KeyError(f"unknown asset {asset_id}")
            for question in questions:
                for finding in provider.investigate(by_id[asset_id], question):
                    if finding.finding_id not in existing:
                        existing[finding.finding_id] = finding
                        new.append(finding)
        _dump(self.root / "findings.json",
              [existing[k].model_dump(mode="json") for k in sorted(existing)])
        return new

    # -- step 4: valuation ------------------------------------------------------------
    def value_selected(
        self, assumptions_path: Path, *, n_sims: int = 5_000, seed: int = 42,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        assumptions_doc = yaml.safe_load(assumptions_path.read_text(encoding="utf-8")) or {}
        shutil.copyfile(assumptions_path, self.inputs / "valuation_assumptions.yaml")
        per_asset: dict[str, Any] = assumptions_doc.get("assets", {})
        log = self.decision_log()
        by_id = {a.asset_id: a for a in self.assets()}
        screening = {s["asset_id"]: s for s in self.screening()["screens"]}
        results: dict[str, Any] = {"label": assumptions_doc.get("label"),
                                   "owner": assumptions_doc.get("owner"), "assets": {}}
        # Readiness is reported for every finalist; only selected, ready ones are run.
        for asset_id in sorted(log.state.finalists):
            asset = by_id[asset_id]
            selected = asset_id in log.state.valuation_selected
            block = per_asset.get(asset.external_id)
            if block is not None:
                block = {"owner": assumptions_doc.get("owner"), "label": assumptions_doc.get("label"), **block}
            readiness: Readiness = check_readiness(asset, block)
            entry: dict[str, Any] = {"selected": selected, "readiness": asdict(readiness), "runs": []}
            if selected and readiness.ready and block is not None:
                indication = ", ".join(
                    f["value"] if isinstance(f["value"], str) else "; ".join(f["value"])
                    for f in screening[asset_id]["facts"] if f["fact_type"] == "indication"
                ) or "not reported"
                stage_check = _stage_warning(screening[asset_id], block["stage"])
                if stage_check:
                    readiness.warnings.append(stage_check)
                    entry["readiness"] = asdict(readiness)
                cases: list[tuple[str, dict[str, Any] | None]] = [("standalone", None)]
                cases += [(name, deal) for name, deal in (block.get("deal_options") or {}).items()]
                for case, deal in cases:
                    if progress:
                        progress(f"valuing {asset.program_name} [{case}]")
                    config = build_config(asset, block, indication_label=indication, deal=deal)
                    run: ValuationRun = run_valuation(
                        config, self.root / "valuation" / asset_id.replace(":", "-"),
                        case=case, n_sims=n_sims, seed=seed, asset_id=asset_id,
                    )
                    entry["runs"].append({**asdict(run), "deal_terms": deal,
                                          "scenario_check": scenario_check(run.summary, deal)})
            results["assets"][asset_id] = entry
        _dump(self.root / "valuation" / "valuations.json", results)
        return results

    def valuations(self) -> dict[str, Any]:
        path = self.root / "valuation" / "valuations.json"
        return json.loads(path.read_text()) if path.exists() else {"assets": {}}


_STAGE_ORDER = {"preclinical": 1, "phase_1": 2, "phase_2": 3, "phase_3": 4, "nda_bla": 5, "approved": 6}


def _stage_warning(screen: dict[str, Any], stage: str) -> str | None:
    observed = screen.get("stage_order")
    expected = _STAGE_ORDER.get(stage)
    if observed is None or expected is None or observed == expected:
        return None
    return (f"Analyst valuation stage {stage!r} differs from the screened source stage order "
            f"{observed}; check which is current before relying on the valuation.")
