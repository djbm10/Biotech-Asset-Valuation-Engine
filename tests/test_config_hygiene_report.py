from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bve.analysis.config_hygiene_report import (
    ConfigHygieneReport,
    LotUptakeFinding,
    PriceBasisFinding,
    _audit_lot_segments,
    _audit_price_basis,
    _is_suspicious_price,
    audit_configs,
)


# ---------------------------------------------------------------------------
# _is_suspicious_price
# ---------------------------------------------------------------------------


def test_is_suspicious_price_round_large_price_is_flagged():
    assert _is_suspicious_price(100_000.0) is True
    assert _is_suspicious_price(250_000.0) is True


def test_is_suspicious_price_non_round_large_price_is_not_flagged():
    assert _is_suspicious_price(102_500.0) is False
    assert _is_suspicious_price(87_654.0) is False


def test_is_suspicious_price_below_threshold_is_not_flagged():
    # Under $50k, not flagged regardless of roundness
    assert _is_suspicious_price(10_000.0) is False
    assert _is_suspicious_price(40_000.0) is False


# ---------------------------------------------------------------------------
# _audit_lot_segments
# ---------------------------------------------------------------------------


def _lot_seg(line: str, use_s_curve=None, years_to_peak=None):
    seg = {"line": line}
    if use_s_curve is not None:
        seg["use_s_curve"] = use_s_curve
    if years_to_peak is not None:
        seg["years_to_peak"] = years_to_peak
    return seg


def test_lot_audit_no_findings_for_non_specialty_ta():
    segs = [_lot_seg("1L", use_s_curve=False)]
    findings = _audit_lot_segments("test.yaml", "asset-1", "primary_care", segs)
    assert findings == []


def test_lot_audit_flags_explicit_false_for_specialty_ta():
    segs = [_lot_seg("1L", use_s_curve=False)]
    findings = _audit_lot_segments("test.yaml", "asset-1", "oncology", segs)
    assert len(findings) == 1
    assert findings[0].explicit_use_s_curve is False
    assert "use_s_curve=False is set explicitly" in findings[0].recommendation


def test_lot_audit_no_finding_when_use_s_curve_true():
    segs = [_lot_seg("1L", use_s_curve=True)]
    findings = _audit_lot_segments("test.yaml", "asset-1", "oncology", segs)
    assert findings == []


def test_lot_audit_flags_missing_for_non_auto_specialty_ta():
    # gene_therapy is specialty but NOT in the auto-S-curve set (oncology/rare_disease/CNS)
    segs = [_lot_seg("1L")]  # use_s_curve not set
    findings = _audit_lot_segments("test.yaml", "asset-1", "gene_therapy", segs)
    assert len(findings) == 1
    assert findings[0].explicit_use_s_curve is None


def test_lot_audit_no_finding_for_auto_s_curve_tas():
    # oncology IS in the auto-S-curve set → MarketModel will activate it automatically
    segs = [_lot_seg("1L")]  # no explicit use_s_curve
    findings = _audit_lot_segments("test.yaml", "asset-1", "oncology", segs)
    assert findings == []


def test_lot_audit_no_finding_when_ta_is_none():
    segs = [_lot_seg("1L", use_s_curve=False)]
    findings = _audit_lot_segments("test.yaml", "asset-1", None, segs)
    assert findings == []


# ---------------------------------------------------------------------------
# _audit_price_basis
# ---------------------------------------------------------------------------


def _make_raw_config(
    price: float | None = None,
    price_basis: str | None = None,
    g2n_rate: float | None = None,
    lot_prices: list[tuple[str, float]] | None = None,
):
    mm: dict = {}
    if price is not None:
        mm["net_price_per_patient_usd"] = price
    if price_basis is not None:
        mm["price_basis"] = price_basis
    if g2n_rate is not None:
        mm["gross_to_net_rate"] = g2n_rate
    if lot_prices:
        mm["lines_of_therapy"] = [
            {"line": line, "net_price_per_patient_usd": p}
            for line, p in lot_prices
        ]
    return {"market_model": mm}


def test_price_audit_flags_round_top_level_price_without_g2n():
    raw = _make_raw_config(price=150_000.0)
    findings = _audit_price_basis("test.yaml", "asset-1", "oncology", raw)
    assert len(findings) == 1
    assert findings[0].price_value_usd == 150_000.0
    assert "WAC" in findings[0].recommendation


def test_price_audit_no_finding_when_price_basis_is_set():
    raw = _make_raw_config(price=150_000.0, price_basis="wac", g2n_rate=0.30)
    findings = _audit_price_basis("test.yaml", "asset-1", "oncology", raw)
    assert findings == []


def test_price_audit_no_finding_when_price_is_not_round():
    raw = _make_raw_config(price=127_500.0)
    findings = _audit_price_basis("test.yaml", "asset-1", "oncology", raw)
    assert findings == []


def test_price_audit_flags_round_lot_segment_price():
    raw = _make_raw_config(lot_prices=[("1L", 200_000.0)])
    findings = _audit_price_basis("test.yaml", "asset-1", "oncology", raw)
    assert len(findings) == 1
    assert "1L" in findings[0].price_field


def test_price_audit_no_finding_for_non_round_lot_segment_price():
    raw = _make_raw_config(lot_prices=[("1L", 157_300.0)])
    findings = _audit_price_basis("test.yaml", "asset-1", "oncology", raw)
    assert findings == []


def test_price_audit_multiple_lot_segments_flagged_independently():
    raw = _make_raw_config(lot_prices=[("1L", 200_000.0), ("2L", 150_000.0)])
    findings = _audit_price_basis("test.yaml", "asset-1", "oncology", raw)
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# audit_configs (integration)
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_audit_configs_empty_dir_returns_zero_findings(tmp_path):
    report = audit_configs(tmp_path)
    assert report.scanned_files == 0
    assert report.total_findings == 0


def test_audit_configs_clean_config_returns_no_findings(tmp_path):
    _write_yaml(
        tmp_path / "clean.yaml",
        {
            "asset_id": "asset-clean",
            "therapeutic_area": "oncology",
            "market_model": {
                "net_price_per_patient_usd": 127_500,  # not round
                "lines_of_therapy": [
                    {"line": "1L", "use_s_curve": True},
                ],
            },
        },
    )
    report = audit_configs(tmp_path)
    assert report.scanned_files == 1
    assert report.total_findings == 0


def test_audit_configs_detects_lot_uptake_issue(tmp_path):
    _write_yaml(
        tmp_path / "problem.yaml",
        {
            "asset_id": "asset-bad",
            "therapeutic_area": "gene_therapy",  # specialty, not auto-S-curve
            "market_model": {
                "lines_of_therapy": [
                    {"line": "1L"},  # no use_s_curve → should be flagged
                ],
            },
        },
    )
    report = audit_configs(tmp_path)
    assert len(report.lot_uptake_findings) == 1


def test_audit_configs_detects_price_basis_issue(tmp_path):
    _write_yaml(
        tmp_path / "pricewac.yaml",
        {
            "asset_id": "asset-wac",
            "market_model": {
                "net_price_per_patient_usd": 200_000,  # round, no price_basis
            },
        },
    )
    report = audit_configs(tmp_path)
    assert len(report.price_basis_findings) == 1


def test_audit_configs_counts_multiple_yaml_files(tmp_path):
    for i in range(3):
        _write_yaml(
            tmp_path / f"asset_{i}.yaml",
            {"asset_id": f"asset-{i}", "market_model": {}},
        )
    report = audit_configs(tmp_path)
    assert report.scanned_files == 3


def test_audit_configs_report_render_contains_summary_header(tmp_path):
    report = audit_configs(tmp_path)
    rendered = report.render()
    assert "Config Hygiene Report" in rendered
    assert "Scanned files:" in rendered


def test_audit_configs_does_not_modify_files(tmp_path):
    yaml_path = tmp_path / "check.yaml"
    original = {"asset_id": "asset-x", "market_model": {"net_price_per_patient_usd": 100_000}}
    _write_yaml(yaml_path, original)
    before = yaml_path.read_text()

    audit_configs(tmp_path)

    assert yaml_path.read_text() == before


def test_audit_configs_skips_non_dict_yaml(tmp_path):
    (tmp_path / "list.yaml").write_text("- foo\n- bar\n", encoding="utf-8")
    report = audit_configs(tmp_path)
    assert report.scanned_files == 0  # list root → skipped


def test_config_hygiene_report_total_findings_sums_both_types():
    report = ConfigHygieneReport(
        scanned_files=2,
        lot_uptake_findings=[
            LotUptakeFinding(
                config_file="a.yaml",
                asset_id="x",
                therapeutic_area="oncology",
                lot_line="1L",
                explicit_use_s_curve=False,
                years_to_peak=None,
                recommendation="review",
            )
        ],
        price_basis_findings=[
            PriceBasisFinding(
                config_file="b.yaml",
                asset_id="y",
                therapeutic_area=None,
                price_field="net_price_per_patient_usd",
                price_value_usd=100_000.0,
                price_basis_set=None,
                gross_to_net_rate_set=None,
                recommendation="check",
            )
        ],
    )
    assert report.total_findings == 2
