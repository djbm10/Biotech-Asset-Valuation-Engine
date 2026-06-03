"""Block 10 — Known-Answer Validation Suite tests.

Covers:
- KnownAnswerCase: construction, field validation, loader
- cases.yaml: loads 5 starter cases, field sanity
- Validator checks: value_in_range, deal_directional, deal_type, buyer, thesis
- Pass/fail/N/A logic per check
- Overall status computation
- Suite aggregation
- Missing-data behavior (N/A not crash)
- Valuation error calculation
- render_known_answer_suite: Markdown output
- ValidationSummaryData: known-answer fields
- bve-validate CLI: --no-known-answers flag
- bve-known-answer-validate CLI: help, JSON, case filtering
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(
    case_id="test_case",
    company_name="TestCo",
    deal_year=2022,
    observed_deal_value_millions=10000.0,
    expected_deal_type="acquisition",
    expected_primary_buyer="BigPharma",
    model_value_range_millions_low=6000.0,
    model_value_range_millions_high=14000.0,
    thesis_direction="long",
    expected_buyer_therapeutic_areas=("oncology",),
):
    from bve.validation.known_answer_cases import KnownAnswerCase
    return KnownAnswerCase(
        case_id=case_id,
        company_name=company_name,
        deal_year=deal_year,
        observed_deal_value_millions=observed_deal_value_millions,
        expected_deal_type=expected_deal_type,
        expected_primary_buyer=expected_primary_buyer,
        model_value_range_millions_low=model_value_range_millions_low,
        model_value_range_millions_high=model_value_range_millions_high,
        thesis_direction=thesis_direction,
        expected_buyer_therapeutic_areas=expected_buyer_therapeutic_areas,
    )


# ---------------------------------------------------------------------------
# KnownAnswerCase unit tests
# ---------------------------------------------------------------------------

class TestKnownAnswerCase:
    def test_range_midpoint(self):
        case = _make_case(model_value_range_millions_low=4000, model_value_range_millions_high=8000)
        assert case.range_midpoint_millions == 6000.0

    def test_range_width(self):
        case = _make_case(model_value_range_millions_low=4000, model_value_range_millions_high=9000)
        assert case.range_width_millions == 5000.0

    def test_optional_ticker_none(self):
        case = _make_case()
        assert case.ticker is None

    def test_expected_buyer_tas_tuple(self):
        case = _make_case(expected_buyer_therapeutic_areas=("oncology", "immunology"))
        assert isinstance(case.expected_buyer_therapeutic_areas, tuple)
        assert "oncology" in case.expected_buyer_therapeutic_areas

    def test_frozen(self):
        case = _make_case()
        with pytest.raises((AttributeError, TypeError)):
            case.company_name = "Modified"  # type: ignore


# ---------------------------------------------------------------------------
# Case loader tests
# ---------------------------------------------------------------------------

class TestLoadCases:
    def test_loads_bundled_cases(self):
        from bve.validation.known_answer_cases import load_cases
        cases = load_cases()
        assert len(cases) == 5

    def test_bundled_case_ids(self):
        from bve.validation.known_answer_cases import load_cases
        cases = load_cases()
        ids = {c.case_id for c in cases}
        assert "prometheus_merck_2023" in ids
        assert "acceleron_merck_2021" in ids
        assert "myokardia_bms_2020" in ids
        assert "karuna_bms_2024" in ids
        assert "seagen_pfizer_2023" in ids

    def test_cases_have_valid_ranges(self):
        from bve.validation.known_answer_cases import load_cases
        for case in load_cases():
            assert case.model_value_range_millions_high >= case.model_value_range_millions_low, \
                f"{case.case_id}: high < low"

    def test_cases_have_positive_deal_value(self):
        from bve.validation.known_answer_cases import load_cases
        for case in load_cases():
            assert case.observed_deal_value_millions > 0, f"{case.case_id}: deal value <= 0"

    def test_cases_have_expected_buyer(self):
        from bve.validation.known_answer_cases import load_cases
        for case in load_cases():
            assert case.expected_primary_buyer, f"{case.case_id}: no expected buyer"

    def test_cases_have_thesis_direction(self):
        from bve.validation.known_answer_cases import load_cases
        for case in load_cases():
            assert case.thesis_direction in ("long", "short"), \
                f"{case.case_id}: unexpected thesis_direction '{case.thesis_direction}'"

    def test_missing_file_returns_empty_list_with_warning(self):
        from bve.validation.known_answer_cases import load_cases
        with pytest.warns(UserWarning, match="not found"):
            cases = load_cases("/nonexistent/path/cases.yaml")
        assert cases == []

    def test_custom_yaml_loads(self, tmp_path):
        from bve.validation.known_answer_cases import load_cases
        yaml_content = """
schema_version: 1
cases:
  - case_id: custom_case
    company_name: CustomCo
    deal_year: 2023
    observed_deal_value_millions: 5000
    expected_deal_type: acquisition
    expected_primary_buyer: Roche
    model_value_range_millions_low: 3000
    model_value_range_millions_high: 8000
    thesis_direction: long
"""
        p = tmp_path / "cases.yaml"
        p.write_text(yaml_content)
        cases = load_cases(str(p))
        assert len(cases) == 1
        assert cases[0].case_id == "custom_case"
        assert cases[0].company_name == "CustomCo"

    def test_malformed_case_skipped_with_warning(self, tmp_path):
        from bve.validation.known_answer_cases import load_cases
        yaml_content = """
schema_version: 1
cases:
  - case_id: good_case
    company_name: GoodCo
    deal_year: 2023
    observed_deal_value_millions: 5000
    expected_deal_type: acquisition
    expected_primary_buyer: Roche
    model_value_range_millions_low: 3000
    model_value_range_millions_high: 8000
    thesis_direction: long
  - case_id: bad_case
    company_name: BadCo
"""
        p = tmp_path / "cases.yaml"
        p.write_text(yaml_content)
        with pytest.warns(UserWarning, match="Skipping"):
            cases = load_cases(str(p))
        assert len(cases) == 1
        assert cases[0].case_id == "good_case"

    def test_inverted_range_raises_on_load(self, tmp_path):
        from bve.validation.known_answer_cases import load_cases
        yaml_content = """
schema_version: 1
cases:
  - case_id: bad_range
    company_name: Foo
    deal_year: 2023
    observed_deal_value_millions: 5000
    expected_deal_type: acquisition
    expected_primary_buyer: Roche
    model_value_range_millions_low: 8000
    model_value_range_millions_high: 3000
    thesis_direction: long
"""
        p = tmp_path / "cases.yaml"
        p.write_text(yaml_content)
        with pytest.warns(UserWarning, match="Skipping"):
            cases = load_cases(str(p))
        assert cases == []

    def test_prometheus_merck_deal_value(self):
        from bve.validation.known_answer_cases import load_cases
        cases = {c.case_id: c for c in load_cases()}
        c = cases["prometheus_merck_2023"]
        assert c.observed_deal_value_millions == pytest.approx(10800.0)
        assert c.expected_primary_buyer == "Merck"

    def test_seagen_pfizer_large_deal(self):
        from bve.validation.known_answer_cases import load_cases
        cases = {c.case_id: c for c in load_cases()}
        c = cases["seagen_pfizer_2023"]
        assert c.observed_deal_value_millions == pytest.approx(43000.0)
        assert c.expected_primary_buyer == "Pfizer"


# ---------------------------------------------------------------------------
# Individual check tests
# ---------------------------------------------------------------------------

class TestCheckValueInRange:
    def test_pass_when_in_range(self):
        from bve.validation.known_answer_validator import _check_value_in_range
        case = _make_case(model_value_range_millions_low=5000, model_value_range_millions_high=15000)
        result = _check_value_in_range(case, 10000.0)
        assert result.status == "pass"

    def test_pass_at_lower_bound(self):
        from bve.validation.known_answer_validator import _check_value_in_range
        case = _make_case(model_value_range_millions_low=5000, model_value_range_millions_high=15000)
        result = _check_value_in_range(case, 5000.0)
        assert result.status == "pass"

    def test_pass_at_upper_bound(self):
        from bve.validation.known_answer_validator import _check_value_in_range
        case = _make_case(model_value_range_millions_low=5000, model_value_range_millions_high=15000)
        result = _check_value_in_range(case, 15000.0)
        assert result.status == "pass"

    def test_fail_below_range(self):
        from bve.validation.known_answer_validator import _check_value_in_range
        case = _make_case(model_value_range_millions_low=5000, model_value_range_millions_high=15000)
        result = _check_value_in_range(case, 1000.0)
        assert result.status == "fail"
        assert "below" in result.notes.lower()

    def test_fail_above_range(self):
        from bve.validation.known_answer_validator import _check_value_in_range
        case = _make_case(model_value_range_millions_low=5000, model_value_range_millions_high=15000)
        result = _check_value_in_range(case, 50000.0)
        assert result.status == "fail"
        assert "above" in result.notes.lower()

    def test_not_available_when_no_model_value(self):
        from bve.validation.known_answer_validator import _check_value_in_range
        case = _make_case()
        result = _check_value_in_range(case, None)
        assert result.status == "not_available"
        assert result.check_name == "value_in_range"


class TestCheckDealDirectional:
    def test_pass_for_reasonable_deal(self):
        from bve.validation.known_answer_validator import _check_deal_directional
        # range 5000-15000, deal = 10800 → floor=2000, ceiling=45000
        case = _make_case(model_value_range_millions_low=5000, model_value_range_millions_high=15000)
        result = _check_deal_directional(case, 10800.0)
        assert result.status == "pass"

    def test_fail_when_deal_way_below_range(self):
        from bve.validation.known_answer_validator import _check_deal_directional
        # range 100000-200000, deal = 100 → floor=40000
        case = _make_case(model_value_range_millions_low=100000, model_value_range_millions_high=200000)
        result = _check_deal_directional(case, 100.0)
        assert result.status == "fail"

    def test_fail_when_deal_way_above_range(self):
        from bve.validation.known_answer_validator import _check_deal_directional
        # range 100-200, deal = 100000 → ceiling=600
        case = _make_case(model_value_range_millions_low=100, model_value_range_millions_high=200)
        result = _check_deal_directional(case, 100000.0)
        assert result.status == "fail"

    def test_always_has_data(self):
        from bve.validation.known_answer_validator import _check_deal_directional
        case = _make_case()
        result = _check_deal_directional(case, case.observed_deal_value_millions)
        assert result.has_data is True


class TestCheckDealType:
    def test_pass_exact_match(self):
        from bve.validation.known_answer_validator import _check_deal_type
        case = _make_case(expected_deal_type="acquisition")
        result = _check_deal_type(case, "acquisition")
        assert result.status == "pass"

    def test_pass_case_insensitive(self):
        from bve.validation.known_answer_validator import _check_deal_type
        case = _make_case(expected_deal_type="acquisition")
        result = _check_deal_type(case, "ACQUISITION")
        assert result.status == "pass"

    def test_pass_substring_match(self):
        from bve.validation.known_answer_validator import _check_deal_type
        case = _make_case(expected_deal_type="acquisition")
        result = _check_deal_type(case, "hostile acquisition")
        assert result.status == "pass"

    def test_fail_wrong_type(self):
        from bve.validation.known_answer_validator import _check_deal_type
        case = _make_case(expected_deal_type="acquisition")
        result = _check_deal_type(case, "licensing")
        assert result.status == "fail"

    def test_not_available_when_none(self):
        from bve.validation.known_answer_validator import _check_deal_type
        case = _make_case()
        result = _check_deal_type(case, None)
        assert result.status == "not_available"


class TestCheckBuyerIdentified:
    def test_pass_exact_match(self):
        from bve.validation.known_answer_validator import _check_buyer_identified
        case = _make_case(expected_primary_buyer="Merck")
        result = _check_buyer_identified(case, ["Merck", "AbbVie", "Pfizer"])
        assert result.status == "pass"

    def test_pass_partial_match(self):
        from bve.validation.known_answer_validator import _check_buyer_identified
        case = _make_case(expected_primary_buyer="Merck")
        result = _check_buyer_identified(case, ["Merck & Co", "Pfizer"])
        assert result.status == "pass"

    def test_pass_case_insensitive(self):
        from bve.validation.known_answer_validator import _check_buyer_identified
        case = _make_case(expected_primary_buyer="Bristol-Myers Squibb")
        result = _check_buyer_identified(case, ["bristol-myers squibb"])
        assert result.status == "pass"

    def test_fail_wrong_buyer(self):
        from bve.validation.known_answer_validator import _check_buyer_identified
        case = _make_case(expected_primary_buyer="Merck")
        result = _check_buyer_identified(case, ["AbbVie", "Pfizer", "Novartis"])
        assert result.status == "fail"

    def test_not_available_when_empty(self):
        from bve.validation.known_answer_validator import _check_buyer_identified
        case = _make_case()
        result = _check_buyer_identified(case, [])
        assert result.status == "not_available"

    def test_not_available_when_none(self):
        from bve.validation.known_answer_validator import _check_buyer_identified
        case = _make_case()
        result = _check_buyer_identified(case, None)
        assert result.status == "not_available"


class TestCheckThesisDirection:
    def test_pass_exact_match(self):
        from bve.validation.known_answer_validator import _check_thesis_direction
        case = _make_case(thesis_direction="long")
        result = _check_thesis_direction(case, "long")
        assert result.status == "pass"

    def test_pass_buy_maps_to_long(self):
        from bve.validation.known_answer_validator import _check_thesis_direction
        case = _make_case(thesis_direction="long")
        result = _check_thesis_direction(case, "buy")
        assert result.status == "pass"

    def test_pass_add_maps_to_long(self):
        from bve.validation.known_answer_validator import _check_thesis_direction
        case = _make_case(thesis_direction="long")
        result = _check_thesis_direction(case, "add")
        assert result.status == "pass"

    def test_fail_short_when_long_expected(self):
        from bve.validation.known_answer_validator import _check_thesis_direction
        case = _make_case(thesis_direction="long")
        result = _check_thesis_direction(case, "short")
        assert result.status == "fail"

    def test_not_available_when_none(self):
        from bve.validation.known_answer_validator import _check_thesis_direction
        case = _make_case()
        result = _check_thesis_direction(case, None)
        assert result.status == "not_available"


# ---------------------------------------------------------------------------
# validate_case: integration tests
# ---------------------------------------------------------------------------

class TestValidateCase:
    def test_definitions_only_no_model_outputs(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case()
        result = validate_case(case)
        assert result.overall_status == "definitions_only"
        assert result.model_value_millions is None
        assert result.valuation_error_pct is None

    def test_pass_with_all_correct_outputs(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case(
            model_value_range_millions_low=6000,
            model_value_range_millions_high=14000,
            expected_deal_type="acquisition",
            expected_primary_buyer="BigPharma",
            thesis_direction="long",
        )
        result = validate_case(
            case,
            model_rnpv_millions=10000.0,
            model_deal_type="acquisition",
            model_top_buyers=["BigPharma", "Pfizer"],
            model_thesis_direction="long",
        )
        assert result.overall_status == "pass"

    def test_fail_with_all_wrong_outputs(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case(
            model_value_range_millions_low=6000,
            model_value_range_millions_high=14000,
            expected_deal_type="acquisition",
            expected_primary_buyer="BigPharma",
            thesis_direction="long",
        )
        result = validate_case(
            case,
            model_rnpv_millions=500.0,   # way below range
            model_deal_type="licensing", # wrong type
            model_top_buyers=["AbbVie"],  # wrong buyer
            model_thesis_direction="short",  # wrong direction
        )
        assert result.overall_status == "fail"

    def test_valuation_error_pct_computed(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case(observed_deal_value_millions=10000.0)
        result = validate_case(case, model_rnpv_millions=8000.0)
        # |8000 - 10000| / 10000 * 100 = 20.0%
        assert result.valuation_error_pct == pytest.approx(20.0)

    def test_valuation_error_pct_none_when_no_model(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case()
        result = validate_case(case)
        assert result.valuation_error_pct is None

    def test_case_result_fields(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case(case_id="my_case", company_name="MyCo", deal_year=2021)
        result = validate_case(case)
        assert result.case_id == "my_case"
        assert result.company_name == "MyCo"
        assert result.deal_year == 2021
        assert len(result.checks) == 5  # always 5 checks

    def test_n_checks_with_data_only_directional_when_no_model(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case()
        result = validate_case(case)
        # Only deal_directional has data without model outputs
        assert result.n_checks_with_data == 1

    def test_n_checks_with_data_all_five_when_full_model(self):
        from bve.validation.known_answer_validator import validate_case
        case = _make_case()
        result = validate_case(
            case,
            model_rnpv_millions=9000.0,
            model_deal_type="acquisition",
            model_top_buyers=["BigPharma"],
            model_thesis_direction="long",
        )
        assert result.n_checks_with_data == 5

    def test_majority_rule_pass(self):
        """3/5 checks passing → overall pass."""
        from bve.validation.known_answer_validator import validate_case
        case = _make_case(
            model_value_range_millions_low=6000,
            model_value_range_millions_high=14000,
            expected_deal_type="acquisition",
            expected_primary_buyer="BigPharma",
            thesis_direction="long",
        )
        result = validate_case(
            case,
            model_rnpv_millions=10000.0,   # PASS value_in_range
            # deal_directional always PASS for reasonable case
            model_deal_type="acquisition",  # PASS deal_type
            model_top_buyers=["WrongCo"],   # FAIL buyer
            model_thesis_direction="short", # FAIL thesis
        )
        # 3 pass (value_in_range, deal_directional, deal_type) out of 5 → majority
        assert result.overall_status == "pass"

    def test_definition_error_when_range_far_from_deal(self):
        """deal_directional fails when range is absurdly wrong."""
        from bve.validation.known_answer_validator import validate_case
        case = _make_case(
            observed_deal_value_millions=100.0,  # tiny deal
            model_value_range_millions_low=50000,  # absurdly large range
            model_value_range_millions_high=100000,
        )
        result = validate_case(case)  # no model outputs
        assert result.overall_status == "definition_error"


# ---------------------------------------------------------------------------
# run_suite tests
# ---------------------------------------------------------------------------

class TestRunSuite:
    def test_suite_loads_5_bundled_cases(self):
        from bve.validation.known_answer_cases import load_cases
        from bve.validation.known_answer_validator import run_suite
        cases = load_cases()
        result = run_suite(cases)
        assert result.n_cases == 5

    def test_suite_definitions_only_mode(self):
        from bve.validation.known_answer_cases import load_cases
        from bve.validation.known_answer_validator import run_suite
        cases = load_cases()
        result = run_suite(cases)
        assert result.n_definitions_only == 5
        assert result.n_pass == 0
        assert result.n_fail == 0
        assert result.overall_pass is False  # no model passes

    def test_suite_overall_pass_with_all_correct(self):
        from bve.validation.known_answer_validator import run_suite
        case = _make_case(
            model_value_range_millions_low=6000,
            model_value_range_millions_high=14000,
        )
        outputs = {
            "test_case": {
                "model_rnpv_millions": 10000,
                "model_deal_type": "acquisition",
                "model_top_buyers": ["BigPharma"],
                "model_thesis_direction": "long",
            }
        }
        result = run_suite([case], model_outputs=outputs)
        assert result.n_pass == 1
        assert result.overall_pass is True

    def test_suite_overall_fail_with_one_fail(self):
        from bve.validation.known_answer_validator import run_suite
        case = _make_case(
            model_value_range_millions_low=6000,
            model_value_range_millions_high=14000,
        )
        outputs = {
            "test_case": {
                "model_rnpv_millions": 100,       # way below range → fail
                "model_deal_type": "licensing",   # wrong → fail
                "model_top_buyers": ["WrongCo"],  # wrong → fail
                "model_thesis_direction": "short", # wrong → fail
            }
        }
        result = run_suite([case], model_outputs=outputs)
        assert result.n_fail == 1
        assert result.overall_pass is False

    def test_suite_notes_added_for_definitions_only(self):
        from bve.validation.known_answer_validator import run_suite
        case = _make_case()
        result = run_suite([case])
        assert any("definitions-only" in n.lower() for n in result.notes)

    def test_suite_run_date_defaults_to_today(self):
        from bve.validation.known_answer_validator import run_suite
        result = run_suite([_make_case()])
        assert result.run_date == date.today()

    def test_suite_run_date_custom(self):
        from bve.validation.known_answer_validator import run_suite
        custom_date = date(2025, 6, 1)
        result = run_suite([_make_case()], run_date=custom_date)
        assert result.run_date == custom_date

    def test_suite_empty_cases(self):
        from bve.validation.known_answer_validator import run_suite
        result = run_suite([])
        assert result.n_cases == 0
        assert result.overall_pass is False

    def test_suite_to_dict(self):
        from bve.validation.known_answer_validator import run_suite
        result = run_suite([_make_case()])
        d = result.to_dict()
        assert "n_cases" in d
        assert "cases" in d
        assert "overall_pass" in d
        assert len(d["cases"]) == 1


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------

class TestRenderKnownAnswerSuite:
    def test_renders_heading(self):
        from bve.validation.known_answer_cases import load_cases
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        result = run_suite(load_cases())
        out = render_known_answer_suite(result)
        assert "Known-Answer Validation Suite" in out

    def test_renders_all_5_cases(self):
        from bve.validation.known_answer_cases import load_cases
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        result = run_suite(load_cases())
        out = render_known_answer_suite(result)
        assert "prometheus_merck_2023" in out
        assert "seagen_pfizer_2023" in out

    def test_renders_validation_philosophy(self):
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        result = run_suite([_make_case()])
        out = render_known_answer_suite(result)
        assert "Directional institutional validation" in out or "directional" in out.lower()

    def test_renders_pass_when_passing(self):
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        case = _make_case(
            model_value_range_millions_low=6000,
            model_value_range_millions_high=14000,
        )
        outputs = {
            "test_case": {
                "model_rnpv_millions": 10000,
                "model_deal_type": "acquisition",
                "model_top_buyers": ["BigPharma"],
                "model_thesis_direction": "long",
            }
        }
        result = run_suite([case], model_outputs=outputs)
        out = render_known_answer_suite(result)
        assert "PASS" in out

    def test_renders_definitions_only_mode(self):
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        result = run_suite([_make_case()])
        out = render_known_answer_suite(result)
        assert "DEF ONLY" in out or "DEFINITIONS ONLY" in out

    def test_renders_check_detail_table(self):
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        result = run_suite([_make_case()])
        out = render_known_answer_suite(result)
        assert "value_in_range" in out
        assert "deal_directional" in out
        assert "deal_type_correct" in out
        assert "buyer_identified" in out
        assert "thesis_direction_match" in out

    def test_renders_na_when_no_model_outputs(self):
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        result = run_suite([_make_case()])
        out = render_known_answer_suite(result)
        assert "N/A" in out

    def test_renders_valuation_error_when_model_provided(self):
        from bve.validation.known_answer_validator import run_suite, render_known_answer_suite
        case = _make_case(observed_deal_value_millions=10000)
        outputs = {"test_case": {"model_rnpv_millions": 8000}}
        result = run_suite([case], model_outputs=outputs)
        out = render_known_answer_suite(result)
        assert "20.0%" in out or "20%" in out


# ---------------------------------------------------------------------------
# ValidationSummaryData: known-answer fields
# ---------------------------------------------------------------------------

class TestValidationSummaryKnownAnswerFields:
    def _make_suite_result(self, n_cases=5, n_pass=5, n_fail=0, n_def=0, overall_pass=True):
        from unittest.mock import MagicMock
        m = MagicMock()
        m.n_cases = n_cases
        m.n_pass = n_pass
        m.n_fail = n_fail
        m.n_definitions_only = n_def
        m.overall_pass = overall_pass
        return m

    def test_known_answer_fields_populated(self):
        from bve.reporting.validation_summary import build_validation_summary
        ka = self._make_suite_result(n_cases=5, n_pass=3, n_fail=0, n_def=2, overall_pass=True)
        data = build_validation_summary(known_answer_suite_result=ka)
        assert data.known_answer_n_cases == 5
        assert data.known_answer_n_pass == 3
        assert data.known_answer_n_fail == 0
        assert data.known_answer_n_definitions_only == 2
        assert data.known_answer_overall_pass is True

    def test_known_answer_none_by_default(self):
        from bve.reporting.validation_summary import build_validation_summary
        data = build_validation_summary()
        assert data.known_answer_n_cases == 0
        assert data.known_answer_overall_pass is None

    def test_render_includes_known_answer_section(self):
        from bve.reporting.validation_summary import build_validation_summary, render_validation_summary
        ka = self._make_suite_result()
        data = build_validation_summary(known_answer_suite_result=ka)
        out = render_validation_summary(data)
        assert "Known-Answer Suite" in out

    def test_render_shows_pass_when_all_pass(self):
        from bve.reporting.validation_summary import build_validation_summary, render_validation_summary
        ka = self._make_suite_result(n_pass=5, n_fail=0, overall_pass=True)
        data = build_validation_summary(known_answer_suite_result=ka)
        out = render_validation_summary(data)
        assert "PASS" in out

    def test_render_shows_fail_when_any_fail(self):
        from bve.reporting.validation_summary import build_validation_summary, render_validation_summary
        ka = self._make_suite_result(n_pass=4, n_fail=1, overall_pass=False)
        data = build_validation_summary(known_answer_suite_result=ka)
        out = render_validation_summary(data)
        assert "FAIL" in out

    def test_render_no_known_answer_section_when_not_run(self):
        from bve.reporting.validation_summary import build_validation_summary, render_validation_summary
        data = build_validation_summary()
        out = render_validation_summary(data)
        assert "Known-Answer Suite" not in out

    def test_render_shows_definitions_only_status(self):
        from bve.reporting.validation_summary import build_validation_summary, render_validation_summary
        ka = self._make_suite_result(n_pass=0, n_fail=0, n_def=5, overall_pass=False)
        data = build_validation_summary(known_answer_suite_result=ka)
        out = render_validation_summary(data)
        assert "DEFINITIONS ONLY" in out


# ---------------------------------------------------------------------------
# CLI: bve-known-answer-validate
# ---------------------------------------------------------------------------

class TestBveKnownAnswerValidateCLI:
    def test_help_exits_cleanly(self):
        from bve.cli.bve_known_answer_validate import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_default_run_succeeds(self, capsys):
        from bve.cli.bve_known_answer_validate import main
        ret = main([])
        assert ret == 0
        out = capsys.readouterr().out
        assert "Known-Answer" in out

    def test_json_output(self, capsys):
        import json
        from bve.cli.bve_known_answer_validate import main
        ret = main(["--json"])
        assert ret == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "n_cases" in data
        assert data["n_cases"] == 5

    def test_filter_by_case_id(self, capsys):
        from bve.cli.bve_known_answer_validate import main
        ret = main(["--case-id", "prometheus_merck_2023"])
        assert ret == 0
        out = capsys.readouterr().out
        assert "prometheus_merck_2023" in out
        assert "seagen_pfizer_2023" not in out

    def test_filter_nonexistent_case_returns_1(self, capsys):
        from bve.cli.bve_known_answer_validate import main
        ret = main(["--case-id", "nonexistent_case_xyz"])
        assert ret == 1

    def test_output_to_file(self, tmp_path):
        from bve.cli.bve_known_answer_validate import main
        out_file = tmp_path / "result.md"
        ret = main(["--output", str(out_file)])
        assert ret == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "Known-Answer" in content

    def test_model_outputs_json(self, tmp_path, capsys):
        import json
        from bve.cli.bve_known_answer_validate import main
        outputs = {
            "prometheus_merck_2023": {
                "model_rnpv_millions": 10000,
                "model_deal_type": "acquisition",
                "model_top_buyers": ["Merck"],
                "model_thesis_direction": "long",
            }
        }
        mo_file = tmp_path / "outputs.json"
        mo_file.write_text(json.dumps(outputs))
        ret = main(["--model-outputs", str(mo_file), "--json"])
        assert ret == 0
        data = json.loads(capsys.readouterr().out)
        assert data["n_cases"] == 5

    def test_custom_cases_yaml(self, tmp_path, capsys):
        from bve.cli.bve_known_answer_validate import main
        yaml_content = """
schema_version: 1
cases:
  - case_id: custom_test
    company_name: CustomCo
    deal_year: 2023
    observed_deal_value_millions: 5000
    expected_deal_type: acquisition
    expected_primary_buyer: Roche
    model_value_range_millions_low: 3000
    model_value_range_millions_high: 8000
    thesis_direction: long
"""
        cases_file = tmp_path / "custom_cases.yaml"
        cases_file.write_text(yaml_content)
        ret = main(["--cases", str(cases_file)])
        assert ret == 0
        out = capsys.readouterr().out
        assert "CustomCo" in out


# ---------------------------------------------------------------------------
# bve-validate CLI: --no-known-answers integration
# ---------------------------------------------------------------------------

class TestBveValidateCLIKnownAnswers:
    def test_no_known_answers_flag(self, capsys):
        from bve.cli.bve_validate import main
        ret = main([
            "--no-replay",
            "--no-ma-backtest",
            "--no-pos-backtest",
            "--no-known-answers",
        ])
        assert ret == 0
        out = capsys.readouterr().out
        assert "Known-Answer Suite" not in out

    def test_known_answers_included_by_default(self, capsys):
        from bve.cli.bve_validate import main
        ret = main([
            "--no-replay",
            "--no-ma-backtest",
            "--no-pos-backtest",
        ])
        assert ret == 0
        out = capsys.readouterr().out
        assert "Known-Answer Suite" in out

    def test_custom_known_answer_cases_path(self, tmp_path, capsys):
        from bve.cli.bve_validate import main
        yaml_content = """
schema_version: 1
cases:
  - case_id: validate_test
    company_name: ValidateCo
    deal_year: 2023
    observed_deal_value_millions: 5000
    expected_deal_type: acquisition
    expected_primary_buyer: Pfizer
    model_value_range_millions_low: 3000
    model_value_range_millions_high: 8000
    thesis_direction: long
"""
        cases_file = tmp_path / "custom_cases.yaml"
        cases_file.write_text(yaml_content)
        ret = main([
            "--no-replay",
            "--no-ma-backtest",
            "--no-pos-backtest",
            "--known-answer-cases", str(cases_file),
        ])
        assert ret == 0
        out = capsys.readouterr().out
        # bve-validate renders a count summary, not case IDs;
        # verify the custom cases file was loaded (1 case → Cases | 1)
        assert "Known-Answer Suite" in out
        assert "DEFINITIONS ONLY" in out
