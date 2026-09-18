"""PDCD1 Rebase V1 - Milestone 7 - Mapper B (candidate chronology, INDEPENDENT build).

This module is a STRUCTURALLY INDEPENDENT re-implementation of the M7
candidate-chronology derivation step, following the pattern established for
Milestone 6 v2 (see
``scripts/pdcd1_rebase_v1_row_identity_mapping_mapper_b.py`` and its
independence guard test). It does not import, call, or otherwise delegate to
Mapper A's chronology-derivation module, and it does not read Mapper A's
output ledger as an evidence source. It is built
directly against the same frozen M2/M5/M6-v2 release artifacts, using a
deliberately different algorithm and control-flow structure so the agreement
between the two builds is a genuine cross-check rather than a restated
computation:

  - Mapper A iterates NCT-outer / version-inner, scanning each version once
    for every candidate relevant to that trial, and matches with a single
    normalized substring test against the whole record.
  - Mapper B (this module) iterates candidate-outer / registry-history-index-
    inner: for each candidate it first builds a token-set signature for the
    candidate's name/aliases, then walks each linked trial's CT.gov
    ``history_index.json`` (a different M2 artifact than the per-version file
    Mapper A reads for its outer loop -- Mapper A never opens
    ``history_index.json``) to get the ordered version/date list, then loads
    each version file only as needed. Matching is done via a token-overlap
    test (every normalized word of the candidate's shortest matching name
    variant must appear as a whole word in the candidate haystack) rather
    than substring containment, so the two builds can disagree on edge cases
    (e.g. a candidate name that is a substring of a longer unrelated word)
    and any such disagreement gets reconciled by hand against frozen evidence
    rather than being definitionally impossible to detect.

Same output contract as Mapper A (one record per candidate x linked-nct_id
pair), same UNKNOWN-by-default discipline: nothing is guessed, date precision
from the registry is preserved verbatim, and approval_date is always left
``None`` because the frozen M4 external-authority ledger available at this
milestone contains no approval-date assertions (only product-existence
assertions) -- inventing one would violate the never-infer guardrail.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

UNKNOWN = "UNKNOWN"

_WORD_RE = re.compile(r"[a-z0-9]+")

_GENERIC_CLASS_WORDS = {
    frozenset({"pd", "1", "inhibitor"}),
    frozenset({"anti", "pd", "1"}),
    frozenset({"anti", "pd", "1", "therapy"}),
    frozenset({"anti", "pd", "1", "antibody"}),
    frozenset({"pd", "1", "antibody"}),
    frozenset({"checkpoint", "inhibitor"}),
    frozenset({"immune", "checkpoint", "inhibitor"}),
    frozenset({"pd", "1"}),
    frozenset({"pd", "l1", "inhibitor"}),
    frozenset({"anti", "pd", "l1"}),
    frozenset({"anti", "pd", "1", "immunotherapy"}),
    frozenset({"anti", "pd", "l1", "immunotherapy"}),
    frozenset({"pd", "1", "immunotherapy"}),
    frozenset({"immunotherapy"}),
}


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True))
            fh.write("\n")


class CandidateSignature:
    """Token-set name signatures for one canonical candidate."""

    def __init__(self, candidate_id: str, canonical_name: str) -> None:
        self.candidate_id = candidate_id
        self.canonical_name = canonical_name
        self.name_variants: list[frozenset[str]] = []

    def add_variant(self, text: str) -> None:
        toks = frozenset(_words(text))
        if not toks or toks in _GENERIC_CLASS_WORDS:
            return
        # Skip single-character / purely numeric noise variants.
        if all(len(t) <= 1 for t in toks):
            return
        if toks not in self.name_variants:
            self.name_variants.append(toks)

    def matches(self, haystack_words: set[str]) -> bool:
        """A variant matches if ALL of its tokens are present as whole words
        somewhere in the haystack (order-independent token-overlap test --
        deliberately different from Mapper A's ordered-substring test)."""
        return any(variant.issubset(haystack_words) for variant in self.name_variants if len(variant) >= 1)


def _build_candidate_signatures(m5_dir: Path) -> dict[str, CandidateSignature]:
    sigs: dict[str, CandidateSignature] = {}
    candidate_recs = _read_jsonl(m5_dir / "candidates" / "canonical_candidate_ledger.jsonl")
    for rec in candidate_recs:
        cid = rec["candidate_id"]
        name = rec.get("canonical_name", "")
        sig = sigs.setdefault(cid, CandidateSignature(cid, name))
        sig.add_variant(name)
        # The name with any parenthetical content stripped is its own
        # variant too -- many registry versions use only the bare product
        # name (e.g. "Sacituzumab govitecan") without ever writing the
        # bracketed development code/alt-name alongside it, and the
        # full-name variant above (which requires every token, parenthetical
        # included) would then never match.
        base_name = re.sub(r"\([^)]*\)", "", name).strip()
        if base_name and base_name != name:
            sig.add_variant(base_name)
        # Parenthetical content in the canonical name (development codes) is
        # a separate, independently useful variant.
        for paren in re.findall(r"\(([^)]+)\)", name):
            for piece in re.split(r"[\/,]| plus | and ", paren):
                sig.add_variant(piece)

    alias_recs = _read_jsonl(m5_dir / "aliases" / "alias_development_code_ledger.jsonl")
    for rec in alias_recs:
        cid = rec.get("candidate_id")
        alias = rec.get("alias_string", "")
        if cid and cid in sigs and alias:
            sigs[cid].add_variant(alias)
    return sigs


_ROW_ID_RE = re.compile(r"^row_\d+_(NCT\d+)_\d+$")


def _candidate_to_ncts(m6v2_dir: Path) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for rec in _read_jsonl(m6v2_dir / "rows" / "row_candidate_mapping_ledger.jsonl"):
        row_id = rec.get("frozen_row_id", "")
        match = _ROW_ID_RE.match(row_id)
        nct_id = match.group(1) if match else None
        if not nct_id:
            continue
        for cid in rec.get("canonical_candidate_ids", []) or []:
            mapping.setdefault(cid, set()).add(nct_id)
    return mapping


def _history_index_versions(m2_dir: Path, nct_id: str) -> list[dict]:
    """Reads the per-trial ``history_index.json`` artifact (distinct from the
    ``version_ledger.jsonl`` file Mapper A consults) for the ordered list of
    captured version numbers and their registry dates."""
    idx_path = m2_dir / "source" / nct_id / "history_index.json"
    if not idx_path.exists():
        return []
    with idx_path.open() as fh:
        payload = json.load(fh)
    changes = payload.get("changes", []) or []
    return sorted(changes, key=lambda c: c.get("version", 0))


def _load_version_study(m2_dir: Path, nct_id: str, version: int) -> dict | None:
    vpath = m2_dir / "source" / nct_id / "versions" / f"{version}.json"
    if not vpath.exists():
        return None
    with vpath.open() as fh:
        payload = json.load(fh)
    return payload.get("study")


def _flatten_intervention_words(study: dict) -> set[str]:
    aim = (study.get("protocolSection") or {}).get("armsInterventionsModule") or {}
    words: set[str] = set()
    for iv in aim.get("interventions", []) or []:
        words |= set(_words(iv.get("name", "")))
        for other in iv.get("otherNames", []) or []:
            words |= set(_words(other))
    for ag in aim.get("armGroups", []) or []:
        for iname in ag.get("interventionNames", []) or []:
            words |= set(_words(iname))
    return words


def _flatten_record_words(study: dict) -> set[str]:
    # Independent whole-record traversal: walk the nested dict/list structure
    # accumulating every string leaf's words, instead of Mapper A's approach
    # of serializing the whole object to JSON text and normalizing that blob.
    words: set[str] = set()
    stack: list[Any] = [study]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            words |= set(_words(node))
    return words


def derive_candidate_chronology(sig: CandidateSignature, nct_ids: set[str], m2_dir: Path) -> list[dict]:
    out: list[dict] = []
    for nct_id in sorted(nct_ids):
        changes = _history_index_versions(m2_dir, nct_id)
        if not changes:
            out.append({
                "candidate_id": sig.candidate_id,
                "canonical_name": sig.canonical_name,
                "nct_id": nct_id,
                "first_registry_string_appearance": UNKNOWN,
                "first_candidate_bearing_intervention_appearance": UNKNOWN,
                "candidate_specific_registered_start": None,
                "start_date_type": UNKNOWN,
                "present_in_original_version": UNKNOWN,
                "later_added_product_status": UNKNOWN,
                "first_known_phase": UNKNOWN,
                "approval_date": None,
                "notes": "No M2 history_index.json entries found for this nct_id.",
            })
            continue

        earliest_version = changes[0]["version"]
        string_hit = None
        intervention_hit = None
        intervention_study = None

        for change in changes:
            vnum = change["version"]
            study = _load_version_study(m2_dir, nct_id, vnum)
            if study is None:
                continue

            if string_hit is None:
                rec_words = _flatten_record_words(study)
                if sig.matches(rec_words):
                    string_hit = (vnum, change.get("date"))

            if intervention_hit is None:
                iv_words = _flatten_intervention_words(study)
                if sig.matches(iv_words):
                    intervention_hit = (vnum, change.get("date"))
                    intervention_study = study

            if string_hit is not None and intervention_hit is not None:
                break

        present_in_original = UNKNOWN
        later_added = UNKNOWN
        registered_start = None
        start_type = UNKNOWN
        first_phase = UNKNOWN

        if intervention_hit is not None:
            iv_vnum, _iv_vdate = intervention_hit
            present_in_original = iv_vnum == earliest_version
            later_added = not present_in_original
            status = (intervention_study.get("protocolSection") or {}).get("statusModule") or {}
            start_struct = status.get("startDateStruct") or {}
            # Guardrail: CT.gov's startDateStruct is a trial-level field, not
            # per-intervention -- it does not move when a later amendment adds
            # a new candidate/arm. Populating it for a later-added candidate
            # would silently misattribute the trial's original start date as
            # if it were specific to that candidate. Only trust it as
            # candidate-specific when the candidate was already present in
            # the trial's earliest captured version.
            if present_in_original:
                registered_start = start_struct.get("date")
                start_type = start_struct.get("type") or UNKNOWN
            else:
                registered_start = None
                start_type = UNKNOWN
            phases = (intervention_study.get("protocolSection") or {}).get("designModule", {}).get("phases")
            if phases:
                first_phase = phases if isinstance(phases, list) else [phases]

        out.append({
            "candidate_id": sig.candidate_id,
            "canonical_name": sig.canonical_name,
            "nct_id": nct_id,
            "first_registry_string_appearance": (
                {"version": string_hit[0], "version_date": string_hit[1]} if string_hit else UNKNOWN
            ),
            "first_candidate_bearing_intervention_appearance": (
                {"version": intervention_hit[0], "version_date": intervention_hit[1]}
                if intervention_hit else UNKNOWN
            ),
            "candidate_specific_registered_start": registered_start,
            "start_date_type": start_type,
            "present_in_original_version": present_in_original,
            "later_added_product_status": later_added,
            "first_known_phase": first_phase,
            "approval_date": None,
            "notes": (
                "Candidate token-set never matched a structured intervention/arm "
                "field across any captured version; chronology fields dependent "
                "on intervention presence left UNKNOWN."
                if intervention_hit is None else
                "Later-added candidate: startDateStruct is a trial-level field "
                "that would misattribute the trial's original start date to "
                "this candidate, so candidate_specific_registered_start is "
                "left UNKNOWN rather than inherited."
                if later_added else ""
            ),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m2-dir", required=True, type=Path)
    parser.add_argument("--m5-dir", required=True, type=Path)
    parser.add_argument("--m6v2-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    signatures = _build_candidate_signatures(args.m5_dir)
    candidate_ncts = _candidate_to_ncts(args.m6v2_dir)

    all_rows: list[dict] = []
    for cid in sorted(candidate_ncts):
        sig = signatures.get(cid) or CandidateSignature(cid, UNKNOWN)
        all_rows.extend(derive_candidate_chronology(sig, candidate_ncts[cid], args.m2_dir))

    _write_jsonl(args.out_dir / "build_b_candidate_chronology_ledger.jsonl", all_rows)
    print(json.dumps(
        {"total_candidate_nct_pairs": len(all_rows), "total_candidates": len(candidate_ncts)},
        indent=2,
    ))


if __name__ == "__main__":
    main()
