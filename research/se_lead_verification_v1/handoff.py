"""Render manually verified follow-up facts; never mutate engine qualification or gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from bve.se.reporting.bd_brief import Assessed, EvidenceStatus

FIELDS = (
    "identity",
    "target_format",
    "development",
    "human_evidence",
    "approval",
    "company_relationship",
    "territorial_rights",
    "availability",
)


class Lead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    research_category: Literal[
        "PRECLINICAL_RESEARCH_LEAD",
        "CLINICAL_INVESTIGATIONAL",
        "APPROVED_COMPARATOR",
        "INSUFFICIENTLY_IDENTIFIED",
    ]
    commercial_context: Literal["ACQUIRED_PROGRAM", "PARTNERED_PROGRAM", "UNKNOWN"]
    facts: dict[str, Assessed]
    why_investigate: str
    next_actions: list[str]

    @model_validator(mode="after")
    def require_evidence(self) -> Lead:
        if set(self.facts) != set(FIELDS):
            raise ValueError("all independent qualification dimensions are required")
        for fact in self.facts.values():
            if fact.status == EvidenceStatus.SUPPORTED and (
                not fact.value or not fact.sources or any(not s.url for s in fact.sources)
            ):
                raise ValueError("supported facts require values and primary source links")
        if (
            self.commercial_context != "UNKNOWN"
            and self.facts["company_relationship"].status != EvidenceStatus.SUPPORTED
        ):
            raise ValueError("acquired/partnered context requires sourced company evidence")
        if (
            self.research_category != "INSUFFICIENTLY_IDENTIFIED"
            and self.facts["identity"].status != EvidenceStatus.SUPPORTED
        ):
            raise ValueError("named lead requires source-backed identity")
        if (
            self.research_category == "APPROVED_COMPARATOR"
            and self.facts["approval"].status != EvidenceStatus.SUPPORTED
        ):
            raise ValueError("approved comparator requires approval evidence")
        if (
            self.research_category in {"PRECLINICAL_RESEARCH_LEAD", "CLINICAL_INVESTIGATIONAL"}
            and self.facts["development"].status != EvidenceStatus.SUPPORTED
        ):
            raise ValueError("development category requires development evidence")
        return self


def verify_pointers(root: Path, ledger: dict) -> None:
    """Verify local archived evidence, including exact selected spans and JSON values."""
    for evidence in ledger["evidence"]:
        path = (root / evidence["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("unsafe evidence path")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != evidence["file_sha256"]:
            raise ValueError("evidence file changed")
        if "start" in evidence:
            text = raw.decode()
            start, end = evidence["start"], evidence["end"]
            if not 0 <= start < end <= len(text):
                raise ValueError("invalid evidence offsets")
            selected = text[start:end].encode()
        else:
            value = json.loads(raw)
            for key in evidence["json_path"]:
                value = value[key]
            selected = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        if hashlib.sha256(selected).hexdigest() != evidence["selection_sha256"]:
            raise ValueError("evidence selection changed")


def render(data: dict) -> str:
    leads = [Lead.model_validate(row) for row in data["leads"]]
    if len({lead.name.casefold() for lead in leads}) != len(leads):
        raise ValueError("duplicate lead")
    lines = [
        "# Autoimmune engager follow-up: HXN-1031 and cizutamig",
        "",
        "**UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability.**",
        (
            f"Observed: {data['observed_date']}. Manual primary-source verification; "
            "independent BD review **OUTSTANDING**."
        ),
        "",
        (
            "Named follow-up to discovery v1; no retrospective discovery credit, identity merges, "
            "scientific gate evaluation or human-PoC promotion."
        ),
        "",
    ]
    for lead in leads:
        lines += [
            f"## {lead.name}",
            "",
            f"**{lead.research_category} · {lead.commercial_context}**",
            "",
            lead.why_investigate,
            "",
            "| Dimension | Finding |",
            "|---|---|",
        ]
        for field in FIELDS:
            fact = lead.facts[field]
            citations = " ".join(f"[{s.label}]({s.url})" for s in fact.sources)
            value = (fact.value or "Unknown").replace("|", "\\|").replace("\n", " ")
            basis = fact.basis.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {field.replace('_', ' ').title()} | **{fact.status.value}** — "
                f"{value}. {basis} {citations} |"
            )
        lines += ["", "Next actions:", "", *[f"- {a}" for a in lead.next_actions], ""]
    lines += ["## Interpretation and limits", "", *data["limitations"], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    ledger = json.loads((root / "evidence.json").read_text())
    verify_pointers(root, ledger)
    data = json.loads((root / "leads.json").read_text())
    known = {e["id"]: e["url"] for e in ledger["evidence"]}
    for lead in data["leads"]:
        for fact in lead["facts"].values():
            if any(known.get(s["label"]) != s["url"] for s in fact.get("sources", [])):
                raise ValueError("unregistered source reference")
    with args.output.open("x") as output:
        output.write(render(data))
