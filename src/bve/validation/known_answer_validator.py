"""Known-answer validation logic for BVE directional institutional validation.

Compares BVE model outputs (when provided) against the expected ranges and
classifications defined in ``KnownAnswerCase`` objects. All checks degrade
gracefully to ``"not_available"`` when model outputs are absent.

Validation checks (up to 5 per case)
-------------------------------------
1. ``value_in_range``         — model rNPV ∈ [low, high]; N/A if not provided
2. ``deal_directional``       — observed deal value ∈ [0.40×low, 3.0×high];
                                always evaluable; validates range quality
3. ``deal_type_correct``      — model deal type matches expected; N/A if absent
4. ``buyer_identified``       — expected buyer found in model top buyers; N/A
5. ``thesis_direction_match`` — model thesis direction matches; N/A if absent

Overall pass per case
---------------------
A case "passes" when ≥ 50% of checks with data available return ``"pass"``.
When no model outputs are provided, only check 2 is evaluable and the case
status is ``"definitions_only"`` (not pass/fail).

Suite-level result
------------------
``KnownAnswerSuiteResult.overall_pass`` is True when every case with model
outputs passes. Cases without model outputs do not count against the suite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from bve.validation.known_answer_cases import KnownAnswerCase


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------

_PASS = "pass"
_FAIL = "fail"
_NA = "not_available"

# Generous multiplier: observed deal price (with premium) vs. model range
_DEAL_DIRECTIONAL_LOW_FACTOR: float = 0.40   # deal value >= 40% of range low
_DEAL_DIRECTIONAL_HIGH_FACTOR: float = 3.00  # deal value <= 3× range high


@dataclass
class CheckResult:
    """Result of one validation check.

    Parameters
    ----------
    check_name:
        Short identifier (e.g. ``"value_in_range"``).
    status:
        ``"pass"`` | ``"fail"`` | ``"not_available"``
    expected:
        The expected value or range (used in report rendering).
    actual:
        The actual value observed or None.
    notes:
        Optional explanation (shown when status is fail or not_available).
    """

    check_name: str
    status: str  # "pass" | "fail" | "not_available"
    expected: Any = None
    actual: Any = None
    notes: Optional[str] = None

    @property
    def has_data(self) -> bool:
        return self.status != _NA

    @property
    def passed(self) -> bool:
        return self.status == _PASS


# ---------------------------------------------------------------------------
# Per-case result
# ---------------------------------------------------------------------------

@dataclass
class KnownAnswerCaseResult:
    """Validation result for one historical case.

    Parameters
    ----------
    case_id:
        Matches ``KnownAnswerCase.case_id``.
    company_name:
        Human-readable company name.
    deal_year:
        Year of the deal.
    checks:
        List of ``CheckResult`` objects (one per check run).
    model_value_millions:
        The BVE rNPV supplied by the caller (or None).
    valuation_error_pct:
        |model_value − observed_deal_value| / observed_deal_value × 100.
        None when model_value is not provided.
    overall_status:
        ``"pass"`` | ``"fail"`` | ``"definitions_only"``
        ``"definitions_only"`` means no model outputs were supplied so only
        the internal range sanity check (check 2) ran.
    """

    case_id: str
    company_name: str
    deal_year: int
    checks: list[CheckResult] = field(default_factory=list)
    model_value_millions: Optional[float] = None
    valuation_error_pct: Optional[float] = None
    overall_status: str = "definitions_only"

    @property
    def n_checks_with_data(self) -> int:
        return sum(1 for c in self.checks if c.has_data)

    @property
    def n_passing(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def n_failing(self) -> int:
        return sum(1 for c in self.checks if c.status == _FAIL)


# ---------------------------------------------------------------------------
# Suite result
# ---------------------------------------------------------------------------

@dataclass
class KnownAnswerSuiteResult:
    """Aggregated result across all known-answer cases.

    Parameters
    ----------
    cases:
        One ``KnownAnswerCaseResult`` per case.
    run_date:
        Date the suite was run.
    n_cases:
        Total cases evaluated.
    n_pass:
        Cases with overall_status == "pass".
    n_fail:
        Cases with overall_status == "fail".
    n_definitions_only:
        Cases where no model outputs were provided.
    overall_pass:
        True when n_fail == 0 and at least one case fully passed.
    notes:
        List of informational notes.
    """

    cases: list[KnownAnswerCaseResult] = field(default_factory=list)
    run_date: Optional[date] = None
    n_cases: int = 0
    n_pass: int = 0
    n_fail: int = 0
    n_definitions_only: int = 0
    overall_pass: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_date": self.run_date.isoformat() if self.run_date else None,
            "n_cases": self.n_cases,
            "n_pass": self.n_pass,
            "n_fail": self.n_fail,
            "n_definitions_only": self.n_definitions_only,
            "overall_pass": self.overall_pass,
            "cases": [
                {
                    "case_id": r.case_id,
                    "company_name": r.company_name,
                    "deal_year": r.deal_year,
                    "overall_status": r.overall_status,
                    "n_checks_with_data": r.n_checks_with_data,
                    "n_passing": r.n_passing,
                    "n_failing": r.n_failing,
                    "model_value_millions": r.model_value_millions,
                    "valuation_error_pct": r.valuation_error_pct,
                    "checks": [
                        {
                            "check_name": c.check_name,
                            "status": c.status,
                            "expected": str(c.expected) if c.expected is not None else None,
                            "actual": str(c.actual) if c.actual is not None else None,
                            "notes": c.notes,
                        }
                        for c in r.checks
                    ],
                }
                for r in self.cases
            ],
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def validate_case(
    case: KnownAnswerCase,
    *,
    model_rnpv_millions: Optional[float] = None,
    model_deal_type: Optional[str] = None,
    model_top_buyers: Optional[list[str]] = None,
    model_thesis_direction: Optional[str] = None,
    observed_deal_value_millions: Optional[float] = None,
) -> KnownAnswerCaseResult:
    """Validate one KnownAnswerCase against optional model outputs.

    Parameters
    ----------
    case:
        Case definition to validate against.
    model_rnpv_millions:
        BVE rNPV estimate (from a live run or stored output).
    model_deal_type:
        Deal type string from the model (e.g. ``"acquisition"``).
    model_top_buyers:
        List of acquirer name strings from the model's M&A scorer.
    model_thesis_direction:
        Model thesis direction string (``"long"`` | ``"short"`` | ``"neutral"``).
    observed_deal_value_millions:
        Override for the actual deal value (defaults to case definition value).

    Returns
    -------
    KnownAnswerCaseResult
    """
    deal_value = observed_deal_value_millions or case.observed_deal_value_millions
    checks: list[CheckResult] = []

    # Check 1: value_in_range
    checks.append(_check_value_in_range(case, model_rnpv_millions))

    # Check 2: deal_directional (always evaluable)
    checks.append(_check_deal_directional(case, deal_value))

    # Check 3: deal_type_correct
    checks.append(_check_deal_type(case, model_deal_type))

    # Check 4: buyer_identified
    checks.append(_check_buyer_identified(case, model_top_buyers))

    # Check 5: thesis_direction_match
    checks.append(_check_thesis_direction(case, model_thesis_direction))

    # Compute valuation error
    val_error_pct: Optional[float] = None
    if model_rnpv_millions is not None and deal_value > 0:
        val_error_pct = round(
            abs(model_rnpv_millions - deal_value) / deal_value * 100.0, 1
        )

    # Determine overall status
    checks_with_data = [c for c in checks if c.has_data]
    model_checks = [c for c in checks if c.check_name != "deal_directional" and c.has_data]

    if not model_checks:
        # No model outputs — only deal_directional ran
        if all(c.passed for c in checks_with_data):
            overall_status = "definitions_only"
        else:
            # deal_directional failed → case definition is suspect
            overall_status = "definition_error"
    else:
        n_data = len(checks_with_data)
        n_pass = sum(1 for c in checks_with_data if c.passed)
        threshold = max(1, (n_data + 1) // 2)  # majority
        overall_status = "pass" if n_pass >= threshold else "fail"

    return KnownAnswerCaseResult(
        case_id=case.case_id,
        company_name=case.company_name,
        deal_year=case.deal_year,
        checks=checks,
        model_value_millions=model_rnpv_millions,
        valuation_error_pct=val_error_pct,
        overall_status=overall_status,
    )


def run_suite(
    cases: list[KnownAnswerCase],
    *,
    model_outputs: Optional[dict[str, dict]] = None,
    run_date: Optional[date] = None,
) -> KnownAnswerSuiteResult:
    """Run the full known-answer validation suite.

    Parameters
    ----------
    cases:
        List of ``KnownAnswerCase`` objects (from ``load_cases()``).
    model_outputs:
        Optional dict mapping ``case_id`` → model output dict. Each dict
        may contain: ``model_rnpv_millions``, ``model_deal_type``,
        ``model_top_buyers`` (list of str), ``model_thesis_direction``.
    run_date:
        Date for the result; defaults to today.

    Returns
    -------
    KnownAnswerSuiteResult
    """
    ref = run_date or date.today()
    outputs = model_outputs or {}
    case_results: list[KnownAnswerCaseResult] = []
    notes: list[str] = []

    for case in cases:
        mo = outputs.get(case.case_id) or {}
        result = validate_case(
            case,
            model_rnpv_millions=_opt_float(mo.get("model_rnpv_millions")),
            model_deal_type=mo.get("model_deal_type"),
            model_top_buyers=mo.get("model_top_buyers"),
            model_thesis_direction=mo.get("model_thesis_direction"),
        )
        case_results.append(result)

    n_pass = sum(1 for r in case_results if r.overall_status == "pass")
    n_fail = sum(1 for r in case_results if r.overall_status == "fail")
    n_def_only = sum(1 for r in case_results if r.overall_status in ("definitions_only", "definition_error"))

    if n_def_only == len(case_results):
        notes.append(
            "No model outputs provided — running in definitions-only mode. "
            "Supply model outputs via --model-outputs JSON or a live BVE run."
        )

    overall_pass = n_fail == 0 and n_pass > 0

    return KnownAnswerSuiteResult(
        cases=case_results,
        run_date=ref,
        n_cases=len(case_results),
        n_pass=n_pass,
        n_fail=n_fail,
        n_definitions_only=n_def_only,
        overall_pass=overall_pass,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_value_in_range(
    case: KnownAnswerCase,
    model_rnpv_millions: Optional[float],
) -> CheckResult:
    if model_rnpv_millions is None:
        return CheckResult(
            check_name="value_in_range",
            status=_NA,
            expected=f"${case.model_value_range_millions_low:,.0f}M – ${case.model_value_range_millions_high:,.0f}M",
            notes="No model rNPV provided",
        )
    low = case.model_value_range_millions_low
    high = case.model_value_range_millions_high
    passed = low <= model_rnpv_millions <= high
    return CheckResult(
        check_name="value_in_range",
        status=_PASS if passed else _FAIL,
        expected=f"${low:,.0f}M – ${high:,.0f}M",
        actual=f"${model_rnpv_millions:,.0f}M",
        notes=None if passed else (
            f"Model rNPV ${model_rnpv_millions:,.0f}M is "
            f"{'below' if model_rnpv_millions < low else 'above'} expected range"
        ),
    )


def _check_deal_directional(
    case: KnownAnswerCase,
    deal_value: float,
) -> CheckResult:
    """Validate that the observed deal value falls in a generous band around the model range.

    This check validates case quality: if the case range is absurdly far from
    the actual deal price, the case definition itself is suspect.
    """
    low = case.model_value_range_millions_low
    high = case.model_value_range_millions_high
    floor = _DEAL_DIRECTIONAL_LOW_FACTOR * low
    ceiling = _DEAL_DIRECTIONAL_HIGH_FACTOR * high
    passed = floor <= deal_value <= ceiling
    return CheckResult(
        check_name="deal_directional",
        status=_PASS if passed else _FAIL,
        expected=f"${floor:,.0f}M – ${ceiling:,.0f}M (directional band)",
        actual=f"${deal_value:,.0f}M (observed deal)",
        notes=None if passed else (
            f"Observed deal value ${deal_value:,.0f}M is outside directional "
            f"band ${floor:,.0f}M – ${ceiling:,.0f}M — case range may need revision"
        ),
    )


def _check_deal_type(
    case: KnownAnswerCase,
    model_deal_type: Optional[str],
) -> CheckResult:
    if model_deal_type is None:
        return CheckResult(
            check_name="deal_type_correct",
            status=_NA,
            expected=case.expected_deal_type,
            notes="No model deal type provided",
        )
    expected = case.expected_deal_type.lower().strip()
    actual = model_deal_type.lower().strip()
    passed = expected == actual or expected in actual or actual in expected
    return CheckResult(
        check_name="deal_type_correct",
        status=_PASS if passed else _FAIL,
        expected=case.expected_deal_type,
        actual=model_deal_type,
        notes=None if passed else f"Expected '{case.expected_deal_type}', got '{model_deal_type}'",
    )


def _check_buyer_identified(
    case: KnownAnswerCase,
    model_top_buyers: Optional[list[str]],
) -> CheckResult:
    if not model_top_buyers:
        return CheckResult(
            check_name="buyer_identified",
            status=_NA,
            expected=case.expected_primary_buyer,
            notes="No model buyer list provided",
        )
    expected_lower = case.expected_primary_buyer.lower()
    found = any(
        expected_lower in b.lower() or b.lower() in expected_lower
        for b in model_top_buyers
    )
    return CheckResult(
        check_name="buyer_identified",
        status=_PASS if found else _FAIL,
        expected=case.expected_primary_buyer,
        actual=", ".join(model_top_buyers[:3]),
        notes=None if found else (
            f"Expected buyer '{case.expected_primary_buyer}' not in top buyers: "
            + ", ".join(model_top_buyers[:3])
        ),
    )


def _check_thesis_direction(
    case: KnownAnswerCase,
    model_thesis_direction: Optional[str],
) -> CheckResult:
    if model_thesis_direction is None:
        return CheckResult(
            check_name="thesis_direction_match",
            status=_NA,
            expected=case.thesis_direction,
            notes="No model thesis direction provided",
        )
    expected = case.thesis_direction.lower().strip()
    actual = model_thesis_direction.lower().strip()
    passed = expected == actual or (expected == "long" and actual in ("buy", "add", "long"))
    return CheckResult(
        check_name="thesis_direction_match",
        status=_PASS if passed else _FAIL,
        expected=case.thesis_direction,
        actual=model_thesis_direction,
        notes=None if passed else f"Expected '{case.thesis_direction}', got '{model_thesis_direction}'",
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_known_answer_suite(result: KnownAnswerSuiteResult) -> str:
    """Render a KnownAnswerSuiteResult as a Markdown section."""
    na = "N/A"
    run_str = result.run_date.isoformat() if result.run_date else na

    status_icon = "PASS" if result.overall_pass else ("DEFINITIONS ONLY" if result.n_fail == 0 else "FAIL")

    lines = [
        "## Known-Answer Validation Suite",
        "",
        f"**Run date:** {run_str}  |  "
        f"**Cases:** {result.n_cases}  |  "
        f"**Pass:** {result.n_pass}  |  "
        f"**Fail:** {result.n_fail}  |  "
        f"**Definitions only:** {result.n_definitions_only}  |  "
        f"**Status:** `{status_icon}`",
        "",
        "> **Validation philosophy:** Directional institutional validation only. "
        "A model rNPV within the expected range and a correct strategic-fit "
        "direction constitutes a pass. Perfect price prediction is not required.",
        "",
    ]

    if result.notes:
        for note in result.notes:
            lines.append(f"> {note}")
        lines.append("")

    # Summary table
    lines += [
        "### Case Summary",
        "",
        "| Case | Company | Year | Deal ($M) | Model Range ($M) | Model rNPV ($M) | Error % | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for case_result in result.cases:
        # Find the case's range from checks
        vir_check = next((c for c in case_result.checks if c.check_name == "value_in_range"), None)
        range_str = vir_check.expected if vir_check and vir_check.expected else na
        model_val_str = f"${case_result.model_value_millions:,.0f}" if case_result.model_value_millions is not None else na
        error_str = f"{case_result.valuation_error_pct:.1f}%" if case_result.valuation_error_pct is not None else na
        # Get deal value from deal_directional check
        dd_check = next((c for c in case_result.checks if c.check_name == "deal_directional"), None)
        deal_val_str = na
        if dd_check and dd_check.actual:
            # actual looks like "$10,800M (observed deal)"
            deal_val_str = dd_check.actual.split("(")[0].strip()
        status_emoji = {
            "pass": "PASS",
            "fail": "FAIL",
            "definitions_only": "DEF ONLY",
            "definition_error": "DEF ERROR",
        }.get(case_result.overall_status, case_result.overall_status)
        lines.append(
            f"| {case_result.case_id} | {case_result.company_name} | "
            f"{case_result.deal_year} | {deal_val_str} | {range_str} | "
            f"{model_val_str} | {error_str} | `{status_emoji}` |"
        )

    lines.append("")

    # Per-case details
    lines += ["### Check Details", ""]
    for case_result in result.cases:
        lines.append(f"**{case_result.company_name}** (`{case_result.case_id}`)")
        lines.append("")
        lines += [
            "| Check | Status | Expected | Actual | Notes |",
            "|---|---|---|---|---|",
        ]
        for chk in case_result.checks:
            icon = {"pass": "PASS", "fail": "FAIL", "not_available": "N/A"}.get(chk.status, chk.status)
            exp_str = str(chk.expected) if chk.expected is not None else na
            act_str = str(chk.actual) if chk.actual is not None else na
            note_str = chk.notes or "—"
            if len(note_str) > 70:
                note_str = note_str[:67] + "..."
            lines.append(
                f"| {chk.check_name} | `{icon}` | {exp_str} | {act_str} | {note_str} |"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opt_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
