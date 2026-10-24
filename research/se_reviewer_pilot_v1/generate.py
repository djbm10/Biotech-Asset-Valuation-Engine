"""Offline presentation demonstration. No discovery, ranking or qualification is performed."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import date
from pathlib import Path

from bve.se.reporting.bd_brief import (
    _CSS,
    Assessed,
    CandidateCard,
    EvidenceStatus,
    _h_card,
    _md_card,
)
from bve.se.reporting.research_followup import attach_followup, load_followup

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/se_lead_verification_v1"
PACKAGE = Path(__file__).parent
AS_OF = date(2026, 10, 24)


def generate(output: Path) -> None:
    # Fresh directory is mandatory; historical runs and responses must never be overwritten.
    output.mkdir(parents=True, exist_ok=False)
    for name in ("leads.json", "evidence.json", "BRIEF.md", "TRIALS.md"):
        (output / name).write_bytes((SOURCE / name).read_bytes())
    for name in ("START_HERE.md", "REVIEW_FORM.md", "BEFORE_AFTER.md"):
        (output / name).write_bytes((PACKAGE / name).read_bytes())
    records = json.loads((output / "leads.json").read_text())
    before, after = [], []
    unknown = Assessed(
        value=None,
        status=EvidenceStatus.UNKNOWN,
        basis="Display scaffold only; no engine run for this follow-up.",
    )
    for i, lead in enumerate(records["leads"], 1):
        card = CandidateCard(
            asset_id=f"research-demo:{i}",
            name=lead["name"],
            position=i,
            eligibility="NOT_EVALUATED",
            disposition="RESEARCH_DISPLAY_ONLY",
            why="Manually selected contrast case; no new autonomous discovery credit.",
            company=unknown,
            target=unknown,
            modality=unknown,
            stage=unknown,
            human_efficacy=unknown,
        )
        followup = load_followup(
            output / "leads.json",
            output / "evidence.json",
            asset_id=card.asset_id,
            name=card.name,
            verified_on=AS_OF,
            display_as_of=AS_OF,
            verification="Prior implementing-agent manual source review; independent BD review pending",
        )
        # Shareable relative locators; provenance digests and original evidence paths are retained.
        followup = followup.model_copy(
            update={"record_locator": "leads.json", "ledger_locator": "evidence.json"}
        )
        before.append(card)
        after.append(attach_followup(card, followup))
    title = "Two-asset manual research display — UNVALIDATED"
    introduction = (
        "This output is UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability. "
        "Question: which CD19- or BCMA-directed T-cell engager programs merit autoimmune research? "
        "Two manually selected contrast cases, not a discovery or qualification run. "
        "Order is not a ranking. Engine fields are synthetic UNKNOWN scaffolds; "
        "the separate manual section reuses the previously audited records as of 2026-10-24 UTC. "
        "Read BRIEF.md first and complete REVIEW_FORM.md. Independent BD review pending."
    )
    for label, cards in (("before", before), ("after", after)):
        page = (
            f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{title}</title>"
            f"<style>{_CSS}</style><body><h1>{title}</h1>"
            f"<p class='banner'>{html.escape(introduction)}</p>"
            + "".join(_h_card(c) for c in cards)
            + "<h2>Known limitations</h2><ul>"
            + "".join(f"<li>{html.escape(x)}</li>" for x in records["limitations"])
            + "</ul></body></html>\n"
        )
        markdown = (
            f"# {title}\n\n{introduction}\n\n"
            + "\n".join(line for c in cards for line in _md_card(c))
            + "\n## Known limitations\n\n"
            + "\n".join(f"- {x}" for x in records["limitations"])
            + "\n"
        )
        (output / f"{label}.html").write_text(page)
        (output / f"{label}.md").write_text(markdown)
        (output / f"{label}.json").write_text(
            json.dumps(
                {
                    "validation_grade": "UNVALIDATED",
                    "run_status": "DISPLAY_DEMONSTRATION",
                    "as_of_date": AS_OF.isoformat(),
                    "cards": [c.model_dump(mode="json") for c in cards],
                },
                indent=2,
            )
            + "\n"
        )
    invariant = all(
        a.model_dump() == {k: v for k, v in b.model_dump().items() if k != "research_followup"}
        for a, b in zip(before, after, strict=True)
    )
    if not invariant:
        raise AssertionError("original card changed")
    (output / "review_status.json").write_text(
        json.dumps(
            {
                "validation_grade": "UNVALIDATED",
                "independent_bd_review": "PENDING",
                "response_count": 0,
                "usefulness": None,
                "missing_information": None,
                "misleading_claims": None,
                "time_to_action_seconds": None,
                "would_use_again": None,
                "original_card_fields_unchanged": invariant,
                "autonomous_qualification_improvement": "NOT_DEMONSTRATED",
                "raw_evidence_note": "Pointers preserved; archived raw files are not in this share package.",
            },
            indent=2,
        )
        + "\n"
    )
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.iterdir())
        if p.is_file()
    }
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    generate(parser.parse_args().output_dir)
