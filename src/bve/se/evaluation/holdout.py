"""Case-level holdout scoring boundary.

The holdout data contains only unlabeled case evidence. Labels are deliberately not accepted by
this module or the CLI; scoring is performed by the independent custodian after predictions are
sealed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Disposition = Literal["INCLUDE", "EXCLUDE", "UNKNOWN"]
GateStatus = Literal["PASS", "FAIL", "UNKNOWN"]


class HoldoutProblem(BaseModel):
    """Strict problem contract for case-level acquisition-triage holdouts.

    This is intentionally separate from ``BuyerProblemV2``. A holdout problem describes the
    classification rubric applied to standalone evidence excerpts; it is not a buyer strategy or
    discovery query.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["se_holdout_problem_v1"] = "se_holdout_problem_v1"
    problem_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version: str | int
    task: str = Field(min_length=1)
    allowed_dispositions: list[Disposition]
    labeling_rubric: dict[Disposition, str]
    decision_rules: list[str] = Field(min_length=1)
    source_text_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dispositions(self) -> "HoldoutProblem":
        expected = {"INCLUDE", "EXCLUDE", "UNKNOWN"}
        if len(self.allowed_dispositions) != len(set(self.allowed_dispositions)):
            raise ValueError("allowed_dispositions contains duplicates")
        if set(self.allowed_dispositions) != expected:
            raise ValueError(
                "allowed_dispositions must contain exactly INCLUDE, EXCLUDE, and UNKNOWN"
            )
        if set(self.labeling_rubric) != expected:
            raise ValueError("labeling_rubric must define INCLUDE, EXCLUDE, and UNKNOWN")
        return self


class HoldoutCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    source_text: str = ""
    required_buyer_capability: str | None = None
    buyer_capabilities: list[str] | None = None


class HoldoutGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: str = Field(min_length=1)
    status: GateStatus
    evidence: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


class HoldoutPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    disposition: Disposition
    gates: list[HoldoutGateDecision] = Field(min_length=1)
    reason: str = Field(min_length=1)


def load_holdout_cases(path: Path) -> list[HoldoutCase]:
    """Load unlabeled JSONL cases without ever accepting a label field."""

    cases: list[HoldoutCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = HoldoutCase.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"invalid holdout case on line {line_number}: {exc}") from exc
        if case.case_id in seen:
            raise ValueError(f"duplicate holdout case_id: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    return cases


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _matched(text: str, patterns: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matches.append(match.group(0))
    return list(dict.fromkeys(matches))


def _decision(gate: str, status: GateStatus, evidence: list[str], reason: str) -> HoldoutGateDecision:
    return HoldoutGateDecision(gate=gate, status=status, evidence=evidence, reason=reason)


def _target_gate(case: HoldoutCase) -> HoldoutGateDecision:
    text = case.source_text
    normalized_text = _normalized(text)
    normalized_targets = [
        _normalized(part)
        for part in re.split(r"\s+(?:and|or)\s+|[+/,&]", case.target, flags=re.IGNORECASE)
        if _normalized(part)
    ]
    ambiguity = _matched(
        text,
        (
            r"does not establish that .* engages",
            r"never identifies the second binding arm",
            r"product and target(?: identity)? (?:are )?redacted",
            r"target(?: identity| linkage)? (?:is|are) (?:redacted|uncertain|unclear)",
            r"cannot establish (?:the )?target",
        ),
    )
    if ambiguity:
        return _decision(
            "target_match",
            "UNKNOWN",
            ambiguity,
            "The source does not resolve construct-level linkage to the required target.",
        )
    mismatch = _matched(
        text,
        (
            r"wrong target",
            r"different target",
            r"does not bind the stated target",
            r"confirmed not to (?:bind|engage|target)",
            rf"rather than {re.escape(case.target)}",
        ),
    )
    if mismatch:
        return _decision(
            "target_match",
            "FAIL",
            mismatch,
            "The source affirmatively identifies a target mismatch.",
        )
    if normalized_targets and all(target in normalized_text for target in normalized_targets):
        return _decision(
            "target_match",
            "PASS",
            [case.target],
            "The required target is explicitly linked to the evidence item.",
        )
    return _decision(
        "target_match",
        "UNKNOWN",
        ["No explicit occurrence of the required target was found."],
        "Target linkage is missing rather than affirmatively mismatched.",
    )


_MODALITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("antibody drug conjugate", ("antibody drug conjugate", "adc", "conjugate")),
    ("bispecific t cell engager", ("bispecific", "t cell engager", "immune engager")),
    ("small molecule inhibitor", ("small molecule", "inhibitor")),
    ("allogeneic car nk", ("allogeneic car nk", "car nk")),
    ("monoclonal antibody", ("monoclonal antibody", "antibody")),
    ("antisense oligonucleotide", ("antisense", "aso")),
    ("radioligand therapy", ("radioligand",)),
    ("inhaled biologic", ("inhaled",)),
    ("in vivo base editing", ("base editing",)),
    ("protein degrader", ("protein degrader", "degrader")),
    ("small molecule agonist", ("small molecule", "agonist")),
    ("depleting antibody", ("depleting antibody", "depletion approach")),
    ("engineered tcr t", ("engineered tcr", "tcr t")),
    ("allosteric inhibitor", ("allosteric inhibitor", "allosteric")),
    ("fusion protein", ("fusion protein", "fusion program")),
    ("cancer vaccine", ("cancer vaccine", "vaccine")),
    ("ligand trap", ("ligand trap",)),
    ("car t", ("car t",)),
    ("sirna", ("sirna",)),
)


def _modality_aliases(modality: str) -> tuple[str, ...]:
    normalized = _normalized(modality)
    aliases = {normalized}
    for canonical, values in _MODALITY_ALIASES:
        if canonical == normalized:
            aliases.update(values)
    return tuple(sorted(aliases, key=len, reverse=True))


def _modality_gate(case: HoldoutCase) -> HoldoutGateDecision:
    text = case.source_text
    normalized_text = _normalized(text)
    ambiguity = _matched(
        text,
        (
            r"does not say whether any participant received",
            r"never identifies the second binding arm",
            r"cannot establish which modality",
            r"cannot resolve .* modality",
            r"resolve modality fit",
            r"modality (?:is|remains) (?:unclear|uncertain)",
            r"described elsewhere as .* while this passage calls it",
            r"linked citation describes a different",
        ),
    )
    if ambiguity:
        return _decision(
            "modality_match",
            "UNKNOWN",
            ambiguity,
            "The source leaves the administered or evidenced modality unresolved.",
        )
    mismatch = _matched(
        text,
        (
            r"wrong modality",
            r"different modality",
            r"did not receive (?:an? |the )?[^.;]*",
            r"provides no evidence involving (?:an? |the )?[^.;]*",
            r"does not involve the stated modality",
            rf"rather than {re.escape(case.modality)}",
        ),
    )
    if mismatch:
        return _decision(
            "modality_match",
            "FAIL",
            mismatch,
            "The source affirmatively concerns a different intervention modality.",
        )
    aliases = _modality_aliases(case.modality)
    matched_aliases = [alias for alias in aliases if alias and alias in normalized_text]
    if matched_aliases:
        return _decision(
            "modality_match",
            "PASS",
            matched_aliases,
            "The source explicitly supports the required intervention modality.",
        )
    return _decision(
        "modality_match",
        "UNKNOWN",
        ["No explicit evidence for the required modality was found."],
        "Modality support is missing rather than affirmatively mismatched.",
    )


def _buyer_capability_gate(case: HoldoutCase) -> HoldoutGateDecision | None:
    required = case.required_buyer_capability
    if required is None:
        return None
    capabilities = case.buyer_capabilities
    if capabilities is None:
        return _decision(
            "buyer_capability",
            "UNKNOWN",
            [f"No capability inventory was supplied for {required!r}."],
            "A required buyer capability has no supporting or contradictory evidence.",
        )
    normalized_required = _normalized(required)
    matched = [value for value in capabilities if _normalized(value) == normalized_required]
    if matched:
        return _decision(
            "buyer_capability",
            "PASS",
            matched,
            "The supplied buyer capability inventory supports the requirement.",
        )
    return _decision(
        "buyer_capability",
        "FAIL",
        capabilities or ["Buyer capability inventory is explicitly empty."],
        f"The buyer capability inventory does not contain required capability {required!r}.",
    )


_NONQUALIFYING_EVIDENCE = (
    r"mouse xenograft",
    r"cultured [^.]*cells",
    r"in vitro",
    r"molecular.docking",
    r"simulation energies",
    r"research batch",
    r"cynomolgus monkeys",
    r"monkeys",
    r"narrative review",
    r"patent application",
    r"cell lines",
    r"corporate slogan",
    r"unsigned market blog",
    r"no human (?:exposure|outcomes|results|or regulator-origin evidence)",
    r"no participant was treated",
    r"no compound was administered to a person",
)

_HUMAN_OR_REGULATORY_EVIDENCE = (
    r"first.in.human",
    r"phase [123]",
    r"patients?",
    r"participants?",
    r"adults",
    r"randomized",
    r"clinical (?:study|trial|abstract|data)",
    r"regulator(?:'s)? (?:assessment|review|safety communication)",
    r"agency review",
    r"registry entry",
)


def _evidence_provenance_gate(case: HoldoutCase) -> HoldoutGateDecision:
    text = case.source_text
    nonqualifying = _matched(text, _NONQUALIFYING_EVIDENCE)
    if nonqualifying:
        return _decision(
            "evidence_provenance",
            "FAIL",
            nonqualifying,
            "The available evidence is affirmatively non-human, technical-only, promotional, or unverified.",
        )
    ambiguity = _matched(
        text,
        (
            r"does not distinguish patients from xenograft animals",
            r"linked citation describes a different",
            r"does not say whether any participant received",
        ),
    )
    if ambiguity:
        return _decision(
            "evidence_provenance",
            "UNKNOWN",
            ambiguity,
            "The source does not establish that the evidence comes from the relevant human intervention.",
        )
    qualifying = _matched(text, _HUMAN_OR_REGULATORY_EVIDENCE)
    if qualifying:
        return _decision(
            "evidence_provenance",
            "PASS",
            qualifying,
            "Human clinical, observational, registry, or regulator-origin evidence is explicit.",
        )
    return _decision(
        "evidence_provenance",
        "UNKNOWN",
        ["No explicit human, registry, or regulator-origin provenance was found."],
        "Evidence provenance is insufficiently supported.",
    )


_INSUFFICIENT_OR_CONFLICTING = (
    r"omits? (?:the )?(?:number|population|dose|methods?|outcomes?|conclusions?)",
    r"does not identify (?:the )?(?:cancer type|evaluable population|assessment method)",
    r"primary endpoint was met, while .* was not met",
    r"does not resolve which statement",
    r"insufficient to reconcile",
    r"methods, population, outcomes, and conclusions are not present",
    r"does not distinguish patients from xenograft animals",
    r"cannot establish which modality generated the result",
    r"intervention field is redacted",
    r"product and target(?: identity)? (?:are )?redacted",
)

_RESULT_EVIDENCE = (
    r"responses?",
    r"clinical endpoint",
    r"primary endpoint",
    r"outcomes?",
    r"adverse.event",
    r"toxicity",
    r"safety",
    r"suppression",
    r"change",
    r"reductions?",
    r"assessments?",
    r"dosimetry",
    r"exacerbations?",
    r"bleeding",
    r"tumor shrinkage",
)

_SPECIFICITY_EVIDENCE = (
    r"\b\d+\b",
    r"denominator",
    r"dose",
    r"data cutoff",
    r"confidence interval",
    r"analysis population",
    r"evaluable patients",
    r"participant counts",
    r"follow.up",
    r"randomized",
)


def _evidence_threshold_gate(case: HoldoutCase) -> HoldoutGateDecision:
    text = case.source_text
    nonqualifying = _matched(text, _NONQUALIFYING_EVIDENCE)
    if nonqualifying:
        return _decision(
            "evidence_threshold",
            "FAIL",
            nonqualifying,
            "The item affirmatively lacks decision-relevant human or regulatory results.",
        )
    ambiguity = _matched(text, _INSUFFICIENT_OR_CONFLICTING)
    if ambiguity:
        return _decision(
            "evidence_threshold",
            "UNKNOWN",
            ambiguity,
            "Critical population, endpoint, result, or source context is unresolved.",
        )
    results = _matched(text, _RESULT_EVIDENCE)
    specificity = _matched(text, _SPECIFICITY_EVIDENCE)
    if results and specificity:
        return _decision(
            "evidence_threshold",
            "PASS",
            [*results, *specificity],
            "The item reports a decision-relevant result with concrete clinical specificity.",
        )
    return _decision(
        "evidence_threshold",
        "UNKNOWN",
        [*(results or ["No explicit decision result found."]), *(specificity or ["No concrete population, dose, denominator, or timing detail found."])],
        "Positive evidence does not clear the minimum specificity threshold.",
    )


def predict_case(case: HoldoutCase) -> HoldoutPrediction:
    """Apply fail-closed three-state gates to one evidence item.

    Confirmed mismatch excludes, unresolved required evidence abstains, and inclusion requires
    positive support from every applicable gate.
    """

    gates = [_target_gate(case), _modality_gate(case)]
    capability_gate = _buyer_capability_gate(case)
    if capability_gate is not None:
        gates.append(capability_gate)
    gates.extend([_evidence_provenance_gate(case), _evidence_threshold_gate(case)])

    failed = next((gate for gate in gates if gate.status == "FAIL"), None)
    unresolved = next((gate for gate in gates if gate.status == "UNKNOWN"), None)
    if failed:
        disposition: Disposition = "EXCLUDE"
        reason = f"Confirmed mismatch at {failed.gate}: {failed.reason}"
    elif unresolved:
        disposition = "UNKNOWN"
        reason = f"Required gate unresolved at {unresolved.gate}: {unresolved.reason}"
    else:
        disposition = "INCLUDE"
        reason = "Every required gate is positively supported."
    return HoldoutPrediction(
        case_id=case.case_id,
        disposition=disposition,
        gates=gates,
        reason=reason,
    )


def predict_holdout(path: Path) -> list[HoldoutPrediction]:
    """Produce exactly one prediction for every input case in canonical case-id order."""

    cases = load_holdout_cases(path)
    return [predict_case(case) for case in sorted(cases, key=lambda case: case.case_id)]


def validate_predictions(
    expected_case_ids: Iterable[str],
    predictions: Iterable[HoldoutPrediction | Mapping[str, object]],
) -> list[HoldoutPrediction]:
    """Validate cardinality, identity, and disposition before serialization."""

    expected = list(expected_case_ids)
    if len(expected) != len(set(expected)):
        raise ValueError("expected case IDs contain duplicates")
    normalized = [HoldoutPrediction.model_validate(prediction) for prediction in predictions]
    observed = [prediction.case_id for prediction in normalized]
    if len(observed) != len(set(observed)):
        raise ValueError("predictions contain duplicate case IDs")
    missing = set(expected) - set(observed)
    extra = set(observed) - set(expected)
    if missing or extra:
        raise ValueError(f"prediction case mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    return sorted(normalized, key=lambda prediction: prediction.case_id)


def predictions_json(predictions: list[HoldoutPrediction]) -> list[dict[str, object]]:
    return [prediction.model_dump(mode="json") for prediction in predictions]
