"""PDCD1 Rebase V1 - Milestone 7 - Mapper A (candidate chronology, Build A).

Derives, for every canonical candidate that appears in the M6 v2 (authoritative)
row->candidate mapping, a set of chronology facts purely from the frozen M2
complete registry history (4,029 ClinicalTrials.gov versions across 81
studies) and the frozen M5 candidate/alias ledgers used only as a *name
source* (never as a chronology source -- M5 carries no dates).

Design spec (frozen before Build B was written; Build B must not read this
file or import from it -- see the independence guard test):

Inputs (read-only, never mutated):
  - M2 ``normalized/version_ledger.jsonl``     -- version -> version_date map
  - M2 ``source/<NCT>/versions/<n>.json``      -- one full CT.gov study record
    per captured version
  - M5 ``candidates/canonical_candidate_ledger.jsonl`` -- candidate_id -> name
  - M5 ``aliases/alias_development_code_ledger.jsonl`` -- candidate_id -> alias
    strings (development codes, synonyms)
  - M6 v2 ``rows/row_candidate_mapping_ledger.jsonl``  -- authoritative
    frozen_row_id -> canonical_candidate_ids (a row's ``frozen_row_id`` embeds
    its NCT id, e.g. ``row_002_NCT06703398_0``)

For each candidate that appears in >=1 M6 v2 row mapping, and for each NCT id
that candidate is linked to via that mapping, this script walks the trial's
registry versions in ascending version order and derives, per (candidate,
nct_id) pair:

  - ``first_registry_string_appearance``: the first version in which the
    candidate's canonical name or any frozen M5 alias string appears ANYWHERE
    in that version's serialized record (title, description, eligibility,
    intervention fields, everything) -- a broad, non-inferential text-match.
  - ``first_candidate_bearing_intervention_appearance``: the first version in
    which the candidate's name/alias appears specifically within a
    *structured* intervention/arm identifier field: ``interventions[].name``,
    ``interventions[].otherNames[]``, or ``armGroups[].interventionNames[]``.
    Free-text arm/intervention *descriptions* are deliberately excluded here
    (those are treated as background narrative, not an intervention/arm
    identity field) to avoid crediting a generic mention as a specific
    intervention entry.
  - ``candidate_specific_registered_start``: the trial's
    ``statusModule.startDateStruct.date`` as recorded AT THE VERSION where the
    candidate first appears in an intervention field (never the trial's
    original/version-0 start date unless the candidate was also present at
    version 0) -- per the guardrail that a later-added candidate must not
    inherit the original registered start date.
  - ``start_date_type``: the CT.gov-reported ``startDateStruct.type``
    (``ACTUAL`` / ``ESTIMATED``) at that same version, or ``UNKNOWN`` if the
    field is absent (never inferred).
  - ``present_in_original_version``: whether the candidate was already present
    in the intervention field at the trial's earliest captured version.
  - ``later_added_product_status``: the negation of the above, when
    determinable.
  - ``first_known_phase``: ``designModule.phases`` at the version of first
    intervention-field appearance.
  - ``approval_date``: always ``UNKNOWN`` for M7 -- the frozen M4 external
    authority evidence available to this milestone contains only
    existence-of-product assertions (``EXACT_PRODUCT_NAME_EXISTS`` etc.), no
    approval-date fields; inventing one from openFDA metadata not present in
    the frozen M4 ledgers would violate the "never derive/infer" guardrail.

Every field defaults to ``"UNKNOWN"`` (or ``None`` for the date fields) and is
only overwritten when supported by an explicit registry-version match. Nothing
is guessed. Date-string precision is preserved exactly as recorded (a
``"2020-03"`` value is never upgraded to a day-precise date).
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

UNKNOWN = "UNKNOWN"


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


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


_GENERIC_CLASS_TERMS = {
    "pd 1 inhibitor", "anti pd 1", "anti pd 1 therapy", "anti pd 1 antibody",
    "pd 1 antibody", "checkpoint inhibitor", "immune checkpoint inhibitor",
    "pd 1", "pd l1 inhibitor", "anti pd l1", "anti pd 1 immunotherapy",
    "anti pd l1 immunotherapy", "pd 1 immunotherapy", "immunotherapy",
}


@dataclass
class CandidateNames:
    candidate_id: str
    canonical_name: str
    match_strings: list[str] = field(default_factory=list)  # normalized, len-filtered


_PAREN_RE = re.compile(r"\(([^)]+)\)")
_COMBO_SPLIT_RE = re.compile(r"\s*/\s*|\s*,\s*|\s+plus\s+|\s+and\s+", re.IGNORECASE)


def _add_variant(names: CandidateNames, text: str) -> None:
    norm = _normalize(text)
    if norm and norm not in _GENERIC_CLASS_TERMS and len(norm) >= 3:
        if norm not in names.match_strings:
            names.match_strings.append(norm)


def _load_candidate_names(m5_dir: Path) -> dict[str, CandidateNames]:
    out: dict[str, CandidateNames] = {}
    for rec in _read_jsonl(m5_dir / "candidates" / "canonical_candidate_ledger.jsonl"):
        cid = rec["candidate_id"]
        name = rec.get("canonical_name", "")
        entry = out.setdefault(cid, CandidateNames(candidate_id=cid, canonical_name=name))
        # Full name as one substring-match variant (works when the registry
        # text literally reproduces the whole name string)...
        _add_variant(entry, name)
        # ...plus each parenthetical alternate/development-code name as its
        # own independent variant (e.g. "Favezelimab/pembrolizumab
        # coformulation (MK-4280A)" -> also match on "MK-4280A" alone), since
        # a candidate whose registry text uses only the parenthetical form
        # would otherwise never be substring-matched against the full name.
        base_name = _PAREN_RE.sub("", name).strip()
        if base_name != name:
            _add_variant(entry, base_name)
        for paren in _PAREN_RE.findall(name):
            for piece in _COMBO_SPLIT_RE.split(paren):
                _add_variant(entry, piece)
        # NOTE: deliberately NOT splitting the base (non-parenthetical) name
        # on combination separators ("/", "plus", "and"). Doing so for a
        # coformulation/combination candidate (e.g. "Pembrolizumab/
        # quavonlimab coformulation") would add a bare "pembrolizumab"
        # variant -- a common standalone backbone product that already has
        # its own separate M5 candidate identity -- which would fabricate
        # false-positive early chronology for the coformulation candidate
        # from every trial that merely uses plain pembrolizumab as
        # background therapy. Only parenthetical development-code content is
        # split into independent variants; the base combination name is only
        # matched as its own full (unsplit) string.
    for rec in _read_jsonl(m5_dir / "aliases" / "alias_development_code_ledger.jsonl"):
        cid = rec.get("candidate_id")
        alias = rec.get("alias_string", "")
        if not cid or cid not in out:
            continue
        _add_variant(out[cid], alias)
    return out


def _load_m6v2_candidate_nct_links(m6v2_dir: Path) -> dict[str, set[str]]:
    """candidate_id -> set of nct_ids the candidate is authoritatively linked to."""
    links: dict[str, set[str]] = {}
    for rec in _read_jsonl(m6v2_dir / "rows" / "row_candidate_mapping_ledger.jsonl"):
        frozen_row_id = rec["frozen_row_id"]
        # frozen_row_id format: row_<seq>_<NCTID>_<intervention_index>
        m = re.match(r"row_\d+_(NCT\d+)_\d+$", frozen_row_id)
        nct_id = m.group(1) if m else frozen_row_id.split("_")[2]
        for cid in rec.get("canonical_candidate_ids", []):
            links.setdefault(cid, set()).add(nct_id)
    return links


def _load_version_dates(m2_dir: Path) -> dict[tuple[str, int], str]:
    """(nct_id, version) -> version_date, from the frozen M2 version ledger
    (the authoritative per-version capture date -- NOT a protocol-level field
    like ``studyFirstSubmitDate``, which is constant across all versions of a
    trial and would misrepresent every later version's actual capture date)."""
    ledger_path = m2_dir / "normalized" / "version_ledger.jsonl"
    out: dict[tuple[str, int], str] = {}
    if not ledger_path.exists():
        return out
    with ledger_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[(rec["nct_id"], rec["version"])] = rec.get("version_date", "")
    return out


_VERSION_DATE_CACHE: dict[Path, dict[tuple[str, int], str]] = {}


def _load_versions(m2_dir: Path, nct_id: str) -> list[tuple[int, str, dict]]:
    """Returns [(version_number, version_date, study_record_dict), ...] ascending."""
    version_dir = m2_dir / "source" / nct_id / "versions"
    if not version_dir.exists():
        return []
    if m2_dir not in _VERSION_DATE_CACHE:
        _VERSION_DATE_CACHE[m2_dir] = _load_version_dates(m2_dir)
    version_dates = _VERSION_DATE_CACHE[m2_dir]

    entries = []
    for vf in version_dir.glob("*.json"):
        try:
            vnum = int(vf.stem)
        except ValueError:
            continue
        with vf.open() as fh:
            payload = json.load(fh)
        study = payload.get("study", {})
        entries.append((vnum, study))
    entries.sort(key=lambda t: t[0])
    out = []
    for vnum, study in entries:
        vdate = version_dates.get((nct_id, vnum), "")
        out.append((vnum, vdate, study))
    return out


def _intervention_field_text(study: dict) -> str:
    ps = study.get("protocolSection", {})
    aim = ps.get("armsInterventionsModule", {})
    parts: list[str] = []
    for iv in aim.get("interventions", []) or []:
        parts.append(iv.get("name", ""))
        parts.extend(iv.get("otherNames", []) or [])
    for ag in aim.get("armGroups", []) or []:
        parts.extend(ag.get("interventionNames", []) or [])
    return " | ".join(p for p in parts if p)


def _full_record_text(study: dict) -> str:
    return json.dumps(study)


def _match_any(haystack_normalized: str, match_strings: list[str]) -> bool:
    return any(ms in haystack_normalized for ms in match_strings)


def derive_chronology(
    candidate: CandidateNames,
    nct_ids: set[str],
    m2_dir: Path,
) -> list[dict]:
    results = []
    for nct_id in sorted(nct_ids):
        versions = _load_versions(m2_dir, nct_id)
        if not versions:
            results.append({
                "candidate_id": candidate.candidate_id,
                "canonical_name": candidate.canonical_name,
                "nct_id": nct_id,
                "first_registry_string_appearance": UNKNOWN,
                "first_candidate_bearing_intervention_appearance": UNKNOWN,
                "candidate_specific_registered_start": None,
                "start_date_type": UNKNOWN,
                "present_in_original_version": UNKNOWN,
                "later_added_product_status": UNKNOWN,
                "first_known_phase": UNKNOWN,
                "approval_date": None,
                "notes": "No M2 registry versions found for this nct_id.",
            })
            continue

        min_version = versions[0][0]
        string_first: tuple[int, str] | None = None
        intervention_first: tuple[int, str] | None = None
        intervention_first_study: dict | None = None

        for vnum, vdate, study in versions:
            full_norm = _normalize(_full_record_text(study))
            if string_first is None and _match_any(full_norm, candidate.match_strings):
                string_first = (vnum, vdate)

            iv_norm = _normalize(_intervention_field_text(study))
            if intervention_first is None and _match_any(iv_norm, candidate.match_strings):
                intervention_first = (vnum, vdate)
                intervention_first_study = study

        present_in_original = UNKNOWN
        later_added = UNKNOWN
        registered_start = None
        start_type = UNKNOWN
        first_phase = UNKNOWN

        if intervention_first is not None:
            iv_vnum, iv_vdate = intervention_first
            present_in_original = iv_vnum == min_version
            later_added = not present_in_original
            ps = (intervention_first_study or {}).get("protocolSection", {})
            status = ps.get("statusModule", {})
            start_struct = status.get("startDateStruct", {}) or {}
            # Guardrail: CT.gov's startDateStruct is a TRIAL-level field, not a
            # per-intervention one -- it does not change when a later amendment
            # adds a new candidate/arm. Treating it as "candidate-specific" for
            # a later-added candidate would silently misattribute the trial's
            # original start date to a product that was not part of the trial
            # at that time. Only populate a registered start for candidates
            # present in the trial's original (version 0) registration; a
            # later-added candidate's own registered start is UNKNOWN unless a
            # future milestone captures a genuinely per-arm/per-intervention
            # start-date field.
            if present_in_original:
                registered_start = start_struct.get("date")
                start_type = start_struct.get("type", UNKNOWN) or UNKNOWN
            else:
                registered_start = None
                start_type = UNKNOWN
            phases = ps.get("designModule", {}).get("phases")
            if phases:
                first_phase = phases if isinstance(phases, list) else [phases]

        results.append({
            "candidate_id": candidate.candidate_id,
            "canonical_name": candidate.canonical_name,
            "nct_id": nct_id,
            "first_registry_string_appearance": (
                {"version": string_first[0], "version_date": string_first[1]}
                if string_first else UNKNOWN
            ),
            "first_candidate_bearing_intervention_appearance": (
                {"version": intervention_first[0], "version_date": intervention_first[1]}
                if intervention_first else UNKNOWN
            ),
            "candidate_specific_registered_start": registered_start,
            "start_date_type": start_type,
            "present_in_original_version": present_in_original,
            "later_added_product_status": later_added,
            "first_known_phase": first_phase,
            "approval_date": None,
            "notes": (
                "Candidate never located in a structured intervention/arm field "
                "across any captured version; chronology fields dependent on "
                "intervention presence left UNKNOWN."
                if intervention_first is None else
                "Later-added candidate: startDateStruct is a trial-level field "
                "that would misattribute the trial's original start date to "
                "this candidate, so candidate_specific_registered_start is "
                "left UNKNOWN rather than inherited."
                if later_added else ""
            ),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m2-dir", required=True, type=Path)
    parser.add_argument("--m5-dir", required=True, type=Path)
    parser.add_argument("--m6v2-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    candidate_names = _load_candidate_names(args.m5_dir)
    links = _load_m6v2_candidate_nct_links(args.m6v2_dir)

    all_rows: list[dict] = []
    for cid, nct_ids in sorted(links.items()):
        cand = candidate_names.get(cid) or CandidateNames(candidate_id=cid, canonical_name=UNKNOWN)
        all_rows.extend(derive_chronology(cand, nct_ids, args.m2_dir))

    _write_jsonl(args.out_dir / "build_a_candidate_chronology_ledger.jsonl", all_rows)
    print(json.dumps({"total_candidate_nct_pairs": len(all_rows), "total_candidates": len(links)}, indent=2))


if __name__ == "__main__":
    main()
