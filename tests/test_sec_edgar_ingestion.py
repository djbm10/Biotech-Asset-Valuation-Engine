from __future__ import annotations

from bve.ingestion import sec_edgar


def test_get_cik_uses_company_tickers_mapping(monkeypatch) -> None:
    sec_edgar._TICKER_TO_CIK_CACHE = None
    sec_edgar._COMPANY_NAME_TO_CIK_CACHE = None

    def fake_get(url: str, params: dict | None = None, retries: int = 3) -> dict:  # noqa: ARG001
        assert url == sec_edgar.COMPANY_TICKERS_URL
        return {
            "0": {"ticker": "VRTX", "cik_str": 875320, "title": "Vertex Pharmaceuticals"},
            "1": {"ticker": "REGN", "cik_str": 872589, "title": "Regeneron"},
        }

    monkeypatch.setattr(sec_edgar, "_get", fake_get)

    assert sec_edgar.get_cik("VRTX") == "0000875320"


def test_get_cik_falls_back_to_search_index(monkeypatch) -> None:
    sec_edgar._TICKER_TO_CIK_CACHE = None
    sec_edgar._COMPANY_NAME_TO_CIK_CACHE = None

    def fake_get(url: str, params: dict | None = None, retries: int = 3) -> dict:  # noqa: ARG001
        if url == sec_edgar.COMPANY_TICKERS_URL:
            return {}
        assert url == sec_edgar.EFTS_BASE
        return {
            "hits": {
                "hits": [
                    {"_source": {"ciks": ["1336920"]}},
                ]
            }
        }

    monkeypatch.setattr(sec_edgar, "_get", fake_get)

    assert sec_edgar.get_cik("REGN") == "0001336920"


def test_get_cik_prefers_company_name_match_when_ticker_search_is_ambiguous(monkeypatch) -> None:
    sec_edgar._TICKER_TO_CIK_CACHE = None
    sec_edgar._COMPANY_NAME_TO_CIK_CACHE = None

    def fake_get(url: str, params: dict | None = None, retries: int = 3) -> dict:  # noqa: ARG001
        if url == sec_edgar.COMPANY_TICKERS_URL:
            return {}
        assert url == sec_edgar.EFTS_BASE
        query = (params or {}).get("q")
        if query == '"Avidity Biosciences"':
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "display_names": [
                                    "Atrium Therapeutics, Inc.  (CIK 0002093101)",
                                    "Avidity Biosciences, Inc.  (RNA)  (CIK 0001599901)",
                                ],
                                "ciks": ["2093101", "1599901"],
                            }
                        }
                    ]
                }
            }
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(sec_edgar, "_get", fake_get)

    assert (
        sec_edgar.get_cik("RNA", company_name="Avidity Biosciences")
        == "0001599901"
    )
