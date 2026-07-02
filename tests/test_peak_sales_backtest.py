import pytest

from bve.analysis.peak_sales_backtest import (
    DEFAULT_PEAK_SALES_BACKTEST_CSV,
    PeakSalesCase,
    load_peak_sales_cases,
    print_peak_sales_report,
    run_peak_sales_backtest,
)


def test_peak_sales_dataset_loads_seed_cases():
    cases = load_peak_sales_cases(DEFAULT_PEAK_SALES_BACKTEST_CSV)

    assert len(cases) == 2
    assert {c.program_id for c in cases} == {
        "vertex_ivacaftor_g551d_2010",
        "incyte_ruxolitinib_mf_2010",
    }
    assert all(c.predicted_peak_sales_millions > 0 for c in cases)
    assert all(c.realized_peak_sales_millions > 0 for c in cases)
    assert all(c.source for c in cases)


def test_peak_sales_backtest_reports_error_metrics():
    cases = [
        PeakSalesCase(
            program_id="a",
            drug="A",
            company="A Co",
            indication="Test",
            therapeutic_area="oncology",
            prediction_year=2010,
            predicted_peak_sales_millions=100.0,
            realized_peak_sales_millions=200.0,
            realized_peak_sales_year=2015,
        ),
        PeakSalesCase(
            program_id="b",
            drug="B",
            company="B Co",
            indication="Test",
            therapeutic_area="oncology",
            prediction_year=2010,
            predicted_peak_sales_millions=300.0,
            realized_peak_sales_millions=200.0,
            realized_peak_sales_year=2015,
        ),
    ]

    report = run_peak_sales_backtest(cases)

    assert report.n_total == 2
    assert report.mean_error_millions == pytest.approx(0.0)
    assert report.mae_millions == pytest.approx(100.0)
    assert report.rmse_millions == pytest.approx(100.0)
    assert report.mean_abs_pct_error == pytest.approx(0.5)
    assert report.within_50pct == pytest.approx(1.0)
    assert report.within_2x == pytest.approx(1.0)
    assert report.is_low_n is True


def test_peak_sales_report_surfaces_low_n_warning():
    report = run_peak_sales_backtest(csv_path=DEFAULT_PEAK_SALES_BACKTEST_CSV)
    rendered = print_peak_sales_report(report)

    assert "BVE Peak-Sales Backtest Report" in rendered
    assert "LOW-N WARNING" in rendered
    assert "measurement only" in rendered
    assert "vertex_ivacaftor_g551d_2010" in rendered


def test_peak_sales_backtest_rejects_empty_cases():
    with pytest.raises(ValueError, match="No peak-sales cases"):
        run_peak_sales_backtest([])
