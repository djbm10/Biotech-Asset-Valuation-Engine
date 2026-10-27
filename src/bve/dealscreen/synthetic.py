"""Seeded generator for the SYNTHETIC 200-row demonstration landscape.

Every program, company, code, trial ID and URL here is invented. Trial IDs use a
``SYNTRIAL-`` prefix and URLs use ``example.org`` so nothing can be mistaken for, or
fetched as, a real record.

Outputs:
- the landscape (CSV + XLSX): the only application input;
- ``ground_truth.json``: the correct business answer per program, written separately and
  read only by the evaluation, never by the application;
- ``evidence_library.json``: synthetic public-style documents for the offline agent;
- ``reviewer_fixture.csv``: decisions by a LABELLED synthetic reviewer;
- ``valuation_assumptions.yaml``: HYPOTHETICAL analyst-owned financial inputs.

The archetype counts below are a plausible landscape mix chosen before any screening was
run. The funnel, shortlist and ranking are whatever the software produces from them.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SEED = 20261026
HEADERS = [
    "Drug ID", "Source", "Drug Name", "Synonyms", "Target(s)", "Mechanism of Action", "Technology",
    "Therapy Area", "Indication(s)", "Highest Phase", "Development Status", "Status Date",
    "Originator", "Trial IDs", "US Rights", "Territory Rights", "Deals / Partnerships",
    "Source URL", "Last Updated", "Data Notes",
]
TOTAL_ROWS = 200

_PREFIX = ["vel", "cor", "tal", "mir", "san", "ober", "lun", "kas", "dri", "fen", "gal", "hes",
           "iro", "jun", "kel", "lor", "mav", "nor", "pel", "quin", "ros", "sel", "tor", "ula",
           "var", "wen", "xan", "yor", "zel", "bra", "cly", "dax", "eno", "fyr", "gor", "hal"]
_MIDDLE = ["a", "i", "o", "e", "u", "ri", "to", "li", "ne", "ve", "ra", "zo"]
_COMPANIES = [
    "Northbay Bio", "Corvane Bio", "Halden Therapeutics", "Ostrava Biologics", "Pellucid Pharma",
    "Quarry Immunology", "Redwater Bio", "Silverleaf Therapeutics", "Tamsin Biosciences",
    "Umberfield Pharma", "Vireo Labs", "Westmark Bio", "Yarrow Therapeutics", "Zephyr Antibodies",
    "Aldermoor Bio", "Brightwell Pharma", "Cinder Biotherapeutics", "Dunmore Bio",
    "Eastlake Immunotherapies", "Foxglove Bio",
]
_PARTNERS = ["Large Pharma A (synthetic)", "Large Pharma B (synthetic)", "Regional Partner C (synthetic)"]
_IBD = ["Ulcerative colitis", "Crohn's disease", "Ulcerative colitis; Crohn's disease",
        "Inflammatory bowel disease"]
_PHASES_IN_SCOPE = ["Phase 1"] * 6 + ["Phase 1/2"] * 2 + ["Phase 2"] * 8 + ["Phase 2/3"] + ["Phase 3"] * 3


@dataclass
class Program:
    external_id: str
    name: str
    aliases: list[str]
    target: str
    mechanism: str
    technology: str
    area: str
    indication: str
    phase: str
    status: str
    company: str
    archetype: str
    truth_disposition: str
    truth_note: str
    us_rights: str = ""
    territory: str = ""
    deals: str = ""
    notes: str = ""
    trials: list[str] = field(default_factory=list)
    extra_rows: list[dict[str, str]] = field(default_factory=list)
    resolvable_by_research: bool = False


class _Names:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.used: set[str] = set()
        self.codes: set[str] = set()

    def inn(self, suffix: str) -> str:
        while True:
            name = (self.rng.choice(_PREFIX) + self.rng.choice(_MIDDLE) + suffix).capitalize()
            if name not in self.used:
                self.used.add(name)
                return name

    def code(self, prefix: str | None = None) -> str:
        while True:
            letters = prefix or "".join(self.rng.choice("ABCDEFGHJKLMNPRSTVWXZ") for _ in range(2))
            code = f"{letters}-{self.rng.randint(100, 999)}"
            if code not in self.codes:
                self.codes.add(code)
                return code


def _programs(rng: random.Random) -> list[Program]:
    names = _Names(rng)
    trial_counter = iter(range(1, 10_000))
    out: list[Program] = []

    def trials(n: int) -> list[str]:
        return [f"SYNTRIAL-{next(trial_counter):05d}" for _ in range(n)]

    def add(archetype: str, truth: str, note: str, *, target: str, mechanism: str, technology: str,
            area: str, indication: str, phase: str, suffix: str = "mab", status: str = "Active",
            **kw: Any) -> Program:
        code = kw.pop("code", None) or names.code()
        name = kw.pop("name", None) or names.inn(suffix)
        aliases = kw.pop("aliases", None) or [code]
        n_trials = kw.pop("n_trials", rng.randint(0, 3))
        program = Program(
            external_id=f"SYN-{len(out) + 1:04d}", name=name, aliases=aliases, target=target,
            mechanism=mechanism, technology=technology, area=area, indication=indication, phase=phase,
            status=status, company=kw.pop("company", None) or rng.choice(_COMPANIES),
            archetype=archetype, truth_disposition=truth, truth_note=note, trials=trials(n_trials), **kw,
        )
        out.append(program)
        return program

    rights_pool = (["U.S. rights available; company seeking a partner"] * 4
                   + ["U.S. rights exclusively licensed to {p}"] * 4
                   + ["Ex-US rights partnered with {p}; U.S. rights not reported"] * 3
                   + ["Not reported"] * 4 + [""] * 5)
    rng.shuffle(rights_pool)
    for i, phase in enumerate(_PHASES_IN_SCOPE):
        rights = rights_pool[i].format(p=rng.choice(_PARTNERS))
        deals = f"License: {rng.choice(_PARTNERS)}" if "licensed" in rights or "partnered" in rights else ""
        code = names.code()
        add("in_scope_tl1a_mab", "ELIGIBLE", "Anti-TL1A antagonist antibody in IBD, clinical stage.",
            target="TL1A", mechanism="TL1A antagonist; blocks TL1A-DR3 binding",
            technology=rng.choice(["Monoclonal antibody", "mAb"]), area=rng.choice(["Immunology", "Gastroenterology"]),
            indication=rng.choice(_IBD), phase=phase, code=code,
            aliases=[code, code.replace("-", "")] + ([f"{code[:2]}{rng.randint(1000, 9999)}"] if i % 3 == 0 else []),
            us_rights=rights, deals=deals, n_trials=rng.randint(1, 4),
            territory="Global" if "available" in rights else "")
    for _ in range(2):
        add("in_scope_bispecific", "ELIGIBLE", "TL1A x IL-23 bispecific antagonist in IBD.",
            target="TL1A; IL23A", mechanism="Dual TL1A and IL-23 neutralizing bispecific",
            technology="Bispecific antibody", area="Immunology", indication=rng.choice(_IBD),
            phase=rng.choice(["Phase 1", "Phase 2"]), suffix="bart", n_trials=rng.randint(1, 2))
    for _ in range(2):
        add("in_scope_dr3_antagonist", "ELIGIBLE", "Anti-DR3 antagonist antibody in IBD.",
            target="DR3", mechanism="DR3 antagonist antibody", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase=rng.choice(["Phase 1", "Phase 2"]),
            n_trials=1)
    for _ in range(2):
        add("discontinued_historical_p2", "ELIGIBLE",
            "Discontinued anti-TL1A program with historical Phase 2 data: scientifically in scope, "
            "development inactive (a ranking and diligence matter, not a hard gate).",
            target="TL1A", mechanism="TL1A neutralizing antibody", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase="Phase 2",
            status="Discontinued (2024)", n_trials=2, notes="Program discontinued; data from Phase 2 retained.")
    for _ in range(4):
        add("tl1a_preclinical", "EXCLUDED", "Preclinical; buyer requires clinical stage.",
            target="TL1A", mechanism="TL1A antagonist", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase="Preclinical", n_trials=0)
    for _ in range(3):
        add("tl1a_small_molecule", "EXCLUDED", "Oral small molecule; buyer requires an antibody.",
            target="TL1A", mechanism="Oral TL1A inhibitor", technology="Small molecule",
            area="Gastroenterology", indication=rng.choice(_IBD), phase=rng.choice(["Phase 1", "Phase 2"]),
            suffix="tinib" if rng.random() < 0.5 else "pradib")
    for _ in range(2):
        add("dr3_agonist_antibody", "EXCLUDED",
            "Antibody against the right axis with the wrong mechanism: a DR3 agonist.",
            target="DR3", mechanism="DR3 agonist antibody (Treg expansion)", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase="Phase 1")
    add("tl1a_cell_therapy", "EXCLUDED", "Cell therapy, not an antibody.",
        target="TL1A", mechanism="TL1A-directed CAR-T cells (antagonist-armed)", technology="CAR-T",
        area="Immunology", indication="Crohn's disease", phase="Phase 1", suffix="cel")
    for indication in ("Systemic sclerosis", "Psoriasis", "Rheumatoid arthritis"):
        add("tl1a_non_ibd", "EXCLUDED",
            "In-scope molecule class outside the buyer's indication. The gate engine cannot "
            "establish incompatibility from registry text, so UNRESOLVED is its expected output.",
            target="TL1A", mechanism="TL1A antagonist", technology="Monoclonal antibody",
            area="Immunology", indication=indication, phase=rng.choice(["Phase 1", "Phase 2"]))
    for _ in range(3):
        add("missing_target_researchable", "UNRESOLVED",
            "Target field blank in the vendor export; the public evidence library names TL1A.",
            target="", mechanism="Neutralizing antibody", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase=rng.choice(["Phase 1", "Phase 2"]),
            resolvable_by_research=True, notes="Target not captured")
    for _ in range(3):
        add("undisclosed_target", "UNRESOLVED", "Target undisclosed; nothing public resolves it.",
            target="Undisclosed", mechanism="Antagonist antibody", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase=rng.choice(["Phase 1", "Phase 2"]))
    for technology in ("Biologic", "Humanized IgG1 antibody", "Biologic"):
        add("unreadable_modality", "UNRESOLVED",
            "Anti-TL1A program whose modality text the vocabulary cannot read; needs confirmation.",
            target="TL1A", mechanism="TL1A antagonist", technology=technology, area="Immunology",
            indication=rng.choice(_IBD), phase=rng.choice(["Phase 1", "Phase 2"]))
    for _ in range(2):
        p = add("conflicting_phase", "UNRESOLVED",
                "Two vendor records for the same program disagree on phase.",
                target="TL1A", mechanism="TL1A antagonist", technology="Monoclonal antibody",
                area="Immunology", indication=rng.choice(_IBD), phase="Phase 2")
        p.extra_rows.append({"Highest Phase": "Phase 1", "Last Updated": "2025-03-01",
                             "Data Notes": "Older record"})
    p = add("conflicting_target", "UNRESOLVED", "Two vendor records disagree on the target.",
            target="TL1A", mechanism="Antagonist antibody", technology="Monoclonal antibody",
            area="Immunology", indication=rng.choice(_IBD), phase="Phase 2")
    p.extra_rows.append({"Target(s)": "IL23A", "Last Updated": "2025-02-11", "Data Notes": "Secondary record"})
    # The MB-102 failure class: two companies' unrelated molecules share one code.
    add("shared_code_in_scope", "ELIGIBLE",
        "In-scope anti-TL1A antibody whose code is also used by an unrelated oncology molecule.",
        target="TL1A", mechanism="TL1A antagonist", technology="Monoclonal antibody", area="Immunology",
        indication="Ulcerative colitis", phase="Phase 2", code="XB-102", aliases=["XB-102", "XB102"],
        company="Corvane Bio", n_trials=2, us_rights="Not reported")
    add("shared_code_unrelated", "EXCLUDED",
        "Unrelated oncology small molecule using the same code XB-102. Must never be merged.",
        target="KRAS", mechanism="KRAS G12C inhibitor", technology="Small molecule", area="Oncology",
        indication="Non-small cell lung cancer", phase="Phase 1", code="XB-102", aliases=["XB-102"],
        company="Halden Therapeutics", suffix="rasib")
    # Background landscape.
    ibd_other = [("IL23A", "IL-23 p19 inhibitor", "Monoclonal antibody"),
                 ("IL-23", "IL-23 p19 inhibitor", "Monoclonal antibody"),
                 ("ITGB7", "Anti-integrin beta7 antibody (blocking)", "Monoclonal antibody"),
                 ("JAK1", "Selective JAK1 inhibitor", "Small molecule"),
                 ("S1PR1", "S1P1 receptor modulator", "Small molecule"),
                 ("TNF", "TNF-alpha blocker", "Monoclonal antibody"),
                 ("IL1RL2", "IL-36 receptor antagonist", "Monoclonal antibody"),
                 ("RIPK1", "RIPK1 kinase inhibitor", "Small molecule"),
                 ("TYK2", "TYK2 inhibitor", "Small molecule"),
                 ("NLRP3", "NLRP3 inflammasome inhibitor", "Small molecule"),
                 ("GPR35", "GPR35 agonist", "Small molecule")]
    immunology = [("IL13", "Asthma"), ("IL17A", "Psoriasis"), ("TSLP", "Asthma"), ("IL4R", "Atopic dermatitis"),
                  ("IL6R", "Rheumatoid arthritis"), ("FCGRT", "Myasthenia gravis"),
                  ("CD40LG", "Systemic lupus erythematosus"), ("STAT6", "Atopic dermatitis"),
                  ("IFNAR1", "Systemic lupus erythematosus"), ("BTK", "Multiple sclerosis"),
                  ("PDE4B", "Psoriasis")]
    oncology = [("EGFR", "Non-small cell lung cancer"), ("ERBB2", "Breast cancer"),
                ("TROP2", "Triple-negative breast cancer"), ("DLL3", "Small cell lung cancer"),
                ("CLDN18", "Gastric cancer"), ("KRAS", "Colorectal cancer"), ("CD19", "B-cell lymphoma"),
                ("PDCD1", "Melanoma")]
    special_rows = len(out) + sum(len(p.extra_rows) for p in out)
    background = TOTAL_ROWS - special_rows - 3 - 2  # 3 exact duplicates, 2 malformed rows
    for i in range(background):
        bucket = i % 10
        if bucket < 4:
            target, mechanism, technology = rng.choice(ibd_other)
            unreadable = target == "IL-23"
            add("other_target_ibd", "EXCLUDED",
                "IBD program against a different target." + (
                    " Target text 'IL-23' is not an approved symbol, so the engine is expected "
                    "to leave it UNRESOLVED (a conservative miss)." if unreadable else ""),
                target=target, mechanism=mechanism, technology=technology,
                area=rng.choice(["Immunology", "Gastroenterology"]), indication=rng.choice(_IBD),
                phase=rng.choice(["Preclinical", "Phase 1", "Phase 2", "Phase 3"]),
                suffix="mab" if "antibody" in technology.casefold() else "tinib")
        elif bucket < 7:
            target, indication = rng.choice(immunology)
            add("other_immunology", "EXCLUDED", "Different target and indication.",
                target=target, mechanism=f"{target} antagonist", technology=rng.choice(
                    ["Monoclonal antibody", "Small molecule", "Fusion protein"]),
                area=rng.choice(["Immunology", "Dermatology", "Respiratory"]), indication=indication,
                phase=rng.choice(["Phase 1", "Phase 2", "Phase 3"]))
        else:
            target, indication = rng.choice(oncology)
            add("oncology", "EXCLUDED", "Oncology program.",
                target=target, mechanism=f"{target} inhibitor", technology=rng.choice(
                    ["Monoclonal antibody", "Antibody-drug conjugate", "Small molecule", "Bispecific antibody"]),
                area="Oncology", indication=indication, phase=rng.choice(["Phase 1", "Phase 2", "Phase 3"]),
                suffix=rng.choice(["mab", "tinib", "vedotin"]))
    return out


def _row(p: Program) -> dict[str, str]:
    return {
        "Drug ID": p.external_id, "Source": "SYNTHETIC_VENDOR", "Drug Name": p.name,
        "Synonyms": "; ".join(p.aliases), "Target(s)": p.target, "Mechanism of Action": p.mechanism,
        "Technology": p.technology, "Therapy Area": p.area, "Indication(s)": p.indication,
        "Highest Phase": p.phase, "Development Status": p.status, "Status Date": "2026-09-30",
        "Originator": p.company, "Trial IDs": "; ".join(p.trials), "US Rights": p.us_rights,
        "Territory Rights": p.territory, "Deals / Partnerships": p.deals,
        "Source URL": f"https://example.org/synthetic-landscape/{p.external_id}",
        "Last Updated": "2026-09-30", "Data Notes": p.notes,
    }


def generate(out_dir: str | Path, *, seed: int = SEED) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    programs = _programs(rng)
    rows: list[dict[str, str]] = []
    for p in programs:
        rows.append(_row(p))
        for extra in p.extra_rows:
            rows.append({**_row(p), **extra})
    rng.shuffle(rows)
    for source in rng.sample(rows[:150], 3):  # exact duplicate rows, as exports often contain
        rows.insert(rng.randint(0, len(rows)), dict(source))
    malformed = dict(rows[7])
    malformed.update({"Drug ID": "", "Drug Name": "Unidentified program", "Data Notes": "ID missing"})
    rows.append(malformed)
    bad_date = dict(rows[11])
    bad_date.update({"Drug ID": "SYN-9999", "Drug Name": "Baddate-mab", "Last Updated": "31/02/2025"})
    rows.append(bad_date)
    assert len(rows) == TOTAL_ROWS, len(rows)

    landscape = out / "landscape_200.csv"
    with landscape.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Landscape export"
        ws.append(HEADERS)
        for r in rows:
            ws.append([r[h] for h in HEADERS])
        wb.save(out / "landscape_200.xlsx")
    except ImportError:  # pragma: no cover
        pass

    _evidence_library(out, programs)  # before the truth: it marks which gaps research can close
    truth = {
        "label": "SYNTHETIC GROUND TRUTH: evaluation only; never an application input",
        "seed": seed,
        "rows": {"total": len(rows), "exact_duplicates": 3, "malformed": 2},
        "programs": {
            p.external_id: {
                "name": p.name, "archetype": p.archetype, "expected_disposition": p.truth_disposition,
                "note": p.truth_note, "resolvable_by_research": p.resolvable_by_research,
                "expected_after_confirmed_research": (
                    "ELIGIBLE" if p.resolvable_by_research else p.truth_disposition),
                "company": p.company, "codes": p.aliases,
            }
            for p in programs
        },
        "must_not_merge": [[p.external_id for p in programs if "XB-102" in p.aliases]],
    }
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n")
    _fixtures(out, programs)
    return {"rows": len(rows), "programs": len(programs), "dir": str(out)}


def _evidence_library(out: Path, programs: list[Program]) -> None:
    docs = []
    for p in programs:
        if p.archetype == "missing_target_researchable":
            docs.append({
                "url": f"https://example.org/synthetic-press/{p.external_id}",
                "title": f"{p.company} reports progress with {p.name} (synthetic press release)",
                "date": "2026-06-15",
                "text": (f"{p.company} today announced dosing in a Phase 2 study of {p.name}. "
                         f"{p.name} is a monoclonal antibody targeting TL1A for moderate-to-severe "
                         "ulcerative colitis. The company did not comment on partnering."),
            })
    conflicted = [p for p in programs if p.archetype == "conflicting_phase"]
    for p in conflicted[:1]:
        p.resolvable_by_research = True
        docs.append({
            "url": f"https://example.org/synthetic-registry-note/{p.external_id}",
            "title": f"Registry update for {p.name} (synthetic)",
            "date": "2026-08-01",
            "text": f"The sponsor lists {p.name} in an ongoing Phase 2 induction study in Crohn's disease.",
        })
    available = [p for p in programs if p.us_rights.startswith("U.S. rights available")]
    for p in available[:1]:
        docs.append({
            "url": f"https://example.org/synthetic-news/{p.external_id}",
            "title": f"{p.company} signs regional deal for {p.name} (synthetic)",
            "date": "2026-09-20",
            "text": (f"{p.company} granted Large Pharma B (synthetic) exclusive licensed U.S. rights "
                     f"to {p.name} in September 2026."),
        })
    (out / "evidence_library.json").write_text(json.dumps(
        {"label": "SYNTHETIC public-style documents for the offline diligence agent", "documents": docs},
        indent=2) + "\n")


def _fixtures(out: Path, programs: list[Program]) -> None:
    """Decisions of a labelled synthetic reviewer, plus hypothetical valuation inputs."""
    by_arch: dict[str, list[Program]] = {}
    for p in programs:
        by_arch.setdefault(p.archetype, []).append(p)
    in_scope = sorted(by_arch["in_scope_tl1a_mab"], key=lambda p: (-_order(p.phase), p.external_id))
    researchable = by_arch["missing_target_researchable"]
    reviewer = "synthetic-reviewer-01"
    rows: list[dict[str, str]] = []

    def dec(phase: str, action: str, ext: str, new_state: str, rationale: str, field: str = "",
            question: str = "") -> None:
        rows.append({"phase": phase, "action": action, "external_id": ext, "field": field,
                     "new_state": new_state, "rationale": rationale, "reviewer_id": reviewer,
                     "question": question})

    for p in researchable:
        dec("1", "CONFIRM_FINDING", p.external_id, "CONFIRMED",
            "Press release names TL1A as the target; consistent with mechanism text.", field="target")
    conflicted = by_arch["conflicting_phase"][0]
    dec("1", "CONFIRM_FINDING", conflicted.external_id, "CONFIRMED",
        "Most recent sponsor registry note lists an ongoing Phase 2 study.", field="phase")
    rights_doc = next((p for p in programs if p.us_rights.startswith("U.S. rights available")), None)
    if rights_doc is not None:
        dec("1", "CONFIRM_FINDING", rights_doc.external_id, "CONFIRMED",
            "Later news reports an exclusive U.S. license; vendor 'available' is out of date.",
            field="us_rights")
    dec("1", "RESOLVE_IDENTITY_FLAG", "XB-102", "KEEP_SEPARATE",
        "Different originators, targets and indications: two molecules sharing a code.")
    for p in by_arch["undisclosed_target"][:1]:
        dec("1", "REQUEST_DILIGENCE", p.external_id, "REQUESTED", "Target undisclosed in all sources.",
            question="Ask the company to disclose the target under CDA.")

    picks = [p for p in in_scope if not p.us_rights.startswith("U.S. rights exclusively")][:6]
    picks += [by_arch["in_scope_bispecific"][0], by_arch["shared_code_in_scope"][0], researchable[0]]
    for p in picks:
        dec("2", "APPROVE_FINALIST", p.external_id, "APPROVED",
            f"{p.phase} anti-TL1A/DR3-axis antibody in {p.indication}; fits mAb capability; rights to "
            "be confirmed.")
    unresolved_pick = by_arch["unreadable_modality"][0]
    dec("2", "APPROVE_FINALIST", unresolved_pick.external_id, "APPROVED_WITH_OPEN_QUESTIONS",
        "Anti-TL1A program kept on the list while its modality is confirmed with the company.")
    dec("2", "APPROVE_FINALIST", by_arch["dr3_agonist_antibody"][0].external_id, "APPROVED",
        "(Deliberate invalid attempt: an excluded DR3 agonist; the log must refuse it.)")
    valued = picks[:3]
    for p in valued:
        dec("2", "SELECT_FOR_VALUATION", p.external_id, "SELECTED",
            "Preliminary valuation requested for the BD discussion.")
    with (out / "reviewer_fixture.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def block(p: Program, *, patients: int, price: int, share: float, stage: str,
              trials: list[dict[str, Any]], deal_scale: float) -> dict[str, Any]:
        return {
            "note": f"HYPOTHETICAL inputs for synthetic {p.name}",
            "therapeutic_area": "immunology", "stage": stage, "modality": "biologic",
            "discount_rate": 0.10,
            "ownership": {"royalty_rate": 0.0},
            "market": {"addressable_patients_annual": patients, "net_price_per_patient_usd": price,
                       "peak_penetration": share, "years_to_peak": 6, "patent_life_years": 12,
                       "cogs_rate": 0.12, "sgna_rate_launch": 0.40, "sgna_rate_mature": 0.22},
            "trials": trials,
            "deal_options": {
                "acquisition": {"label": "Acquisition (hypothetical)", "upfront_cost_millions": round(900 * deal_scale),
                                "milestones": [{"description": "Approval milestone", "amount_millions": round(300 * deal_scale),
                                                "trigger": "approval", "direction": "payable"}]},
                "license": {"label": "U.S. license (hypothetical)", "upfront_cost_millions": round(150 * deal_scale),
                            "royalty_rate": 0.12,
                            "milestones": [{"description": "Phase 3 success", "amount_millions": round(100 * deal_scale),
                                            "trigger": "phase_success", "trigger_phase": "phase_3",
                                            "direction": "payable"},
                                           {"description": "Approval", "amount_millions": round(200 * deal_scale),
                                            "trigger": "approval", "direction": "payable"}]},
            },
        }

    def path(stage: str) -> list[dict[str, Any]]:
        steps = {"phase_1": [("phase_1", 0.55, 1.5, 25)], "phase_2": [], "phase_3": []}
        seq = [("phase_2", 0.40, 2.0, 70), ("phase_3", 0.60, 3.0, 260), ("nda_bla", 0.90, 1.0, 25)]
        start = {"phase_1": 0, "phase_2": 0, "phase_3": 1}[stage]
        chosen = steps.get(stage, []) + seq[start:]
        return [{"phase": ph, "success_probability": p_, "duration_years": d, "cost_millions": c}
                for ph, p_, d, c in chosen]

    stage_of = {"Phase 1": "phase_1", "Phase 1/2": "phase_1", "Phase 2": "phase_2", "Phase 2/3": "phase_2",
                "Phase 3": "phase_3"}
    assets: dict[str, Any] = {}
    sizes = [(140_000, 60_000, 0.07, 1.0), (120_000, 55_000, 0.05, 0.6), (4_000, 90_000, 0.15, 1.0)]
    for p, (patients, price, share, scale) in zip(valued, sizes, strict=True):
        stage = stage_of[p.phase]
        assets[p.external_id] = block(p, patients=patients, price=price, share=share, stage=stage,
                                      trials=path(stage), deal_scale=scale)
    incomplete = picks[3]
    assets[incomplete.external_id] = {
        "note": "Deliberately incomplete: price and development costs not yet owned by anyone.",
        "therapeutic_area": "immunology", "stage": stage_of[incomplete.phase], "modality": "biologic",
        "discount_rate": 0.10, "ownership": {"royalty_rate": 0.0},
        "market": {"addressable_patients_annual": 100_000, "peak_penetration": 0.05, "years_to_peak": 6},
        "trials": [{"phase": "phase_2", "success_probability": 0.40, "duration_years": 2.0}],
    }
    doc = {
        "label": "HYPOTHETICAL_ANALYST_ASSUMPTIONS (synthetic demo; not sourced facts)",
        "owner": "synthetic-reviewer-01 (demo)",
        "units": {"market.net_price_per_patient_usd": "USD per patient-year", "cost_millions": "USD millions"},
        "assets": assets,
    }
    (out / "valuation_assumptions.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))


def _order(phase: str) -> int:
    return {"Phase 1": 1, "Phase 1/2": 2, "Phase 2": 3, "Phase 2/3": 4, "Phase 3": 5}.get(phase, 0)


if __name__ == "__main__":  # pragma: no cover
    import sys

    print(generate(sys.argv[1] if len(sys.argv) > 1 else "examples/dealscreen"))
