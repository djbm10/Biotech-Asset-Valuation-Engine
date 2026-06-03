from __future__ import annotations

from bve.ui.dashboard.components.portfolio_dashboard import render_portfolio_dashboard


class _FakeColumn:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, object]] = []

    def metric(self, label: str, value: object) -> None:
        self.metrics.append((label, value))


class _FakeStreamlit:
    def __init__(self) -> None:
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.frames: list[object] = []
        self._columns = [_FakeColumn() for _ in range(4)]

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def columns(self, n: int) -> list[_FakeColumn]:
        assert n == 4
        return self._columns

    def dataframe(self, data, **kwargs) -> None:  # noqa: ANN001
        self.frames.append(data)


def test_portfolio_dashboard_renders_company_decisions_table() -> None:
    st = _FakeStreamlit()
    payload = {
        "watchlist_summary": {
            "assets": [
                {"asset_id": "asset-a", "status": "success", "valuation_diffs_persisted": 1, "memo_generated": True}
            ]
        },
        "metrics_dashboard": {
            "top_opportunities_source_mode": "company_sotp_snapshot",
            "top_opportunities_reference_date": "2026-03-10",
            "top_opportunities": [
                {
                    "rank": 1,
                    "ticker": "AAA",
                    "company_name": "AAA Bio",
                    "ranked_sotp_discount": 1.55,
                    "action_policy": "buy",
                    "modeled_asset_coverage_pct": 0.82,
                    "sotp_equity_value_millions": 840.0,
                    "enterprise_value_millions": 420.0,
                    "balance_sheet_snapshot_date": "2026-02-28",
                }
            ],
        },
    }

    render_portfolio_dashboard(st, payload)

    assert "Top Company Decisions" in st.subheaders
    assert any("company_sotp_snapshot" in caption for caption in st.captions)
    assert len(st.frames) == 2
    assert st.frames[1][0]["ticker"] == "AAA"
    assert st.frames[1][0]["action_policy"] == "buy"
