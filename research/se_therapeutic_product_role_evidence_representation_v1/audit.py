"""Frozen source-availability ledger; not a production ProductRoleEvidence adapter."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
STUDY = ROOT / "research/se_therapeutic_product_role_evidence_representation_v1"
RUN = Path("/home/djmann/se_runs/heldout_h19_v4/result.json")


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def key(x):
    return " ".join(str(x).split()).casefold()


def field(snapshot, digest, docid, path, raw, scope):
    origin = {
        "snapshot": str(snapshot),
        "artifact_sha256": digest,
        "document_id": docid,
        "field_path": path,
    }
    return {
        "assertion_id": sha(origin),
        "source": origin,
        "semantic_scope": scope,
        "raw_value": raw,
        "normalized_value": raw,
        "transformations": [{"operation": "identity"}],
        "status": "NATIVE_FIELD_ONLY",
        "therapeutic_product_assertion": False,
        "intervention_use_assertion": False,
    }


def inventory(raw, path=()):
    if isinstance(raw, dict):
        for k, v in raw.items():
            yield from inventory(v, path + (k,))
    elif isinstance(raw, list):
        for v in raw:
            yield from inventory(v, path + ("[]",))
    else:
        yield "/".join(path), type(raw).__name__


def native_fields(raw, snapshot, digest, docid):
    records = []

    def add(path, value, scope):
        records.append(field(snapshot, digest, docid, path, value, scope))

    module = raw.get("armsInterventionsModule", {})
    for i, intervention in enumerate(module.get("interventions", [])):
        for name, value in intervention.items():
            scope = {
                "type": "ENTITY_TYPE",
                "name": "IDENTITY_TEXT",
                "otherNames": "IDENTITY_TEXT",
                "description": "FREE_TEXT",
                "armGroupLabels": "INTERVENTION_ARM_LINK",
            }.get(name, "UNMAPPED_NATIVE_FIELD")
            base = ["armsInterventionsModule", "interventions", i, name]
            if isinstance(value, list):
                for j, item in enumerate(value):
                    add(base + [j], item, scope)
            else:
                add(base, value, scope)
    for i, arm in enumerate(module.get("armGroups", [])):
        for name, value in arm.items():
            scope = {
                "type": "ARM_TYPE",
                "label": "ARM_LABEL",
                "description": "FREE_TEXT",
                "interventionNames": "ARM_INTERVENTION_LINK",
            }.get(name, "UNMAPPED_NATIVE_FIELD")
            base = ["armsInterventionsModule", "armGroups", i, name]
            if isinstance(value, list):
                for j, item in enumerate(value):
                    add(base + [j], item, scope)
            else:
                add(base, value, scope)
    purpose = raw.get("designModule", {}).get("designInfo", {}).get("primaryPurpose")
    if purpose is not None:
        add(["designModule", "designInfo", "primaryPurpose"], purpose, "STUDY_PURPOSE")
    for module_name, scope in [
        ("sponsorCollaboratorsModule", "SPONSOR_ORGANISATION_CONTEXT"),
        ("identificationModule", "STUDY_IDENTITY_CONTEXT"),
        ("descriptionModule", "FREE_TEXT"),
    ]:
        for name, value in raw.get(module_name, {}).items():
            add([module_name, name], value, scope)
    return records


def build(output):
    inputs = json.loads((STUDY / "inputs.json").read_text())
    for p, h in inputs.items():
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == h, p
    run = json.loads(RUN.read_text())
    frozen = json.loads((STUDY / "population.json").read_text())
    actual = [
        {
            "asset_id": a["asset_id"],
            "name": a["canonical_name"],
            "qualification_reason": a["qualification_reason"],
        }
        for a in run["candidates"]
    ]
    assert actual == frozen and len(frozen) == 1181
    docs = {d["document_id"]: d for d in run["source_documents"]}
    rawdocs = {}
    fields = {}
    doc_fields = {}
    schema = defaultdict(Counter)
    for d in docs.values():
        if not d.get("snapshot_path"):
            continue
        p = Path(d["snapshot_path"])
        raw = json.loads(p.read_text())
        rawdocs[d["document_id"]] = raw
        for path, typ in inventory(raw):
            schema[d["publisher"]][path + ":" + typ] += 1
        generated = (
            native_fields(raw, p, inputs[str(p)], d["document_id"])
            if d["publisher"] == "ClinicalTrials.gov"
            else []
        )
        doc_fields[d["document_id"]] = generated
        for f in generated:
            fields[f["assertion_id"]] = f
    mentions = {m["mention_id"]: m for m in run["identity_mentions"]}
    claims = {c["claim_id"]: c for c in run["claims"]}
    rows = []
    docmatched = Counter()
    native_types = Counter()
    native_arms = Counter()
    purposes = Counter()
    type_variations = []
    arm_variations = []
    for ci, a in enumerate(run["candidates"]):
        ms = [mentions[m] for m in a["mention_ids"] if m in mentions]
        cs = [claims[c] for c in a["supporting_claim_ids"] if c in claims]
        document_ids = sorted(
            {m["source_document_id"] for m in ms} | {c["source_document_id"] for c in cs}
        )
        names = {
            key(n)
            for n in [a["canonical_name"], *a["aliases"], *[m["raw_asset_name"] for m in ms]]
            if n
        }
        links = []
        support = set()
        types = set()
        arms = set()
        purpose_values = set()
        unmatched = []
        has_prose = False
        for did in document_ids:
            raw = rawdocs.get(did)
            if raw is None:
                continue
            if docs[did]["publisher"] != "ClinicalTrials.gov":
                has_prose = True
                continue
            module = raw.get("armsInterventionsModule", {})
            matches = []
            for i, iv in enumerate(module.get("interventions", [])):
                ivnames = [iv.get("name", ""), *iv.get("otherNames", [])]
                if not names.intersection(key(n) for n in ivnames if n):
                    continue
                matches.append(i)
                types.add(iv.get("type", "MISSING"))
                labels = set(iv.get("armGroupLabels", []))
                arm_indices = []
                channels = []
                for ai, arm in enumerate(module.get("armGroups", [])):
                    channel = []
                    if arm.get("label") in labels:
                        channel.append("INTERVENTION_ARM_LABEL")
                    armnames = [
                        n.split(":", 1)[1].strip() if ":" in n else n
                        for n in arm.get("interventionNames", [])
                    ]
                    if key(iv.get("name", "")) in {key(n) for n in armnames}:
                        channel.append("ARM_INTERVENTION_NAME")
                    if channel:
                        arm_indices.append(ai)
                        arms.add(arm.get("type", "MISSING"))
                        channels.append({"arm_index": ai, "channels": channel})
                links.append(
                    {
                        "document_id": did,
                        "trial_id": raw.get("identificationModule", {}).get("nctId"),
                        "intervention_index": i,
                        "arm_links": channels,
                        "link_basis": "EXISTING_NAME_OR_ALIAS_EXACT_CASEFOLD_WHITESPACE",
                        "raw_intervention_names": ivnames,
                        "normalized_intervention_names": [key(n) for n in ivnames],
                    }
                )
                for f in doc_fields.get(did, []):
                    path = f["source"]["field_path"]
                    applicable = (
                        (path[:2] == ["armsInterventionsModule", "interventions"] and path[2] == i)
                        or (
                            path[:2] == ["armsInterventionsModule", "armGroups"]
                            and path[2] in arm_indices
                        )
                        or path[0] != "armsInterventionsModule"
                    )
                    if applicable:
                        support.add(f["assertion_id"])
                        if f["semantic_scope"] == "FREE_TEXT":
                            has_prose = True
                        if f["semantic_scope"] == "STUDY_PURPOSE":
                            purpose_values.add(f["raw_value"])
            if not matches:
                unmatched.append(did)
        for v in types:
            native_types[v] += 1
        for v in arms:
            native_arms[v] += 1
        for v in purpose_values:
            purposes[v] += 1
        if len(types) > 1:
            type_variations.append(
                {
                    "asset_id": a["asset_id"],
                    "values": sorted(types),
                    "status": "SOURCE_ENTITY_TYPE_VARIATION_NOT_PRODUCT_KIND_CONFLICT",
                }
            )
        if len(arms) > 1:
            arm_variations.append(
                {
                    "asset_id": a["asset_id"],
                    "values": sorted(arms),
                    "status": "MIXED_ARM_CONTEXTS_NOT_INTRINSIC_CONFLICT",
                }
            )
        for link in links:
            docmatched[link["document_id"]] += 1
        authority = []
        for prop in ["authority_modality", "authority_modality_basis"]:
            if a.get(prop) is not None:
                f = field(
                    RUN,
                    inputs[str(RUN)],
                    "frozen_result",
                    ["candidates", ci, prop],
                    a[prop],
                    "LEGACY_MODALITY_ANNOTATION",
                )
                fields[f["assertion_id"]] = f
                authority.append(f["assertion_id"])
        row = {
            "asset_id": a["asset_id"],
            "name": a["canonical_name"],
            "qualification_reason_before": a["qualification_reason"],
            "qualification_reason_after": a["qualification_reason"],
            "source_document_ids": document_ids,
            "intervention_links": links,
            "native_assertion_ids": sorted(support),
            "authority_annotation_ids": authority,
            "entity_type_declarations": sorted(types),
            "arm_type_declarations": sorted(arms),
            "study_purpose_declarations": sorted(purpose_values),
            "unmatched_ctgov_documents": unmatched,
            "availability": {
                "structured_context_dropped_before_qualification": bool(support),
                "free_text_present_not_classified": has_prose,
                "explicit_product_kind_assertion_present": False,
                "explicit_intervention_use_assertion_present": False,
                "sponsor_organisation_is_not_product_designation": True,
                "source_type_variation": len(types) > 1,
                "mixed_arm_contexts": len(arms) > 1,
            },
            "product_kind": "UNKNOWN",
            "intervention_use": "UNKNOWN",
            "semantic_status": "NO_ADOPTED_CORRECT_SCOPE_STRUCTURED_ASSERTION",
            "note": "UNKNOWN denotes absent certified product/use semantics, not absence of raw evidence or nontherapeutic identity.",
        }
        rows.append(row)
    controls = []
    for c in json.loads((STUDY / "structural_controls.json").read_text()):
        f = native_fields(c["source"], "synthetic:" + c["id"], sha(c["source"]), c["id"])
        assert any(
            x["semantic_scope"] == "ENTITY_TYPE" and x["raw_value"] == c["expected_entity_type"]
            for x in f
        )
        assert any(
            x["semantic_scope"] == "ARM_TYPE" and x["raw_value"] == c["expected_arm_type"]
            for x in f
        )
        controls.append(
            {
                "id": c["id"],
                "assertions": f,
                "product_kind": "UNKNOWN",
                "intervention_use": "UNKNOWN",
                "kind_expectation_preserved": c["expected_product_kind"] == "UNKNOWN",
                "use_expectation_preserved": c["expected_intervention_use"] == "UNKNOWN",
            }
        )
    oldcontrols = json.loads(
        (ROOT / "research/se_h19_candidate_qualification_diagnosis_v1/population.json").read_text()
    )["controls"]
    pairs = json.loads(
        (
            ROOT
            / "research/se_therapeutic_product_role_qualification_contract_v1/structural_gap_controls.json"
        ).read_text()
    )["controls"]
    control_availability = [
        {
            "id": c["id"],
            "source_control": c,
            "availability": "FREE_TEXT_SEMANTICS_ONLY"
            if c.get("synthetic")
            else "LEGACY_QUALIFICATION_FIXTURE_NOT_TYPED_PRODUCT_ROLE_SOURCE",
            "product_kind": "UNKNOWN",
            "intervention_use": "UNKNOWN",
        }
        for c in oldcontrols
    ]
    for c in pairs:
        control_availability.append(
            {
                "id": c["id"],
                "source_control": c,
                "availability": "DISTINGUISHING_EVIDENCE_ONLY_IN_INTERVENTION_DESCRIPTION",
                "product_kind": "UNKNOWN",
                "intervention_use": "UNKNOWN",
            }
        )
    snapshot_lookup = {
        str(Path(d["snapshot_path"])): rawdocs[did]
        for did, d in docs.items()
        if d.get("snapshot_path")
    }
    snapshot_lookup[str(RUN)] = run
    for f in fields.values():
        value = snapshot_lookup[f["source"]["snapshot"]]
        for part in f["source"]["field_path"]:
            value = value[part]
        assert value == f["raw_value"] == f["normalized_value"]
        assert not f["therapeutic_product_assertion"] and not f["intervention_use_assertion"]
    product_bins = [
        "therapeutic",
        "diagnostic/imaging",
        "supportive/background",
        "other non-therapeutic",
        "ambiguous/conflicting",
        "unknown",
    ]
    use_bins = [
        "investigational therapeutic",
        "comparator",
        "background/concomitant",
        "conditioning",
        "supportive",
        "diagnostic",
        "placebo/control",
        "ambiguous",
        "unknown",
    ]
    summary = {
        "population": len(rows),
        "snapshots": len(rawdocs),
        "snapshotless_documents": len(docs) - len(rawdocs),
        "source_assertions_round_tripped": len(fields),
        "candidates_with_linked_interventions": sum(bool(x["intervention_links"]) for x in rows),
        "candidates_with_unmatched_ctgov_documents": sum(
            bool(x["unmatched_ctgov_documents"]) for x in rows
        ),
        "candidates_with_unparsed_source_text": sum(
            x["availability"]["free_text_present_not_classified"] for x in rows
        ),
        "native_entity_types_candidate_counts": dict(sorted(native_types.items())),
        "native_arm_types_candidate_counts": dict(sorted(native_arms.items())),
        "native_study_purpose_candidate_counts": dict(sorted(purposes.items())),
        "entity_type_variations": len(type_variations),
        "mixed_arm_contexts": len(arm_variations),
        "product_kind_counts": {k: len(rows) if k == "unknown" else 0 for k in product_bins},
        "intervention_use_counts": {k: len(rows) if k == "unknown" else 0 for k in use_bins},
        "cross_tab": {
            p: {u: len(rows) if p == u == "unknown" else 0 for u in use_bins} for p in product_bins
        },
        "qualification_decision_changes": 0,
        "G0": "FAIL_PROSE_OR_WRONG_SEMANTIC_LEVEL_ONLY",
        "implementation": "NOT_STARTED",
        "adoption": "NOT_ADOPTED_SOURCE_GATE_BOUNDARY",
    }
    output.mkdir(parents=True, exist_ok=False)
    data = {
        "availability.json.gz": rows,
        "source_field_ledger.json.gz": sorted(fields.values(), key=lambda f: f["assertion_id"]),
        "schema_inventory.json": {k: dict(sorted(v.items())) for k, v in sorted(schema.items())},
        "source_variations.json": {"entity_types": type_variations, "arm_contexts": arm_variations},
        "structural_control_results.json": controls,
        "prior_control_availability.json": control_availability,
        "summary.json": summary,
    }
    for n, d in data.items():
        content = (canonical(d) + "\n").encode()
        (output / n).write_bytes(gzip.compress(content, mtime=0) if n.endswith(".gz") else content)
    (output / "hashes.json").write_text(
        canonical(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
        )
        + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
