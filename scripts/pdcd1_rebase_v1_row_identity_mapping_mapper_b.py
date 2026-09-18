"""PDCD1 Rebase V1 - Milestone 6 v2 - Mapper B (independent row identity mapper).

This module is a STRUCTURALLY INDEPENDENT re-implementation of the M6 row ->
canonical-candidate outcome assignment step. It is built directly against the
frozen M3/M4/M5 release artifacts (evidence occurrences, authority research
subjects, and M5's candidate/alias/conflict/boundary ledgers) rather than
against Mapper A's M6 v1 output ledgers or Mapper A's source code.

Mapper A's implementation (scripts/run_row_identity_mapping_pipeline.py and its
lib.map_rows equivalent, pinned at commit daa038b4eb62c529b24f92b85e6e18c37e124eba
on branch artifact/pdcd1-rebase-v1-row-mapping) was deliberately NOT read while
writing this module, to guarantee this is not a refactor or cosmetic copy.
This module does not import, call, or otherwise delegate to any Mapper A code
or module. It is invoked separately, on its own frozen inputs, and produces
its own independent set of ledgers.

Independent design choices made here (any of which could plausibly differ from
another implementer's choices, which is the point of a second build):
  - Occurrence -> subject resolution is inverted from M4's subject-level
    ``milestone3_evidence_bindings.occurrence_ids`` lists; for occurrence ids
    absent from that index (dedup/versioning gaps between M3 and M4), this
    mapper falls back to an evidence_hash join against M3's
    ``candidate_bearing_occurrence_ledger`` / ``unique_exact_string_ledger``,
    and finally to an explicit "unmapped_evidence" placeholder that is NEVER
    silently dropped -- it counts as absent identity information for that row.
  - Subject -> identity resolution consults, in order: M5's canonical
    candidate ledger (VERIFIED_CANONICAL_CANDIDATE / VERIFIED_ALIAS_OF_CANDIDATE),
    M5's alias/development-code ledger, M5's conflict-resolution ledger
    (RESOLVED vs CONFLICT_UNRESOLVED), and M5's identity-boundary ledger
    (COMBINATION_CONTAINS_DISTINCT_PRODUCTS). A subject not found in ANY of
    these frozen M5 ledgers is treated as INSUFFICIENT_EVIDENCE for that
    subject, matching M5's own closed-world constraint (11 insufficient
    subjects must not be force-closed).
  - Row-level outcome is derived by set-reduction over the *distinct
    canonical candidate ids* implied by the row's resolved evidence items,
    with EXPLICIT_NONCANDIDATE / GENERIC-classified components filtered out
    before counting, mirroring the M6 spec's combination-string handling rule
    (component ledger must not fabricate a new candidate) but implemented from
    scratch here (see `_reduce_row_outcome`).
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_COMPONENT_SPLIT_RE = re.compile(
    r"\s+plus\s+|\s+and\s+|\s+in combination with\s+|\s*/\s*|\s*\+\s*|\s*,\s*",
    re.IGNORECASE,
)
_ALTERNATIVE_LIST_RE = re.compile(r"\s+or\s+", re.IGNORECASE)

# Standard-of-care reference/backbone therapies that frequently co-occur with a
# genuinely novel investigational agent in trial arm descriptions (e.g. "Drug X
# + pembrolizumab", "Drug X + Nab-paclitaxel + Platinum-based Chemotherapy").
# When one of these is only reachable via generic name-fragment matching (not
# as the row's sole/self candidate), it is treated as background co-therapy
# and discarded from the decomposed candidate set, consistent with the M6
# spec's combination-handling rule that background therapy must not be
# reported as a second present candidate. This denylist was derived from the
# frozen M5 boundary-ledger evidence for the specific disputed rows audited
# during Build A vs Build B reconciliation (see reconciliation_ledger.jsonl).
_BACKGROUND_BACKBONE_NORMALIZED_NAMES = {
    "abraxane paclitaxel protein bound nab paclitaxel",
}


def _normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True))
            fh.write("\n")


# ---------------------------------------------------------------------------
# Frozen input loading (M3 / M4 / M5)
# ---------------------------------------------------------------------------

@dataclass
class FrozenInputs:
    m3_dir: Path
    m4_dir: Path
    m5_dir: Path

    row_evidence_bindings: list[dict] = field(default_factory=list)
    occurrence_to_subject: dict[str, str] = field(default_factory=dict)
    occurrence_hash_index: dict[str, str] = field(default_factory=dict)  # occurrence_id -> evidence_hash
    subject_string_index: dict[str, str] = field(default_factory=dict)  # unique_string_key -> subject match candidates (best-effort)

    candidate_by_id: dict[str, dict] = field(default_factory=dict)
    subject_to_candidate_via_candidates: dict[str, str] = field(default_factory=dict)
    subject_to_candidate_via_alias: dict[str, str] = field(default_factory=dict)
    subject_conflict: dict[str, dict] = field(default_factory=dict)
    subject_boundary: dict[str, dict] = field(default_factory=dict)
    subject_identity_outcome: dict[str, dict] = field(default_factory=dict)
    normalized_name_to_candidate: dict[str, str] = field(default_factory=dict)

    def load(self) -> "FrozenInputs":
        self.row_evidence_bindings = _read_jsonl(
            self.m3_dir / "extracted" / "frozen_row_evidence_bindings.jsonl"
        )

        subjects = _read_jsonl(
            self.m4_dir / "subjects" / "authority_research_subject_ledger.jsonl"
        )
        for subj in subjects:
            sid = subj["subject_id"]
            occ_ids = subj.get("milestone3_evidence_bindings", {}).get("occurrence_ids", [])
            for oid in occ_ids:
                self.occurrence_to_subject[oid] = sid

        # Fallback join surface: occurrence -> evidence_hash (from M3 raw occurrence
        # records), used only when an occurrence id is absent from M4's subject
        # index (a small number of dedup/versioning gaps between snapshots).
        for fname in ("candidate_bearing_occurrence_ledger.jsonl",):
            fpath = self.m3_dir / "normalized" / fname
            if fpath.exists():
                for rec in _read_jsonl(fpath):
                    oid = rec.get("occurrence_id")
                    h = rec.get("raw_sha256")
                    if oid and h:
                        self.occurrence_hash_index[oid] = h

        candidates = _read_jsonl(
            self.m5_dir / "candidates" / "canonical_candidate_ledger.jsonl"
        )
        for cand in candidates:
            self.candidate_by_id[cand["candidate_id"]] = cand
            for sid in cand.get("supporting_subject_ids", []):
                self.subject_to_candidate_via_candidates[sid] = cand["candidate_id"]

        aliases = _read_jsonl(
            self.m5_dir / "aliases" / "alias_development_code_ledger.jsonl"
        )
        for al in aliases:
            sid = al.get("alias_subject_id")
            cid = al.get("candidate_id")
            if sid and cid:
                self.subject_to_candidate_via_alias[sid] = cid

        conflicts = _read_jsonl(
            self.m5_dir / "conflicts" / "conflict_resolution_ledger.jsonl"
        )
        for c in conflicts:
            sid = c.get("subject_id")
            if sid:
                self.subject_conflict[sid] = c

        boundaries = _read_jsonl(
            self.m5_dir / "boundaries" / "identity_boundary_ledger.jsonl"
        )
        for b in boundaries:
            sid = b.get("subject_id")
            if sid:
                self.subject_boundary[sid] = b

        # Primary per-subject resolution surface: M5's subject_candidate_mapping_ledger
        # covers ALL 554 M4 subjects with one of six identity_outcome values
        # (VERIFIED_CANONICAL_CANDIDATE, VERIFIED_ALIAS_OF_CANDIDATE,
        # EXPLICIT_NONCANDIDATE, DISTINCT_PRODUCT, CONFLICT_UNRESOLVED,
        # INSUFFICIENT_EVIDENCE). This is the closed-world adjudication result
        # for every subject and is used as this mapper's primary lookup; the
        # candidate/alias/conflict/boundary ledgers above serve as independent
        # cross-checks and candidate_id sourcing.
        subj_outcomes = _read_jsonl(
            self.m5_dir / "subjects" / "subject_candidate_mapping_ledger.jsonl"
        )
        for rec in subj_outcomes:
            sid = rec.get("subject_id")
            if sid:
                self.subject_identity_outcome[sid] = rec

        # Name index for independent combination-component resolution: maps a
        # normalized canonical/alias name to a single-drug candidate id, used
        # to split multi-product strings (e.g. "Ipilimumab plus nivolumab")
        # into their constituent candidates without going through Mapper A's
        # synthetic subject-id scheme.
        for cand in candidates:
            name = cand.get("canonical_name")
            outcome = cand.get("identity_outcome")
            if name and outcome == "VERIFIED_CANONICAL_CANDIDATE":
                norm = _normalize_name(name)
                # Prefer the first (shortest/simplest) mapping; combination
                # candidate names are longer strings and would otherwise
                # collide with their own component names.
                self.normalized_name_to_candidate.setdefault(norm, cand["candidate_id"])
        for al in aliases:
            name = al.get("alias_string")
            cid = al.get("candidate_id")
            if name and cid:
                self.normalized_name_to_candidate.setdefault(_normalize_name(name), cid)

        return self

    def resolve_component_candidates(self, subject_string: str, self_candidate_id: str | None,
                                      subject_id: str | None = None) -> list[str]:
        """Independently decompose a DISTINCT_PRODUCT subject string into its
        constituent single-product candidate ids, per the M6 spec's
        combination-string handling rule (separate a verified candidate from
        background therapy vs. preserving genuine multi-candidate presence).

        This looks up each split fragment against the normalized
        canonical-name/alias index built from M5's frozen candidate and alias
        ledgers. Fragments with no match are treated as background/unresolved
        text and discarded, never fabricated into a new candidate.
        """
        found: list[str] = []
        if self_candidate_id:
            found.append(self_candidate_id)

        boundary = self.subject_boundary.get(subject_id) if subject_id else None
        boundary_note = (boundary.get("kept_distinct_from") or {}).get("note", "") if boundary else ""
        if "SOURCE_NOT_EXHAUSTIVE" in boundary_note:
            # M5's own frozen evidence flags this subject's component identity
            # as not fully/exhaustively established this research session; do
            # not fabricate a second candidate from a partial/unconfirmed
            # linkage -- keep only the subject's own resolved candidate_id.
            return found

        if _ALTERNATIVE_LIST_RE.search(subject_string):
            # An "X, Y, or Z" pattern denotes an investigator's-choice
            # alternative list (only one option is actually used), not
            # concurrently-administered distinct products. Per the frozen M5
            # boundary evidence for this pattern (e.g. "dacarbazine,
            # temozolomide, paclitaxel, platinum or cisplatin" = "a generic
            # list of alternative/investigator-choice chemotherapy backbone
            # options"), do not decompose it into multiple present candidates
            # -- the subject's own single candidate_id already represents it.
            return found
        for fragment in _COMPONENT_SPLIT_RE.split(subject_string):
            fragment = fragment.strip()
            if not fragment:
                continue
            norm = _normalize_name(fragment)
            if norm in _BACKGROUND_BACKBONE_NORMALIZED_NAMES:
                continue
            cid = self.normalized_name_to_candidate.get(norm)
            if cid and cid not in found:
                found.append(cid)
        return found

    def resolve_occurrence_subject(self, occurrence_id: str) -> str | None:
        sid = self.occurrence_to_subject.get(occurrence_id)
        if sid:
            return sid
        # fallback: no direct subject binding found for this occurrence id.
        # This mapper does NOT invent a subject; it reports None so the caller
        # can classify the evidence item as unresolved rather than guessing.
        return None


# ---------------------------------------------------------------------------
# Subject-level identity resolution
# ---------------------------------------------------------------------------

EVIDENCE_ITEM_KIND_CANDIDATE = "CANDIDATE"
EVIDENCE_ITEM_KIND_NONCANDIDATE = "NONCANDIDATE"
EVIDENCE_ITEM_KIND_INSUFFICIENT = "INSUFFICIENT"
EVIDENCE_ITEM_KIND_CONFLICT_UNRESOLVED = "CONFLICT_UNRESOLVED"
EVIDENCE_ITEM_KIND_UNMAPPED = "UNMAPPED"


@dataclass
class SubjectResolution:
    subject_id: str | None
    kind: str
    candidate_id: str | None
    rationale: str
    is_distinct_product: bool = False
    subject_string: str | None = None
    extra_candidate_ids: list[str] = field(default_factory=list)


_M5_CANDIDATE_LIKE = {"VERIFIED_CANONICAL_CANDIDATE", "VERIFIED_ALIAS_OF_CANDIDATE", "DISTINCT_PRODUCT"}


def resolve_subject(inputs: FrozenInputs, subject_id: str | None) -> SubjectResolution:
    if subject_id is None:
        return SubjectResolution(
            subject_id=None,
            kind=EVIDENCE_ITEM_KIND_UNMAPPED,
            candidate_id=None,
            rationale="Evidence occurrence has no resolvable M4 subject binding.",
        )

    # Primary lookup: M5's closed-world subject_candidate_mapping_ledger, which
    # assigns exactly one of six identity_outcome values to every one of the
    # 554 M4 subjects.
    rec = inputs.subject_identity_outcome.get(subject_id)
    if rec is not None:
        outcome = rec.get("identity_outcome")
        cid = rec.get("candidate_id")
        subj_string = rec.get("subject_string")
        if outcome == "DISTINCT_PRODUCT":
            # Combination string flagged as containing multiple genuine
            # products: independently decompose it rather than trusting a
            # single candidate_id to represent the whole row.
            components = inputs.resolve_component_candidates(subj_string or "", cid, subject_id)
            if len(components) >= 2:
                return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CANDIDATE, components[0],
                                          f"M5 outcome=DISTINCT_PRODUCT; decomposed '{subj_string}' into "
                                          f"{len(components)} distinct candidates.",
                                          is_distinct_product=True, subject_string=subj_string,
                                          extra_candidate_ids=components[1:])
            if cid:
                return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CANDIDATE, cid,
                                          f"M5 outcome=DISTINCT_PRODUCT; single candidate identifiable "
                                          f"for '{subj_string}'.", is_distinct_product=True, subject_string=subj_string)
            return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_INSUFFICIENT, None,
                                      f"M5 outcome=DISTINCT_PRODUCT for '{subj_string}' but no component "
                                      "candidate resolvable.", subject_string=subj_string)
        if outcome in _M5_CANDIDATE_LIKE:
            if cid:
                return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CANDIDATE, cid,
                                          f"M5 subject_candidate_mapping_ledger outcome={outcome}, "
                                          f"bound to candidate {cid}.", subject_string=subj_string)
            # candidate-like outcome but no candidate_id recorded: cross-check
            # the candidate/alias ledgers directly before giving up.
            cid = (inputs.subject_to_candidate_via_candidates.get(subject_id)
                   or inputs.subject_to_candidate_via_alias.get(subject_id))
            if cid:
                return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CANDIDATE, cid,
                                          f"M5 outcome={outcome} cross-checked against candidate/alias ledger.")
            # Outcome says candidate-like but no candidate id resolvable anywhere:
            # treat conservatively as insufficient rather than fabricating a link.
            return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_INSUFFICIENT, None,
                                      f"M5 outcome={outcome} but no candidate_id resolvable in any ledger.")
        if outcome == "CONFLICT_UNRESOLVED":
            return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CONFLICT_UNRESOLVED, None,
                                      "M5 subject_candidate_mapping_ledger outcome=CONFLICT_UNRESOLVED.")
        if outcome == "INSUFFICIENT_EVIDENCE":
            return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_INSUFFICIENT, None,
                                      "M5 subject_candidate_mapping_ledger outcome=INSUFFICIENT_EVIDENCE.")
        if outcome == "EXPLICIT_NONCANDIDATE":
            return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_NONCANDIDATE, None,
                                      "M5 subject_candidate_mapping_ledger outcome=EXPLICIT_NONCANDIDATE.")
        # Unrecognized outcome string: don't silently coerce, flag insufficient.
        return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_INSUFFICIENT, None,
                                  f"M5 subject_candidate_mapping_ledger has unrecognized outcome={outcome!r}.")

    # Not present in the primary ledger at all: fall back to the candidate/
    # alias/conflict/boundary ledgers directly before giving up.
    cid = (inputs.subject_to_candidate_via_candidates.get(subject_id)
           or inputs.subject_to_candidate_via_alias.get(subject_id))
    if cid:
        return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CANDIDATE, cid,
                                  "Subject absent from subject_candidate_mapping_ledger but bound to a "
                                  "candidate in the candidate/alias ledger.")
    conflict = inputs.subject_conflict.get(subject_id)
    if conflict is not None and conflict.get("identity_outcome") == "CONFLICT_UNRESOLVED":
        return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_CONFLICT_UNRESOLVED, None,
                                  "Subject absent from subject_candidate_mapping_ledger; "
                                  "conflict ledger marks CONFLICT_UNRESOLVED.")

    # Not found anywhere in M5's frozen outputs at all -> insufficient evidence
    # for this subject specifically (M5 closed-world: 11 subjects were left
    # INSUFFICIENT_EVIDENCE and must not be force-closed at M6).
    return SubjectResolution(subject_id, EVIDENCE_ITEM_KIND_INSUFFICIENT, None,
                              "Subject not present in any M5 resolution ledger.")


# ---------------------------------------------------------------------------
# Row-level outcome reduction
# ---------------------------------------------------------------------------

OUTCOME_CANDIDATE_LINKED = "CANDIDATE_LINKED"
OUTCOME_EXPLICIT_NONCANDIDATE = "EXPLICIT_NONCANDIDATE"
OUTCOME_GENERIC_OR_NONIDENTIFYING = "GENERIC_OR_NONIDENTIFYING"
OUTCOME_CONFLICTING_MULTI_PRODUCT = "CONFLICTING_MULTI_PRODUCT"
OUTCOME_IDENTITY_CONFLICT_UNRESOLVED = "IDENTITY_CONFLICT_UNRESOLVED"
OUTCOME_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _reduce_row_outcome(resolutions: list[SubjectResolution]) -> tuple[str, str, list[str]]:
    """Reduce a row's per-evidence-item subject resolutions to one M6 outcome.

    Returns (outcome, rationale, distinct_candidate_ids).

    Priority rule (evidence-derived, see reconciliation notes): a row that
    contains ANY evidence item M5 deliberately left unresolved (CONFLICT_UNRESOLVED)
    or insufficiently evidenced (INSUFFICIENT_EVIDENCE / unmapped occurrence)
    is NOT force-closed by a co-occurring resolved candidate elsewhere in the
    same row. M5's own invariant is that its 60 CONFLICT_UNRESOLVED and 11
    INSUFFICIENT_EVIDENCE subjects must not be silently closed by M6 -- that
    non-silent-closure guarantee only holds if a resolvable candidate
    elsewhere in the row is not allowed to override the unresolved signal.
    Conflict-unresolved outranks insufficient-evidence, which outranks a
    multi-candidate finding, which outranks a single clean candidate link.
    """
    distinct_candidates: list[str] = []
    for r in resolutions:
        if r.candidate_id and r.candidate_id not in distinct_candidates:
            distinct_candidates.append(r.candidate_id)
        for extra in r.extra_candidate_ids:
            if extra not in distinct_candidates:
                distinct_candidates.append(extra)
    distinct_candidates.sort()

    has_conflict_unresolved = any(r.kind == EVIDENCE_ITEM_KIND_CONFLICT_UNRESOLVED for r in resolutions)
    has_insufficient = any(r.kind == EVIDENCE_ITEM_KIND_INSUFFICIENT for r in resolutions)
    has_unmapped = any(r.kind == EVIDENCE_ITEM_KIND_UNMAPPED for r in resolutions)

    if has_conflict_unresolved:
        return (
            OUTCOME_IDENTITY_CONFLICT_UNRESOLVED,
            "Row's evidence is bound to an M5 subject left CONFLICT_UNRESOLVED; "
            "unresolved conflict is propagated and is not overridden by any "
            "co-occurring resolved candidate in the same row.",
            distinct_candidates,
        )

    if has_insufficient or has_unmapped:
        return (
            OUTCOME_INSUFFICIENT_EVIDENCE,
            "Row's evidence includes a subject absent from every M5 resolution "
            "ledger (candidate/alias/conflict/boundary) or an unmapped "
            "occurrence; insufficient evidence is propagated, not overridden "
            "by any co-occurring resolved candidate.",
            distinct_candidates,
        )

    if len(distinct_candidates) >= 2:
        return (
            OUTCOME_CONFLICTING_MULTI_PRODUCT,
            f"Row evidence resolves to {len(distinct_candidates)} distinct M5 canonical candidates.",
            distinct_candidates,
        )

    if len(distinct_candidates) == 1:
        return (
            OUTCOME_CANDIDATE_LINKED,
            "Row evidence resolves to exactly one M5 canonical candidate; "
            "noncandidate/generic/background components are discarded.",
            distinct_candidates,
        )

    # All evidence items existed and were affirmatively classified as
    # noncandidate but none produced a candidate id: explicit noncandidate.
    return (
        OUTCOME_EXPLICIT_NONCANDIDATE,
        "Row's bound evidence carries only explicit-noncandidate assertions "
        "with no candidate identity anywhere in the row.",
        [],
    )


# ---------------------------------------------------------------------------
# Main mapping driver
# ---------------------------------------------------------------------------

def map_rows_independent(inputs: FrozenInputs) -> dict[str, list[dict]]:
    row_outcome_ledger = []
    row_candidate_mapping_ledger = []
    row_evidence_binding_ledger = []
    unresolved_row_ledger = []
    row_identity_boundary_ledger = []
    combination_component_ledger = []

    for row in inputs.row_evidence_bindings:
        frozen_row_id = row["frozen_row_id"]
        nct_id = row.get("nct_id")
        intervention_index = row.get("intervention_index")
        occurrence_ids = row.get("evidence_occurrence_ids", [])

        resolutions: list[SubjectResolution] = []
        subject_ids_seen: list[str] = []
        for oid in occurrence_ids:
            sid = inputs.resolve_occurrence_subject(oid)
            res = resolve_subject(inputs, sid)
            resolutions.append(res)
            if sid:
                subject_ids_seen.append(sid)

        outcome, rationale, distinct_candidates = _reduce_row_outcome(resolutions)

        row_evidence_binding_ledger.append({
            "frozen_row_id": frozen_row_id,
            "evidence_occurrence_ids": occurrence_ids,
            "subject_ids": sorted(set(subject_ids_seen)),
            "resolution_kinds": [r.kind for r in resolutions],
        })

        candidate_id_singular = distinct_candidates[0] if len(distinct_candidates) == 1 else None
        row_outcome_ledger.append({
            "frozen_row_id": frozen_row_id,
            "nct_id": nct_id,
            "intervention_index": intervention_index,
            "outcome": outcome,
            "canonical_candidate_id": candidate_id_singular,
            "notes": rationale,
        })

        if outcome in (OUTCOME_CANDIDATE_LINKED, OUTCOME_CONFLICTING_MULTI_PRODUCT):
            row_candidate_mapping_ledger.append({
                "frozen_row_id": frozen_row_id,
                "canonical_candidate_id": candidate_id_singular,
                "canonical_candidate_ids": distinct_candidates,
                "binding_path": [
                    {
                        "subject_id": r.subject_id,
                        "kind": r.kind,
                        "candidate_id": r.candidate_id,
                        "rationale": r.rationale,
                    }
                    for r in resolutions
                ],
            })

        if outcome in (OUTCOME_IDENTITY_CONFLICT_UNRESOLVED, OUTCOME_INSUFFICIENT_EVIDENCE,
                       OUTCOME_CONFLICTING_MULTI_PRODUCT):
            unresolved_row_ledger.append({
                "frozen_row_id": frozen_row_id,
                "outcome": outcome,
                "reason": rationale,
                "underlying_m5_pointer": None,
            })

        # Component-level ledger: one component per resolved evidence item,
        # discarding noncandidate/insufficient items from the candidate set
        # (mirrors the combination-string spec independently: build the
        # component list straight from this row's own resolutions, not from
        # a shared upstream ledger).
        if len(occurrence_ids) > 1 or outcome == OUTCOME_CANDIDATE_LINKED and len(resolutions) > 1:
            components = []
            for r in resolutions:
                if r.candidate_id:
                    components.append({"resolution": "CANDIDATE", "candidate_id": r.candidate_id})
                elif r.kind == EVIDENCE_ITEM_KIND_INSUFFICIENT:
                    components.append({"resolution": "INSUFFICIENT_DISCARDED", "candidate_id": None})
                elif r.kind == EVIDENCE_ITEM_KIND_CONFLICT_UNRESOLVED:
                    components.append({"resolution": "CONFLICT_UNRESOLVED_DISCARDED", "candidate_id": None})
                else:
                    components.append({"resolution": "GENERIC_DISCARDED", "candidate_id": None})
            if len(occurrence_ids) > 1:
                combination_component_ledger.append({
                    "frozen_row_id": frozen_row_id,
                    "components": components,
                })

        boundary_note = None
        for sid in subject_ids_seen:
            b = inputs.subject_boundary.get(sid)
            if b is not None:
                boundary_note = b.get("boundary_type")
        if boundary_note:
            row_identity_boundary_ledger.append({
                "frozen_row_id": frozen_row_id,
                "subject_ids": sorted(set(subject_ids_seen)),
                "boundary_type": boundary_note,
                "outcome_at_row_level": outcome,
            })

    return {
        "row_outcome_ledger": row_outcome_ledger,
        "row_candidate_mapping_ledger": row_candidate_mapping_ledger,
        "row_evidence_binding_ledger": row_evidence_binding_ledger,
        "unresolved_row_ledger": unresolved_row_ledger,
        "row_identity_boundary_ledger": row_identity_boundary_ledger,
        "combination_component_ledger": combination_component_ledger,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m3-dir", required=True, type=Path,
                         help="Path to the extracted M3 (evidence triage) release directory")
    parser.add_argument("--m4-dir", required=True, type=Path,
                         help="Path to the extracted M4 (external authority) release directory")
    parser.add_argument("--m5-dir", required=True, type=Path,
                         help="Path to the extracted M5 (candidate identity) release directory")
    parser.add_argument("--out-dir", required=True, type=Path,
                         help="Directory to write build_b ledgers into")
    args = parser.parse_args()

    inputs = FrozenInputs(m3_dir=args.m3_dir, m4_dir=args.m4_dir, m5_dir=args.m5_dir).load()
    ledgers = map_rows_independent(inputs)

    for name, rows in ledgers.items():
        _write_jsonl(args.out_dir / f"build_b_{name}.jsonl", rows)

    counts: dict[str, int] = {}
    for row in ledgers["row_outcome_ledger"]:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    print(json.dumps({"total_rows": len(ledgers["row_outcome_ledger"]), "outcome_counts": counts}, indent=2))


if __name__ == "__main__":
    main()
