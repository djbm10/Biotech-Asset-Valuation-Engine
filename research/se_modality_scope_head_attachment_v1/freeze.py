"""Freeze head-attachment controls and the pre-implementation baseline. Run once, before src edits."""

import hashlib
import json
from pathlib import Path

from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_modality_scope_head_attachment_v1"
V1 = ROOT / "research/se_modality_assertion_scope_representation_v1"
V2 = ROOT / "research/se_product_vs_component_modality_semantics_v2"

P, A = "PRODUCT_LEVEL", "AMBIGUOUS"
HEAD, NOT_HEAD, COORD, OLD = (
    "explicit_product_predicate",
    "product_phrase_not_head",
    "product_phrase_coordination",
    "unproven_subject_or_relation",
)
ADC, MAB, PEP, SM = "ANTIBODY_DRUG_CONJUGATE", "MONOCLONAL_ANTIBODY", "PEPTIDE", "SMALL_MOLECULE"

# (id, text, [(mention, start, modality, scope, rule)], phrase|None, head|None, coordinated)
CONTROLS = [
    (
        "HA01_MODIFIER_PEPTIDE",
        "Novel Product is a peptide-linked antibody-drug conjugate.",
        [
            ("peptide", 19, PEP, A, NOT_HEAD),
            ("antibody", 34, MAB, A, NOT_HEAD),
            ("antibody-drug conjugate", 34, ADC, P, HEAD),
        ],
        "peptide-linked antibody-drug conjugate",
        "conjugate",
        False,
    ),
    (
        "HA02_MODIFIER_ANTIBODY",
        "Novel Product is an antibody-derived cell therapy.",
        [("antibody", 20, MAB, A, NOT_HEAD), ("cell therapy", 37, "CELL_THERAPY", P, HEAD)],
        "antibody-derived cell therapy",
        "therapy",
        False,
    ),
    (
        "HA03_MODIFIER_PAYLOAD",
        "Novel Product is a small-molecule-loaded nanoparticle.",
        [("small-molecule", 19, SM, A, NOT_HEAD)],
        "small-molecule-loaded nanoparticle",
        "nanoparticle",
        False,
    ),
    (
        "HA04_PREMOD_HYPHEN",
        "Novel Product is a first-in-class ADC.",
        [("ADC", 34, ADC, P, HEAD)],
        "first-in-class ADC",
        "ADC",
        False,
    ),
    (
        "HA05_PREMOD_TARGET",
        "Novel Product is an anti-TROP2 antibody.",
        [("antibody", 31, MAB, P, HEAD)],
        "anti-TROP2 antibody",
        "antibody",
        False,
    ),
    (
        "HA06_HYPHEN_BASED",
        "Novel Product is a peptide-based therapeutic.",
        [("peptide", 19, PEP, A, NOT_HEAD)],
        "peptide-based therapeutic",
        "therapeutic",
        False,
    ),
    (
        "HA07_HYPHEN_TARGETED",
        "Novel Product is an antibody-targeted gene therapy.",
        [("antibody", 20, MAB, A, NOT_HEAD), ("gene therapy", 38, "GENE_THERAPY", P, HEAD)],
        "antibody-targeted gene therapy",
        "therapy",
        False,
    ),
    (
        "HA08_MULTIWORD_CART",
        "Novel Product is a CAR-T cell therapy.",
        [
            ("CAR-T", 19, "CAR_T", A, NOT_HEAD),
            ("CAR-T cell", 19, "CAR_T", P, HEAD),
            ("CAR-T cell therapy", 19, "CAR_T", P, HEAD),
            ("cell therapy", 25, "CELL_THERAPY", P, HEAD),
        ],
        "CAR-T cell therapy",
        "therapy",
        False,
    ),
    (
        "HA09_NESTED_PAYLOAD",
        "Novel Product is an ADC with a peptide-linked payload.",
        [("ADC", 20, ADC, P, HEAD), ("peptide", 31, PEP, A, OLD)],
        "ADC",
        "ADC",
        False,
    ),
    (
        "HA10_NESTED_DOMAIN",
        "Novel Product is a cell therapy with an antibody-derived binding domain.",
        [
            ("cell therapy", 19, "CELL_THERAPY", P, HEAD),
            ("antibody", 40, MAB, "COMPONENT_LEVEL", "explicit_component_relation"),
        ],
        "cell therapy",
        "therapy",
        False,
    ),
    (
        "HA11_UNRECOGNIZED_HEAD",
        "Novel Product is a peptide-conjugated nanoparticle.",
        [("peptide", 19, PEP, A, NOT_HEAD), ("peptide-conjugate", 19, PEP, A, OLD)],
        "peptide-conjugated nanoparticle",
        "nanoparticle",
        False,
    ),
    (
        "HA12_FRAGMENT_HEAD",
        "Novel Product is an antibody fragment.",
        [("antibody", 20, MAB, A, NOT_HEAD)],
        "antibody fragment",
        "fragment",
        False,
    ),
    (
        "HA13_CONFLICT",
        "Novel Product is a peptide therapeutic. Novel Product is an antibody.",
        [("peptide", 19, PEP, P, HEAD), ("antibody", 60, MAB, P, HEAD)],
        "peptide therapeutic",
        "therapeutic",
        False,
    ),
    (
        "HA14_MISSING_SUBJECT",
        "Is a peptide-linked antibody-drug conjugate.",
        [
            ("peptide", 5, PEP, A, OLD),
            ("antibody", 20, MAB, A, OLD),
            ("antibody-drug conjugate", 20, ADC, A, OLD),
        ],
        None,
        None,
        False,
    ),
    (
        "HA15_NO_COREFERENCE",
        "Novel Product is an ADC. It is a peptide-linked antibody-drug conjugate.",
        [
            ("ADC", 20, ADC, P, HEAD),
            ("peptide", 33, PEP, A, OLD),
            ("antibody", 48, MAB, A, OLD),
            ("antibody-drug conjugate", 48, ADC, A, OLD),
        ],
        "ADC",
        "ADC",
        False,
    ),
    (
        "HA16_GENERIC_THERAPY",
        "Novel Product is an antibody therapy.",
        [("antibody", 20, MAB, P, HEAD)],
        "antibody therapy",
        "therapy",
        False,
    ),
    (
        "HA17_GENERIC_PRODUCT",
        "Novel Product is a small-molecule product.",
        [("small-molecule", 19, SM, P, HEAD)],
        "small-molecule product",
        "product",
        False,
    ),
    (
        "HA18_COORDINATION",
        "Novel Product is a peptide and antibody combination.",
        [("peptide", 19, PEP, A, COORD), ("antibody", 31, MAB, A, COORD)],
        "peptide and antibody combination",
        "combination",
        True,
    ),
    (
        "HA19_COORDINATION_OR",
        "Novel Product is a peptide or antibody.",
        [("peptide", 19, PEP, A, COORD), ("antibody", 30, MAB, A, COORD)],
        "peptide or antibody",
        "antibody",
        True,
    ),
    (
        "HA20_VERB_GUARD",
        "Novel Product is given after an ADC.",
        [("ADC", 32, ADC, A, OLD)],
        "given",
        "given",
        False,
    ),
    (
        "HA21_PLAIN_PREMOD",
        "Novel Product is a novel peptide therapeutic.",
        [("peptide", 25, PEP, A, NOT_HEAD)],
        "novel peptide therapeutic",
        "therapeutic",
        False,
    ),
    (
        "HA22_PDC",
        "Novel Product is a peptide-drug conjugate.",
        [("peptide", 19, PEP, A, NOT_HEAD)],
        "peptide-drug conjugate",
        "conjugate",
        False,
    ),
    (
        "HA23_BISPECIFIC",
        "Novel Product is a bispecific antibody.",
        [
            ("bispecific", 19, "BISPECIFIC_ANTIBODY", A, NOT_HEAD),
            ("bispecific antibody", 19, "BISPECIFIC_ANTIBODY", P, HEAD),
            ("antibody", 30, MAB, A, NOT_HEAD),
        ],
        "bispecific antibody",
        "antibody",
        False,
    ),
    (
        "HA24_SIRNA",
        "Novel Product is an siRNA therapeutic.",
        [
            ("siRNA", 20, "RNA_THERAPEUTIC", P, HEAD),
            ("RNA therapeutic", 22, "RNA_THERAPEUTIC", A, OLD),
        ],
        "siRNA therapeutic",
        "therapeutic",
        False,
    ),
    (
        "HA25_HYPHEN_NEGATED_MODIFIER",
        "Novel Product is a non-peptide small molecule.",
        [("peptide", 23, PEP, A, NOT_HEAD), ("small molecule", 31, SM, P, HEAD)],
        "non-peptide small molecule",
        "molecule",
        False,
    ),
]


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def v1_source(text):
    return ScopeSource(
        artifact="fixture",
        artifact_sha256=hashlib.sha256(text.encode()).hexdigest(),
        record_id="fixture",
        field="description",
        product_names=("Novel Product", "Dato-DXd"),
        product_locator="intervention.name+otherNames",
    )


def v2_source(path, i, cid):
    return ScopeSource(
        artifact=str(path),
        artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        record_id=cid,
        field=f"/{i}/text",
        product_names=("Novel Product",),
        product_locator="fixture subject Novel Product",
    )


def population():
    """Every pre-existing frozen scope input: (population, id, candidate, text, source, legacy ids)."""
    for c in json.loads((V1 / "controls.json").read_text()):
        yield "v1_controls", c["id"], "candidate", c["text"], v1_source(c["text"]), ()
    path = V2 / "additional_controls.json"
    for i, c in enumerate(json.loads(path.read_text())):
        yield (
            "v2_controls",
            c["id"],
            "fixture:Novel Product",
            c["text"],
            v2_source(path, i, c["id"]),
            (),
        )
    saved = json.loads((V1 / "results/h19_assertions.json").read_text())
    first = saved[0]
    assert all(r["raw_text"] == first["raw_text"] and r["source"] == first["source"] for r in saved)
    yield (
        "h19",
        "H19_DATO",
        first["candidate_id"],
        first["raw_text"],
        ScopeSource(**first["source"]),
        tuple(first["legacy_fact_ids"]),
    )


def records(text, candidate, source, legacy=()):
    return [
        r.model_dump(mode="json")
        for r in scoped_modality_assertions(candidate, text, source, legacy_fact_ids=legacy)
    ]


if __name__ == "__main__":
    controls = [
        {
            "id": i,
            "text": t,
            "product_names": ["Novel Product"],
            "mentions": [
                {"text": m, "start": s, "end": s + len(m), "modality": mod, "scope": sc, "rule": r}
                for m, s, mod, sc, r in ms
            ],
            "phrase": ph,
            "head": hd,
            "coordinated": co,
        }
        for i, t, ms, ph, hd, co in CONTROLS
    ]
    for c in controls:
        for m in c["mentions"]:
            assert c["text"][m["start"] : m["end"]] == m["text"], (c["id"], m)
    (STUDY / "controls.json").write_text(json.dumps(controls, indent=1) + "\n")
    baseline = {
        f"{pop}:{cid}": records(t, cand, src, leg) for pop, cid, cand, t, src, leg in population()
    }
    (STUDY / "baseline_records.json").write_text(canonical(baseline) + "\n")
