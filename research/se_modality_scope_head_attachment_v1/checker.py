"""Independent acceptance checker for MODALITY_SCOPE_HEAD_ATTACHMENT v1.

The verdict is derived only from frozen expectations vs measured extractor output; no verdict
constant exists. `--selftest` proves the checker can fail, pass and flip.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import freeze

STUDY = freeze.STUDY


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rehash(record):
    """Re-implemented assertion-id scheme: sha256 of the canonical record with an empty id."""
    body = {**record, "assertion_id": ""}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def span(text, start, end):
    return {"start": start, "end": end, "text": text[start:end]}


def apply_delta(baseline, delta):
    """Predicted post-change records: baseline with only the frozen delta applied."""
    predicted = copy.deepcopy(baseline)
    for key, changes in delta.items():
        for change in changes:
            [r] = [
                r
                for r in predicted[key]
                if (r["mention"]["start"], r["mention"]["end"], r["modality"])
                == (change["start"], change["end"], change["modality"])
            ]
            assert [r["scope"], r["rule"]] == change["before"], (key, change)
            scope, rule = change["after"]
            product = r["product_span"]
            r.update(scope=scope, rule=rule, component_span=None)
            if scope == "PRODUCT_LEVEL":
                r.update(
                    relation_span=span(r["raw_text"], product["end"], change["start"]),
                    relations=["PRODUCT_IS_MODALITY"],
                    status="EXPLICIT_RELATION",
                )
            else:
                r.update(relation_span=None, relations=[], status="AMBIGUOUS")
            r["assertion_id"] = rehash(r)
    return predicted


def check_population(actual, baseline, delta):
    failures = []
    predicted = apply_delta(baseline, delta)
    if set(actual) != set(predicted):
        failures.append(("population_keys", sorted(set(actual) ^ set(predicted))))
    for key in sorted(set(actual) & set(predicted)):
        if actual[key] != predicted[key]:
            failures.append(("unexpected_delta", key))
    return failures


def check_controls(controls, measured):
    """measured[id] = {"mentions": [...], "phrase": .., "head": .., "coordinated": ..}."""
    failures = []
    for c in controls:
        got = measured[c["id"]]
        want = sorted(
            (m["start"], m["end"], m["modality"], m["scope"], m["rule"]) for m in c["mentions"]
        )
        have = sorted(tuple(m) for m in got["mentions"])
        if want != have:
            failures.append(("control_mentions", c["id"], {"want": want, "have": have}))
        for field in ("phrase", "head", "coordinated"):
            if got[field] != c[field]:
                failures.append(("control_structure", c["id"], field, c[field], got[field]))
    return failures


def criteria(controls, measured, population_failures):
    """A1-A5/A8 derived from frozen expectations; A6/A7/A9/A10 recorded by the operator."""
    by_id = {c["id"]: c for c in controls}
    bad = {f[1] for f in check_controls(controls, measured)}

    def ok(ids):
        return all(i not in bad for i in ids)

    product_controls = [
        i for i, c in by_id.items() if any(m["scope"] == "PRODUCT_LEVEL" for m in c["mentions"])
    ]
    invented = [
        (i, m)
        for i, got in measured.items()
        for m in got["mentions"]
        if m[3] == "PRODUCT_LEVEL"
        and (m[0], m[1], m[2], m[3], m[4])
        not in {
            (x["start"], x["end"], x["modality"], x["scope"], x["rule"])
            for x in by_id[i]["mentions"]
        }
    ]
    ambiguous_ids = [
        i
        for i, c in by_id.items()
        if c["coordinated"]
        or c["phrase"] is None
        or i in {"HA15_NO_COREFERENCE", "HA20_VERB_GUARD"}
    ]
    return {
        "A1_modifier_errors_corrected": ok(
            ["HA01_MODIFIER_PEPTIDE", "HA02_MODIFIER_ANTIBODY", "HA03_MODIFIER_PAYLOAD"]
        ),
        "A2_whole_product_controls": ok(product_controls),
        "A3_population_conforms": not bad and not population_failures,
        "A4_no_invented_product_modality": not invented,
        "A5_ambiguous_structures": ok(ambiguous_ids),
        "A8_every_change_preregistered": not population_failures,
    }


def verdict(crit):
    return "ADOPT" if crit and all(crit.values()) else "FAIL"


def measure(controls):
    from bve.se.evidence.modality_scope import (
        ScopeSource,
        product_phrase,
        scoped_modality_assertions,
    )

    out = {}
    for c in controls:
        text = c["text"]
        source = ScopeSource(
            artifact="fixture",
            artifact_sha256=hashlib.sha256(text.encode()).hexdigest(),
            record_id=c["id"],
            field="text",
            product_names=tuple(c["product_names"]),
            product_locator="fixture",
        )
        rows = scoped_modality_assertions("fixture:Novel Product", text, source)
        name = c["product_names"][0]
        phrase = None
        if text.startswith(name + " is "):
            article = text[len(name) + 4 :]
            skip = 2 if article.startswith("a ") else 3 if article.startswith("an ") else 0
            start = len(name) + 4 + skip
            right = min([p for ch in ".;\n" if (p := text.find(ch, start)) >= 0] or [len(text)])
            phrase = product_phrase(text, start, right)
        out[c["id"]] = {
            "mentions": [
                [r.mention.start, r.mention.end, r.modality, r.scope, r.rule] for r in rows
            ],
            "phrase": phrase.phrase.text if phrase else None,
            "head": phrase.head.text if phrase else None,
            "coordinated": phrase.coordinated if phrase else False,
        }
    return out


def measure_population():
    return {
        f"{pop}:{cid}": freeze.records(t, cand, src, leg)
        for pop, cid, cand, t, src, leg in freeze.population()
    }


def load():
    return (
        json.loads((STUDY / "controls.json").read_text()),
        json.loads((STUDY / "baseline_records.json").read_text()),
        json.loads((STUDY / "expected_delta.json").read_text()),
    )


def selftest():
    controls, baseline, delta = load()
    # Valid fixture: measurements equal to the frozen expectations must pass.
    valid = {
        c["id"]: {
            "mentions": [
                [m["start"], m["end"], m["modality"], m["scope"], m["rule"]] for m in c["mentions"]
            ],
            "phrase": c["phrase"],
            "head": c["head"],
            "coordinated": c["coordinated"],
        }
        for c in controls
    }
    predicted = apply_delta(baseline, delta)
    v_valid = verdict(criteria(controls, valid, check_population(predicted, baseline, delta)))
    # Invalid fixture: the unpatched baseline measured against the frozen delta must fail.
    v_baseline = verdict(criteria(controls, valid, check_population(baseline, baseline, delta)))
    # Flip: re-promote the HA01 peptide modifier to PRODUCT_LEVEL in an otherwise valid measurement.
    flipped = copy.deepcopy(valid)
    flipped["HA01_MODIFIER_PEPTIDE"]["mentions"][0][3:] = [
        "PRODUCT_LEVEL",
        "explicit_product_predicate",
    ]
    crit_flip = criteria(controls, flipped, [])
    # Unregistered delta: change one untouched record.
    rogue = copy.deepcopy(predicted)
    rogue["v1_controls:S01"][0]["scope"] = "AMBIGUOUS"
    v_rogue = verdict(criteria(controls, valid, check_population(rogue, baseline, delta)))
    result = {
        "valid_fixture": v_valid,
        "unpatched_baseline": v_baseline,
        "flipped_modifier": verdict(crit_flip),
        "flipped_criteria_failed": sorted(k for k, v in crit_flip.items() if not v),
        "unregistered_delta": v_rogue,
    }
    assert result["valid_fixture"] == "ADOPT", result
    assert (
        result["unpatched_baseline"]
        == result["flipped_modifier"]
        == result["unregistered_delta"]
        == "FAIL"
    ), result
    return result


def build(out):
    controls, baseline, delta = load()
    measured = measure(controls)
    population_failures = check_population(measure_population(), baseline, delta)
    control_failures = check_controls(controls, measured)
    crit = criteria(controls, measured, population_failures)
    summary = {
        "criteria": crit,
        "verdict_from_frozen_expectations": verdict(crit),
        "control_failures": control_failures,
        "population_failures": population_failures,
        "controls": len(controls),
        "population_inputs": len(baseline),
        "population_records": sum(map(len, baseline.values())),
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "measured_controls.json").write_text(canonical(measured) + "\n")
    (out / "measured_population.json").write_text(canonical(measure_population()) + "\n")
    (out / "summary.json").write_text(canonical(summary) + "\n")
    (out / "hashes.json").write_text(
        canonical(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
        )
        + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        print(canonical(selftest()))
    else:
        build(a.output)
