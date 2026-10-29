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

import contextlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
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


def _ontology_version() -> str | None:
    """The installed S&E ontology version, without loading it when it is not installed."""
    from bve.se.ontology.targets import default_snapshot_path

    manifest = default_snapshot_path() / "manifest.json"
    if not manifest.exists():
        return None
    try:
        return str(json.loads(manifest.read_text()).get("ontology_version") or manifest.stat().st_mtime)
    except (OSError, ValueError):
        return None


@contextlib.contextmanager
def _ontology_disabled() -> Iterator[None]:
    """Run with no S&E ontology snapshot installed, restoring the previous setting after."""
    from bve.se.ontology.targets import reset_resolver_cache

    key = "BVE_SE_ONTOLOGY_SNAPSHOT"
    previous = os.environ.get(key)
    with tempfile.TemporaryDirectory() as empty:
        os.environ[key] = str(Path(empty) / "none")
        reset_resolver_cache()
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
            reset_resolver_cache()


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
        target_normalizer: TargetNormalizer | None = None,
    ) -> ImportResult:
        profile = MappingProfile.from_yaml(profile_path)
        BuyerSpec.from_yaml(buyer_path)  # fail early on a bad spec
        result = import_landscape(landscape, profile, sheet=sheet)
        previous = self.import_result() if (self.root / "import.json").exists() else None
        flags = identity_flags(result.assets, authority=drug_authority)
        report = None
        if previous is not None or self.decisions_path.exists():
            from bve.dealscreen.refresh import refresh_report

            # Computed before anything is written, so a failure leaves the workspace intact.
            report = refresh_report(previous, result, self.decision_log().state, self.findings(), flags)
        if previous is not None:  # a refresh: keep the old import, never overwrite it silently
            history = self.root / "import_history"
            history.mkdir(parents=True, exist_ok=True)
            n = len(list(history.glob("import_*.json"))) + 1
            shutil.copyfile(self.root / "import.json", history / f"import_{n:03d}.json")
        self.inputs.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(landscape, self.inputs / f"landscape{landscape.suffix.lower()}")
        shutil.copyfile(profile_path, self.inputs / "profile.yaml")
        shutil.copyfile(buyer_path, self.inputs / "buyer.yaml")
        _dump(self.root / "import.json", result.model_dump(mode="json"))
        _dump(self.root / "identity.json", [f.model_dump(mode="json") for f in flags])
        if report is not None:
            _dump(self.root / "refresh_report.json", report)
        if target_normalizer is not None:
            self.write_target_cache(target_normalizer, result.assets, profile)
        return result

    # -- target cache (Cycle 4) -------------------------------------------------------
    @property
    def target_cache_path(self) -> Path:
        return self.root / "target_cache.json"

    def write_target_cache(self, normalizer: TargetNormalizer, assets: list[LandscapeAsset],
                           profile: MappingProfile) -> dict[str, str | None]:
        """Resolve every distinct target string (and the parts FactBuilder splits) once."""
        from bve.dealscreen.importer import split_list

        strings: set[str] = set()
        for asset in assets:
            for claim in asset.claims_for("target"):
                text = claim.value_as_written
                strings.update(split_list(text.replace("/", profile.list_separator), profile.list_separator))
        for term in self.buyer().problem.strategic_gap.target_expression.targets:
            strings.add(term.canonical_id)
        cache = {s: normalizer(s) for s in sorted(strings)}
        _dump(self.target_cache_path, cache)
        _dump(self.root / "target_cache_meta.json", {
            "ontology_version": _ontology_version(),
            "note": "Re-import to rebuild the cache after the S&E ontology snapshot changes.",
            "strings": len(cache)})
        return cache

    def cached_normalizer(self) -> TargetNormalizer | None:
        """A normalizer backed by the import-time cache; misses fall back to the ontology."""
        if not self.target_cache_path.exists():
            return None
        cache: dict[str, str | None] = json.loads(self.target_cache_path.read_text())

        def normalize(text: str) -> str | None:
            if text in cache:
                return cache[text]
            return ontology_target_normalizer()(text)  # P4: never null-by-default

        return normalize

    def can_screen_without_ontology(self) -> bool:
        """True when every buyer target id is already canonical per the cache (P2)."""
        if not self.target_cache_path.exists():
            return False
        cache = json.loads(self.target_cache_path.read_text())
        meta_path = self.root / "target_cache_meta.json"
        if meta_path.exists() and json.loads(meta_path.read_text()).get("ontology_version") != _ontology_version():
            return False  # the installed ontology changed since import: use the full path
        terms = self.buyer().problem.strategic_gap.target_expression.targets
        if not all(t.target_reference is None and cache.get(t.canonical_id) == t.canonical_id for t in terms):
            return False
        # Every target string a decision can introduce must already be cached, or the
        # ontology-free path would read it as "no target" (Cycle 4 review H1).
        from bve.dealscreen.importer import split_list

        sep = self.profile().list_separator
        state = self.decision_log().state
        confirmed = {f for f, s in state.findings.items() if s == "CONFIRMED"}
        strings = [a["value"] for a in state.assertions.values() if a["field"] == "target"]
        strings += [f.proposed_value for f in self.findings() if f.finding_id in confirmed and f.field == "target"]
        parts = {p for s in strings for p in split_list(s.replace("/", sep), sep)}
        return parts <= set(cache)

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

    def refresh(self) -> dict[str, Any]:
        path = self.root / "refresh_report.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def findings(self) -> list[AgentFinding]:
        path = self.root / "findings.json"
        return [AgentFinding(**f) for f in json.loads(path.read_text())] if path.exists() else []

    def decision_log(self) -> DecisionLog:
        return DecisionLog(self.decisions_path)

    def assets(self) -> list[LandscapeAsset]:
        return self.import_result().assets

    # -- step 2: screen ---------------------------------------------------------------
    def screen(self, target_normalizer: TargetNormalizer | None = None) -> ScreeningResult:
        """With no normalizer, use the import-time target cache and, when safe, skip loading
        the S&E ontology entirely (Cycle 4). Results are identical to the full path (tested)."""
        if target_normalizer is None:
            cached = self.cached_normalizer()
            if cached is None:
                return self._screen(ontology_target_normalizer())
            if self.can_screen_without_ontology():
                with _ontology_disabled():
                    return self._screen(cached)
            return self._screen(cached)
        return self._screen(target_normalizer)

    def _screen(self, target_normalizer: TargetNormalizer) -> ScreeningResult:
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

    def decision_context(self, target_normalizer: TargetNormalizer | None = None) -> DecisionContext:
        """``target_normalizer`` is only used to check asserted target values (lazy)."""
        spec = self.buyer()
        profile = self.profile()

        def readable(field_name: str, value: str) -> bool:
            normalizer = target_normalizer or self.cached_normalizer() or ontology_target_normalizer()
            return FactBuilder(profile, normalizer).readable(field_name, value)

        screening = self.screening()
        assets = self.assets()
        return DecisionContext(
            dispositions={s["asset_id"]: s["disposition"] for s in screening["screens"]},
            claim_ids={c.claim_id for a in assets for c in a.claims},
            finding_ids={f.finding_id for f in self.findings()},
            flag_ids={f.flag_id for f in self.flags()},
            max_finalists=spec.max_finalists,
            max_valuations=spec.max_valuations,
            readable=readable,
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
            readiness: Readiness = check_readiness(
                asset, block, screened_stage_order=screening[asset_id].get("stage_order"))
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
        (self.root / "valuation").mkdir(parents=True, exist_ok=True)
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
