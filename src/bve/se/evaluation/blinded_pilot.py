"""Blinded Search & Evaluation pilot benchmark.

Two phases, run in this order and never merged:

1. ``seal`` -- hashes the analyst's search spec, the predeclared criteria and the engine's
   exported candidates into a receipt. Nothing in this phase reads a reference dataset.
2. ``score`` -- verifies the receipt, then (and only then) opens the hidden reference and
   scores the sealed candidates against it.

The scorer never self-certifies. A run is ``UNVALIDATED`` unless the supplied reference
declares itself independent of the engine; even then the verdict depends on that
reference's provenance, which this code cannot verify.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bve.se.pipeline import SESearchResult

RECEIPT_VERSION = "blinded-pilot-v1"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------------- analyst inputs (sealed)
class PilotSearchSpec(_Frozen):
    """What the analyst asks the engine to find. Must not name any expected asset."""

    spec_id: str
    therapeutic_area: str
    indications: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    as_of_date: date
    query_text: str


class Thresholds(_Frozen):
    min_precision: float = Field(ge=0.0, le=1.0)
    min_recall: float = Field(ge=0.0, le=1.0)
    min_trial_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    max_identity_errors: int = Field(default=0, ge=0)
    max_misleading_claims: int = Field(default=0, ge=0)


class EvaluationCriteria(_Frozen):
    """Declared before the reference is opened; its hash is in the receipt."""

    criteria_id: str
    spec_id: str
    thresholds: Thresholds
    #: Precision denominator: count every unmatched candidate as false ("strict"), or
    #: report it as unadjudicated and exclude it ("adjudicated_only"). Both are always
    #: reported; this picks which one the pass/fail verdict uses.
    precision_basis: Literal["strict", "adjudicated_only"] = "strict"


# ----------------------------------------------------------------- engine output (sealed)
class CandidateClaim(_Frozen):
    kind: Literal["scientific", "commercial"]
    field: str
    value: str
    citations: list[str] = Field(default_factory=list)


class PilotCandidate(_Frozen):
    candidate_id: str
    names: list[str] = Field(min_length=1)
    target_ids: list[str] = Field(default_factory=list)
    modality: str | None = None
    trial_ids: list[str] = Field(default_factory=list)
    claims: list[CandidateClaim] = Field(default_factory=list)


class CandidateExport(_Frozen):
    spec_id: str
    engine_commit: str
    candidates: list[PilotCandidate]


# ----------------------------------------------------------------- hidden reference
class ReferenceProvenance(_Frozen):
    prepared_by: str
    organization: str = ""
    prepared_on: date
    method: str
    independent_of_engine: bool
    synthetic: bool = False


class ReferenceFact(_Frozen):
    field: str
    value: str


class ReferenceAsset(_Frozen):
    reference_id: str
    names: list[str] = Field(min_length=1)
    #: False marks a negative control: a plausible asset that does NOT meet the spec.
    in_scope: bool = True
    target_ids: list[str] = Field(default_factory=list)
    modality: str | None = None
    trial_ids: list[str] = Field(default_factory=list)
    facts: list[ReferenceFact] = Field(default_factory=list)


class ReferenceDataset(_Frozen):
    reference_id: str
    spec_id: str
    provenance: ReferenceProvenance
    assets: list[ReferenceAsset]


# ----------------------------------------------------------------- receipt / report
class SealReceipt(_Frozen):
    version: str = RECEIPT_VERSION
    spec_sha256: str
    criteria_sha256: str
    candidates_sha256: str
    spec_id: str
    sealed_at: str
    scorer_commit: str


class PilotReport(BaseModel):
    status: Literal["UNVALIDATED", "SYNTHETIC_SELF_TEST", "SCORED_AGAINST_SUPPLIED_REFERENCE"]
    status_note: str
    receipt: SealReceipt
    reference_id: str
    reference_sha256: str
    n_candidates: int
    n_reference_in_scope: int
    true_positives: list[str]
    false_negatives: list[str]
    negative_control_hits: list[str]
    unadjudicated_candidates: list[str]
    precision_strict: float | None
    precision_adjudicated: float | None
    recall: float | None
    target_accuracy: float | None
    target_unknown: int
    modality_accuracy: float | None
    modality_unknown: int
    trial_coverage: float | None
    unreferenced_trials: int
    merge_errors: list[str]
    split_errors: list[str]
    claims_total: int
    claims_cited: int
    claims_supported: int
    claims_unverifiable: int
    misleading_claims: list[str]
    passes_thresholds: bool | None
    not_auto_scored: list[str]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


# ----------------------------------------------------------------- engine adapter
def export_candidates(
    result: SESearchResult, *, spec_id: str, engine_commit: str
) -> CandidateExport:
    """Convert a saved engine run into the sealed candidate format. Reads no labels."""
    doc_by_claim = {claim.claim_id: claim.source_document_id for claim in result.claims}
    facts_by_subject: dict[str, list[CandidateClaim]] = {}
    for fact in result.facts:
        citations = sorted(
            {doc_by_claim[c] for c in fact.supporting_claim_ids if c in doc_by_claim}
        )
        kind: Literal["scientific", "commercial"] = (
            "commercial"
            if fact.fact_type.startswith(("owner", "rights", "deal", "licens"))
            else "scientific"
        )
        facts_by_subject.setdefault(fact.subject_id, []).append(
            CandidateClaim(
                kind=kind, field=fact.fact_type, value=str(fact.value), citations=citations
            )
        )
    candidates = [
        PilotCandidate(
            candidate_id=asset.asset_id,
            names=[asset.canonical_name, *asset.aliases],
            target_ids=list(asset.target_ids),
            modality=asset.authority_modality,
            trial_ids=list(asset.trial_ids),
            claims=facts_by_subject.get(asset.asset_id, []),
        )
        for asset in result.candidates
    ]
    return CandidateExport(spec_id=spec_id, engine_commit=engine_commit, candidates=candidates)


# ----------------------------------------------------------------- phase 1: seal
def seal(spec_path: Path, criteria_path: Path, candidates_path: Path) -> SealReceipt:
    spec = PilotSearchSpec.model_validate_json(spec_path.read_text())
    criteria = EvaluationCriteria.model_validate_json(criteria_path.read_text())
    export = CandidateExport.model_validate_json(candidates_path.read_text())
    if not (spec.spec_id == criteria.spec_id == export.spec_id):
        raise ValueError("spec, criteria and candidates must share one spec_id")
    return SealReceipt(
        spec_sha256=sha256_file(spec_path),
        criteria_sha256=sha256_file(criteria_path),
        candidates_sha256=sha256_file(candidates_path),
        spec_id=spec.spec_id,
        sealed_at=datetime.now(UTC).isoformat(),
        scorer_commit=_git_commit(),
    )


# ----------------------------------------------------------------- phase 2: score
def _verify(receipt: SealReceipt, spec: Path, criteria: Path, candidates: Path) -> None:
    pairs = [
        ("spec", receipt.spec_sha256, spec),
        ("criteria", receipt.criteria_sha256, criteria),
        ("candidates", receipt.candidates_sha256, candidates),
    ]
    for label, expected, path in pairs:
        if sha256_file(path) != expected:
            raise ValueError(f"{label} changed after sealing; re-run discovery and re-seal")


def _reject_in_repo(reference_path: Path, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    try:
        reference_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return
    raise ValueError(
        "reference dataset is inside the engine repository; keep it outside so discovery "
        "and tuning cannot read it"
    )


def _status(prov: ReferenceProvenance) -> tuple[str, str]:
    if prov.synthetic:
        return (
            "SYNTHETIC_SELF_TEST",
            "Synthetic fixture: tests the scorer, says nothing about the engine.",
        )
    if not prov.independent_of_engine or not prov.prepared_by.strip():
        return "UNVALIDATED", "Reference does not declare an independent human preparer."
    return (
        "SCORED_AGAINST_SUPPLIED_REFERENCE",
        (
            "Scored against an externally supplied reference. Validity rests on that "
            "reference's provenance, which this tool does not verify."
        ),
    )


def score(
    receipt: SealReceipt,
    *,
    spec_path: Path,
    criteria_path: Path,
    candidates_path: Path,
    reference_path: Path,
    repo_root: Path | None,
) -> PilotReport:
    _verify(receipt, spec_path, criteria_path, candidates_path)
    _reject_in_repo(reference_path, repo_root)
    criteria = EvaluationCriteria.model_validate_json(criteria_path.read_text())
    export = CandidateExport.model_validate_json(candidates_path.read_text())
    reference = ReferenceDataset.model_validate_json(reference_path.read_text())
    if reference.spec_id != receipt.spec_id:
        raise ValueError("reference was prepared for a different search spec")
    status, note = _status(reference.provenance)
    return _compute(receipt, criteria, export, reference, sha256_file(reference_path), status, note)


def _match(export: CandidateExport, reference: ReferenceDataset) -> dict[str, set[str]]:
    key_owner: dict[str, set[str]] = {}
    for ref in reference.assets:
        for name in ref.names:
            key_owner.setdefault(_norm(name), set()).add(ref.reference_id)
    return {
        cand.candidate_id: set().union(*(key_owner.get(_norm(n), set()) for n in cand.names))
        for cand in export.candidates
    }


def _compute(
    receipt: SealReceipt,
    criteria: EvaluationCriteria,
    export: CandidateExport,
    reference: ReferenceDataset,
    reference_sha: str,
    status: str,
    note: str,
) -> PilotReport:
    refs = {r.reference_id: r for r in reference.assets}
    in_scope = {rid for rid, r in refs.items() if r.in_scope}
    matches = _match(export, reference)
    merge_errors = sorted(cid for cid, rids in matches.items() if len(rids) > 1)
    hits_by_ref: dict[str, list[str]] = {}
    for cid, rids in matches.items():
        for rid in rids:
            hits_by_ref.setdefault(rid, []).append(cid)
    split_errors = sorted(rid for rid, cids in hits_by_ref.items() if len(cids) > 1)
    tp = sorted(rid for rid in in_scope if rid in hits_by_ref)
    fn = sorted(in_scope - set(tp))
    control_hits = sorted(rid for rid in hits_by_ref if rid not in in_scope)
    unadjudicated = sorted(cid for cid, rids in matches.items() if not rids)
    tp_candidates = [cid for cid, rids in matches.items() if rids & in_scope]
    n = len(export.candidates)
    adjudicated = n - len(unadjudicated)

    t_ok = t_unknown = m_ok = m_unknown = scored = trial_hit = trial_den = extra_trials = 0
    trials_by_ref: dict[str, set[str]] = {}
    claims_total = cited = supported = unverifiable = 0
    misleading: list[str] = []
    for cand in export.candidates:
        rids = matches[cand.candidate_id]
        ref = refs[next(iter(rids))] if len(rids) == 1 else None
        for claim in cand.claims:
            claims_total += 1
            cited += bool(claim.citations)
            truth = [f.value for f in ref.facts if f.field == claim.field] if ref else []
            if not truth:
                unverifiable += 1
            elif _norm(claim.value) in {_norm(v) for v in truth}:
                supported += 1
            else:
                misleading.append(f"{cand.candidate_id}:{claim.kind}:{claim.field}={claim.value}")
        if ref is None or not ref.in_scope:
            continue
        scored += 1
        if not cand.target_ids:
            t_unknown += 1
        elif {_norm(t) for t in cand.target_ids} == {_norm(t) for t in ref.target_ids}:
            t_ok += 1
        if cand.modality is None:
            m_unknown += 1
        elif ref.modality and _norm(cand.modality) == _norm(ref.modality):
            m_ok += 1
        # Pooled per reference asset, so a split identity is not double-counted here.
        trials_by_ref.setdefault(ref.reference_id, set()).update(t.upper() for t in cand.trial_ids)

    for rid, got in trials_by_ref.items():
        ref_trials = {t.upper() for t in refs[rid].trial_ids}
        trial_den += len(ref_trials)
        trial_hit += len(ref_trials & got)
        extra_trials += len(got - ref_trials)
    p_strict = _ratio(len(tp_candidates), n)
    p_adj = _ratio(len(tp_candidates), adjudicated)
    recall = _ratio(len(tp), len(in_scope))
    trial_cov = _ratio(trial_hit, trial_den)
    th = criteria.thresholds
    precision = p_strict if criteria.precision_basis == "strict" else p_adj
    passes = (
        None
        if status == "UNVALIDATED"
        else (
            (precision or 0.0) >= th.min_precision
            and (recall or 0.0) >= th.min_recall
            and (trial_cov if trial_cov is not None else 1.0) >= th.min_trial_coverage
            and len(merge_errors) + len(split_errors) <= th.max_identity_errors
            and len(misleading) <= th.max_misleading_claims
        )
    )
    return PilotReport(
        status=status,  # type: ignore[arg-type]
        status_note=note,
        receipt=receipt,
        reference_id=reference.reference_id,
        reference_sha256=reference_sha,
        n_candidates=n,
        n_reference_in_scope=len(in_scope),
        true_positives=tp,
        false_negatives=fn,
        negative_control_hits=control_hits,
        unadjudicated_candidates=unadjudicated,
        precision_strict=p_strict,
        precision_adjudicated=p_adj,
        recall=recall,
        target_accuracy=_ratio(t_ok, scored - t_unknown),
        target_unknown=t_unknown,
        modality_accuracy=_ratio(m_ok, scored - m_unknown),
        modality_unknown=m_unknown,
        trial_coverage=trial_cov,
        unreferenced_trials=extra_trials,
        merge_errors=merge_errors,
        split_errors=split_errors,
        claims_total=claims_total,
        claims_cited=cited,
        claims_supported=supported,
        claims_unverifiable=unverifiable,
        misleading_claims=sorted(misleading),
        passes_thresholds=passes,
        not_auto_scored=[
            "whether cited sources actually support each claim (needs a human reader)",
            "unadjudicated candidates: real misses in the reference vs engine false positives",
            "unreferenced trials: correct additions vs wrong attributions",
            "claims on fields the reference does not cover",
        ],
    )
