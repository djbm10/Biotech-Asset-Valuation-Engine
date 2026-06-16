"""Route detected lead assets to an action by confidence — conservatively.

Slice 2 of bve-discover. Given a candidate company, we detect + cluster + rank
its CT.gov programs (slice 1) and then decide what to *do* with the result:

    high confidence    -> propose a seed   (or auto-add, only behind an opt-in flag)
    medium confidence  -> review queue      (a human confirms before it is seeded)
    low / no lead      -> exception         (no action)

Two hard safety rules sit on top of the confidence tiers, both learned from the
50-seed backtest adjudication:

1. **Approved-vs-active-pivotal ambiguity is never auto-added.** If the company
   already has an approved/marketed program *other than* the pick (e.g. Merus:
   approved zenocutuzumab vs. active Phase 3 petosemtamab), "lead asset" is a
   judgment call — it is forced to review regardless of tier. This is the MRUS
   rule.
2. **Already-seeded tickers are never re-proposed or auto-added.** The registry
   is the source of truth; routing only ever *adds* names it does not yet know.

Nothing here mutates the curated registry. Proposals and auto-adds are written to
separate files under ``outputs/discovery/`` and every decision is recorded in an
audit artifact — including the ones that wrote nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from pydantic import BaseModel

from bve.discovery.lead_ranker import RankedLead, rank_leads
from bve.discovery.matching import infer_modality
from bve.discovery.program_cluster import CandidateProgram, cluster_programs
from bve.discovery.program_filters import is_device_or_dx_company
from bve.discovery.sponsor_trials import TrialRecord

# ── Dispositions (what the evidence says) ────────────────────────────────────────
DISPOSITION_HIGH = "high_confidence"
DISPOSITION_MEDIUM = "medium_confidence"
DISPOSITION_LOW = "low_confidence"
DISPOSITION_APPROVED_AMBIGUOUS = "approved_vs_active_pivotal"
DISPOSITION_NO_LEAD = "no_lead"
DISPOSITION_EXCLUDED = "excluded"
DISPOSITION_NOT_DEVELOPER = "device_or_diagnostic"
DISPOSITION_UNCONFIRMED_ORIGINATOR = "unconfirmed_originator"

# ── Actions (what we do about it) ────────────────────────────────────────────────
ACTION_AUTO_ADD = "auto_add"
ACTION_PROPOSE = "propose"
ACTION_REVIEW = "review"
ACTION_EXCEPTION = "exception"
ACTION_SKIP_EXISTS = "skip_exists"
ACTION_EXCLUDED = "excluded"

_APPROVED_STATUSES = {"APPROVED_FOR_MARKETING"}
_ACTIVE_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}


class CandidateCompany(BaseModel, frozen=True):
    """One company to route: a ticker + the sponsor name to query CT.gov by."""

    ticker: str
    company_name: str


class RouteDecision(BaseModel, frozen=True):
    """The full, auditable record of how one company was routed."""

    ticker: str
    company_name: str
    disposition: str
    action: str
    reason: str
    already_seeded: bool = False
    n_programs: int = 0
    # Pick details (None when there is no lead).
    drug: Optional[str] = None
    drug_key: Optional[str] = None
    stage: Optional[str] = None
    indication: Optional[str] = None
    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None
    nct_id: Optional[str] = None
    tier: Optional[str] = None
    score: float = 0.0
    margin: float = 0.0
    # Name of the conflicting approved program, when the MRUS rule fired.
    approved_alternative: Optional[str] = None

    def as_seed_entry(self) -> dict:
        """UniverseRegistryEntry-shaped dict for a proposed/auto-added seed."""
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "asset_id": f"asset-{self.ticker.lower()}-{(self.drug_key or 'lead')}",
            "drug_name": self.drug,
            "indication": self.indication or "unknown",
            "therapeutic_area": self.therapeutic_area or "unknown",
            "stage": self.stage,
            "modality": self.modality or "unknown",
            "nct_id": self.nct_id,
        }


# ── Pick-detail extraction ───────────────────────────────────────────────────────

# Ordered: first category whose keywords hit wins. Oncology first (it dominates and
# its terms are unambiguous); specific organ/area buckets before broad ones. TA
# labels match the assumptions-loader vocabulary (cns, cardiovascular, renal,
# gastroenterology, psychiatry, pulmonary, infectious_disease, rare_disease, …) so
# downstream economics resolve instead of falling back to "other".
_TA_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("cancer", "carcinoma", "tumor", "tumour", "lymphoma", "leukemia", "leukaemia",
      "myeloma", "melanoma", "sarcoma", "oncolog", "solid", "neoplas", "glioma",
      "glioblastoma", "metasta", "malignan"), "oncology"),
    (("retina", "macular", "ophthalmo", "uveitis", "glaucoma", "geographic atrophy",
      "vision", "ocular", "eye", "stargardt"), "ophthalmology"),
    (("kidney", "renal", "nephro", "nephropathy", "glomerulo", "glomerulosclerosis",
      "iga nephropathy", "fsgs", "focal segmental", "nephrotic"), "renal"),
    (("gerd", "reflux", "esophagitis", "h. pylori", "helicobacter", "gastric",
      "peptic ulcer", "gastrointestinal", "eosinophilic esophagitis"), "gastroenterology"),
    (("obesity", "weight", "diabet", "nash", "mash", "metabolic", "hyperlipid",
      "cholesterol", "dyslipid", "fatty liver", "hypertriglycerid"), "metabolic"),
    (("amyloidosis", "anemia", "anaemia", "thrombo", "hemophilia", "haemophilia",
      "sickle", "thalassemia", "thalassaemia", "polycythemia", "myelofibrosis",
      "bleeding", "hematolog"), "hematology"),
    (("lupus", "arthritis", "psoriasis", "colitis", "crohn", "dermatitis", "asthma",
      "vasculitis", "myositis", "scleroderma", "immune", "autoimmune", "atopic",
      "urticaria", "graft", "lupus nephritis", "sjogren", "myasthenia"), "immunology"),
    (("depression", "major depressive", "schizophrenia", "bipolar", "anxiety",
      "ptsd", "psychiatr"), "psychiatry"),
    (("epilepsy", "alzheimer", "parkinson", "migraine", "seizure", "neuro", "tremor",
      "huntington", "amyotrophic", "multiple sclerosis", "dystrophy", "myopathy",
      "ataxia", "spinal muscular", "facioscapulohumeral", "fshd"), "cns"),
    (("heart", "cardiac", "cardiovascular", "cardiomyopathy", "hypertension",
      "atrial", "coronary", "thrombosis"), "cardiovascular"),
    (("hepatitis", "hiv", "influenza", "covid", "sars", "rsv", "bacterial",
      "infection", "antiviral", "antibiotic", "vaccine"), "infectious_disease"),
    (("pulmonary", "fibrosis", "copd", "respiratory", "cystic fibrosis"), "pulmonary"),
    (("prader-willi", "prader willi"), "rare_disease"),
]


def _infer_ta(indication: Optional[str]) -> str:
    text = (indication or "").lower()
    for keywords, ta in _TA_KEYWORDS:
        if any(k in text for k in keywords):
            return ta
    return "unknown"


def _best_indication(program: CandidateProgram) -> Optional[str]:
    """Most informative indication: a real disease from the max-phase trial."""
    def _usable(cond: str) -> bool:
        return bool(cond) and "healthy" not in cond.lower()

    max_phase_trials = [t for t in program.trials if t.phase == program.max_phase]
    for trial in max_phase_trials:
        for cond in trial.conditions:
            if _usable(cond):
                return cond
    for cond in program.conditions:
        if _usable(cond):
            return cond
    return program.conditions[0] if program.conditions else None


def _representative_nct(program: CandidateProgram) -> Optional[str]:
    """Prefer the active trial at the max phase, then any max-phase trial."""
    max_phase_trials = [t for t in program.trials if t.phase == program.max_phase]
    for trial in max_phase_trials:
        if trial.status in _ACTIVE_STATUSES:
            return trial.nct_id
    if max_phase_trials:
        return max_phase_trials[0].nct_id
    return program.trials[0].nct_id if program.trials else None


def approved_alternative(programs: list[CandidateProgram], lead: RankedLead) -> Optional[str]:
    """The MRUS rule: name of an approved program that is *not* the pick.

    When a company already markets a drug but the ranker picks a different,
    still-active asset, the lead is genuinely ambiguous (approved value driver
    vs. active pivotal) and must go to a human. Returns None when the pick is
    itself the approved asset, or there is no approved alternative.
    """
    pick_key = lead.program.drug_key
    pick_approved = any(t.status in _APPROVED_STATUSES for t in lead.program.trials)
    if pick_approved:
        return None
    for prog in programs:
        if prog.drug_key == pick_key:
            continue
        if any(t.status in _APPROVED_STATUSES for t in prog.trials):
            return prog.drug
    return None


# ── Routing ──────────────────────────────────────────────────────────────────────

def route_company(
    candidate: CandidateCompany,
    programs: list[CandidateProgram],
    lead: Optional[RankedLead],
    *,
    existing_tickers: Optional[set[str]] = None,
    auto_add_high: bool = False,
) -> RouteDecision:
    """Pure routing decision for one company (no I/O, no network)."""
    existing = {t.upper() for t in (existing_tickers or set())}
    seeded = candidate.ticker.upper() in existing
    base = dict(
        ticker=candidate.ticker,
        company_name=candidate.company_name,
        already_seeded=seeded,
        n_programs=len(programs),
    )

    # Device / diagnostics / imaging firms are not therapeutic developers, even if
    # they pass the liquidity screen and run a drug-arm trial.
    if is_device_or_dx_company(candidate.company_name):
        return RouteDecision(
            **base, disposition=DISPOSITION_NOT_DEVELOPER, action=ACTION_EXCEPTION,
            reason="company appears to be a device/diagnostics firm, not a drug developer",
        )

    if lead is None:
        return RouteDecision(
            **base, disposition=DISPOSITION_NO_LEAD, action=ACTION_EXCEPTION,
            reason="no clusterable programs found",
        )

    prog = lead.program
    indication = _best_indication(prog)
    pick = dict(
        drug=prog.drug,
        drug_key=prog.drug_key,
        stage=prog.max_phase,
        indication=indication,
        therapeutic_area=_infer_ta(indication),
        modality=infer_modality(prog.drug, list(prog.conditions),
                                intervention_type=prog.intervention_type,
                                aliases=list(prog.aliases),
                                descriptions=list(prog.descriptions),
                                drug_key=prog.drug_key),
        nct_id=_representative_nct(prog),
        tier=lead.tier,
        score=lead.score,
        margin=lead.margin,
    )

    # Rule 1 (MRUS): approved alternative overrides tier → always review.
    conflict = approved_alternative(programs, lead)
    if conflict is not None:
        return RouteDecision(
            **base, **pick, approved_alternative=conflict,
            disposition=DISPOSITION_APPROVED_AMBIGUOUS, action=ACTION_REVIEW,
            reason=(
                f"approved alternative ({conflict}) competes with active pick "
                f"({prog.drug}) — lead is a judgment call, never auto-added"
            ),
        )

    # Rule 2 (originator): a collaborator-only lead (company is not the trial's
    # lead sponsor) is likely a partner / someone-else's molecule. Never propose
    # it unconfirmed — route to review for originator confirmation. Calibrated:
    # genuine leads sponsor their own pivotal trials (sponsor_is_lead=True).
    if not prog.sponsor_is_lead:
        return RouteDecision(
            **base, **pick,
            disposition=DISPOSITION_UNCONFIRMED_ORIGINATOR, action=ACTION_REVIEW,
            reason=(
                f"company is not the lead sponsor of {prog.drug} — possible partner/"
                "comparator asset; confirm the company originates it before seeding"
            ),
        )

    if lead.tier == "high":
        disposition, want = DISPOSITION_HIGH, (ACTION_AUTO_ADD if auto_add_high else ACTION_PROPOSE)
        reason = "high-confidence lead"
    elif lead.tier == "medium":
        disposition, want = DISPOSITION_MEDIUM, ACTION_REVIEW
        reason = "medium-confidence lead — confirm before seeding"
    else:
        disposition, want = DISPOSITION_LOW, ACTION_EXCEPTION
        reason = "low-confidence lead — no action"

    # Rule 2: never re-touch an already-seeded ticker.
    if seeded and want in (ACTION_AUTO_ADD, ACTION_PROPOSE):
        return RouteDecision(
            **base, **pick, disposition=disposition, action=ACTION_SKIP_EXISTS,
            reason=f"{reason}; already in registry — skipped",
        )

    return RouteDecision(**base, **pick, disposition=disposition, action=want, reason=reason)


class RoutingResult(BaseModel):
    """All routing decisions plus the artifacts they imply."""

    generated_at: str
    auto_add_enabled: bool
    decisions: list[RouteDecision]

    @property
    def action_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.decisions:
            counts[d.action] = counts.get(d.action, 0) + 1
        return counts

    @property
    def proposals(self) -> list[RouteDecision]:
        return [d for d in self.decisions if d.action == ACTION_PROPOSE]

    @property
    def auto_added(self) -> list[RouteDecision]:
        return [d for d in self.decisions if d.action == ACTION_AUTO_ADD]

    @property
    def reviews(self) -> list[RouteDecision]:
        return [d for d in self.decisions if d.action == ACTION_REVIEW]

    def _entry(self, d: RouteDecision) -> dict:
        entry = d.as_seed_entry()
        meta = {
            "source": "bve-discover",
            "disposition": d.disposition,
            "tier": d.tier,
            "score": round(d.score, 4),
            "margin": round(d.margin, 4),
            "generated_at": self.generated_at,
        }
        if d.approved_alternative:
            meta["approved_alternative"] = d.approved_alternative
        entry["_meta"] = meta
        return entry

    def proposals_doc(self) -> dict:
        """Serializable document of everything needing human attention.

        Three sections — ``proposals`` (high-confidence), ``review`` (medium /
        approved-vs-active-pivotal), and ``auto_added`` (only when the flag is on)
        — so a single file is the source the profile review queue reads from.
        Exceptions and already-seeded skips are intentionally omitted (no action).
        """
        return {
            "generated_at": self.generated_at,
            "proposals": [self._entry(d) for d in self.proposals],
            "review": [self._entry(d) for d in self.reviews],
            "auto_added": [{**self._entry(d), "_meta": {**self._entry(d)["_meta"], "auto_added": True}}
                           for d in self.auto_added],
        }

    def to_dict(self) -> dict:
        return self.model_dump()

    def to_audit_text(self) -> str:
        lines = [
            "=" * 70,
            "bve-discover — routing audit",
            "=" * 70,
            f"generated_at   : {self.generated_at}",
            f"auto-add high  : {'ENABLED' if self.auto_add_enabled else 'disabled (default)'}",
            f"candidates     : {len(self.decisions)}",
            "",
            "Action counts",
        ]
        for action in (ACTION_AUTO_ADD, ACTION_PROPOSE, ACTION_REVIEW,
                       ACTION_EXCEPTION, ACTION_SKIP_EXISTS, ACTION_EXCLUDED):
            lines.append(f"  {action:12s}: {self.action_counts.get(action, 0)}")
        lines += ["", "Decisions (every candidate, with the reason)"]
        order = {ACTION_AUTO_ADD: 0, ACTION_PROPOSE: 1, ACTION_REVIEW: 2,
                 ACTION_EXCEPTION: 3, ACTION_SKIP_EXISTS: 4, ACTION_EXCLUDED: 5}
        for d in sorted(self.decisions, key=lambda x: (order.get(x.action, 9), x.ticker)):
            pick = f"{d.drug} [{d.stage}]" if d.drug else "(no lead)"
            seeded = " seeded" if d.already_seeded else ""
            lines.append(f"  {d.ticker:6s} {d.action:12s} {pick:32s} {d.disposition}{seeded}")
            lines.append(f"         └ {d.reason}")
        return "\n".join(lines)


def run_routing(
    candidates: list[CandidateCompany],
    *,
    fetch_fn: Callable[[str], list[TrialRecord]],
    existing_tickers: Optional[set[str]] = None,
    excluded_tickers: Optional[set[str]] = None,
    auto_add_high: bool = False,
    now: Optional[datetime] = None,
) -> RoutingResult:
    """Detect, rank, and route every candidate company (pure over ``fetch_fn``).

    Excluded tickers (rejected / acquired / bad-data, from the exclusion ledger)
    are short-circuited with no CT.gov fetch — a rejected name must not keep
    coming back, and must not cost a network call to re-reject.
    """
    generated = (now or datetime.now(timezone.utc)).isoformat()
    excluded = {t.upper() for t in (excluded_tickers or set())}
    decisions: list[RouteDecision] = []
    for cand in candidates:
        if cand.ticker.upper() in excluded:
            decisions.append(RouteDecision(
                ticker=cand.ticker, company_name=cand.company_name,
                disposition=DISPOSITION_EXCLUDED, action=ACTION_EXCLUDED,
                reason="on exclusion ledger — not re-proposed",
            ))
            continue
        programs = cluster_programs(fetch_fn(cand.company_name))
        lead = rank_leads(programs)
        decisions.append(route_company(
            cand, programs, lead,
            existing_tickers=existing_tickers, auto_add_high=auto_add_high,
        ))
    return RoutingResult(
        generated_at=generated, auto_add_enabled=auto_add_high, decisions=decisions,
    )
