"""Offline reference-assisted analyst worklist; never counts as engine discovery."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent / "se_bd_discovery_source_coverage_v1"
WARNING = (
    "UNVALIDATED development worklist. Do not use for trade sizing or acquisition "
    "probability. Reference-assisted leads, not engine discoveries. Frozen as of "
    "2026-10-15; current programme status requires verification."
)


def build() -> list[dict]:
    raw = json.loads((STUDY / "reference_raw.json").read_text())
    frozen = json.loads((STUDY / "reference_frozen.json").read_text())
    rows = {r["ref_id"]: r for r in raw["entries"]}
    result = []
    for entry in frozen["entries"]:
        source = rows[entry["ref_id"]]
        fields = {}
        for key, value in (
            ("identity", source["name"]),
            ("target", source.get("targets")),
            ("modality", source.get("modality")),
            ("indication", source.get("indications")),
            ("phase", source.get("phase")),
            ("company", source.get("company")),
        ):
            evidence = [e for e in source.get("evidence", []) if key in e["supports"]]
            fields[key] = {
                "value": value,
                "status": "QUOTED_REFERENCE" if evidence else "UNVERIFIED",
                "evidence": evidence,
            }
        result.append(
            {
                **entry,
                "fields": fields,
                "notes": source.get("notes", ""),
                "human_efficacy": "UNVERIFIED: no adjudicated human PoC in this worklist",
                "commercial_rights": "UNKNOWN: company attribution is not ownership or availability",
            }
        )
    return result


def render(rows: list[dict]) -> str:
    lines = [
        "# S&E analyst worklist: CD19/BCMA engagers in autoimmune disease",
        "",
        f"> {WARNING}",
        "",
        (
            "This worklist makes the existing independently sourced development reference usable "
            "for manual investigation. It adds no retrieved assets or scientific validation. "
            "QUOTED_REFERENCE means the frozen verification found a supporting quotation; "
            "it does not establish primary-source quality, current status, clinical efficacy, "
            "or passage entailment beyond the original annotation."
        ),
        "",
        (
            "Search A asks for CD19 **or** BCMA; Search B asks for CD19 **and** BCMA. "
            "The frozen MATCH labels are retained as reference annotations, not eligibility "
            "decisions: phase and disease-specific human evidence still need review."
        ),
        "",
        (
            "Start with relevant investigational entries, open the field-level evidence, "
            "then verify product identity, indication-specific trial stage and results, "
            "approval across jurisdictions, and territory-specific rights. "
            "A missing licensing agreement is not evidence of availability."
        ),
        "",
        "| ID | Asset | Frozen reference category | A | B | Quoted target? |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['ref_id']} | {row['name']} | {row['label']} | "
            f"{row['search_A']} | {row['search_B']} | {row['fields']['target']['status']} |"
        )
    for row in rows:
        lines += [
            "",
            f"## {row['ref_id']} — {row['name']}",
            "",
            (
                f"**Category:** {row['label']}. **Why here:** manually included in the frozen "
                f"development reference; A={row['search_A']}, B={row['search_B']}."
            ),
            "",
        ]
        for key, field in row["fields"].items():
            value = field["value"]
            if isinstance(value, list):
                value = "; ".join(value)
            lines += [f"**{key}: {field['status']}** — {value or 'Unknown'}", ""]
            for evidence in field["evidence"]:
                lines += [f"- [Source]({evidence['url']}): {evidence['passage']}", ""]
        lines += [
            f"**Human efficacy:** {row['human_efficacy']}",
            "",
            f"**Commercial rights:** {row['commercial_rights']}",
            "",
            f"**Reference caveats:** {row['notes'] or 'None recorded; not proof of completeness.'}",
            "",
            (
                "**Before diligence:** verify the named product against a primary product "
                "description; distinguish registered/planned trials from reported results; "
                "confirm autoimmune cohort, dose, n, endpoint, follow-up and safety; check "
                "global approval, discontinued status and licence territories with dated sources."
            ),
        ]
    lines += [
        "",
        "## Other established development example",
        "",
        (
            "The CD19 cell-therapy/B-cell-lymphoma and dual-target autoimmune frozen briefs "
            "remain in docs/demos/bd_opportunity_triage_v1/. Their original run inputs were "
            "not restored, so this work does not claim to regenerate or reassess those runs."
        ),
        "",
        "## Evaluation limits",
        "",
        (
            "No new recall measurement, timed analyst trial, independent review of this final "
            "worklist, or GO decision. Existing reference errors and secondary-source reliance "
            "remain visible. See STATUS.md for the connector inventory and blockers."
        ),
    ]
    return "\n".join(lines) + "\n"


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    rows = build()
    markdown = render(rows)
    (output / "brief.md").write_text(markdown)
    # Keep the text identical and all source URLs clickable without a Markdown dependency.
    import re

    page = html.escape(markdown)
    page = re.sub(r"\[Source\]\((https?://[^\s)]+)\)", r'<a href="\1">Source</a>', page)
    (output / "brief.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        "<title>S&E reference-assisted worklist</title><style>body{max-width:1000px;"
        "margin:2em auto;padding:1em;font:16px system-ui}pre{white-space:pre-wrap;"
        "overflow-wrap:anywhere;font:inherit}</style><pre>" + page + "</pre>\n"
    )
    (output / "worklist.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    main(parser.parse_args().output_dir)
