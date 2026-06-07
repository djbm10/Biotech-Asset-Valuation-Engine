"""
Discovers public biotech/pharma companies from SEC EDGAR.

Biotech SIC codes targeted:
  2836 — Pharmaceutical preparations
  2835 — In vitro & in vivo diagnostic substances
  2833 — Pharmaceutical preparations (medicinal chemicals)
  8731 — Commercial physical & biological research

Approach:
  1. Fetch company_tickers_exchange.json  → all public companies (Nasdaq/NYSE/CBOE)
  2. Filter to Nasdaq / NYSE
  3. Per-company: fetch submissions/{CIK}.json to resolve SIC (cached in SQLite)
  4. Filter to BIOTECH_SIC_CODES
  5. Write YAML output

Rate-limiting: token-bucket at ≤8 req/s to stay well under EDGAR's 10 req/s policy.
Caching: SIC resolutions cached in SQLite — SIC codes don't change for active filers,
         so subsequent runs read the cache and only hit the API for new companies.

First run: ~5–15 min depending on cache warmth.
Subsequent runs: < 30 sec.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"

BIOTECH_SIC_CODES: frozenset[int] = frozenset({2836, 2835, 2833, 8731})
TARGET_EXCHANGES: frozenset[str] = frozenset({"Nasdaq", "NYSE"})

_HEADERS = {
    "User-Agent": "BVE Analytics research@bve.local",
    "Accept-Encoding": "gzip, deflate",
}

_DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "research" / "universe" / ".sic_cache.db"
)
_DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parents[3] / "research" / "universe" / "biotech_tickers.yaml"
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class UniverseEntry:
    ticker: str
    cik: str
    company_name: str
    sic: int
    sic_description: str
    exchange: str
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Targetability fields — populated by apply_targetability_filter()
    target_type: str = "unknown"
    market_cap_bucket: str = "micro"
    include_in_ma_screen: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Rate limiter (token bucket)
# ---------------------------------------------------------------------------


class _TokenBucket:
    """Thread-safe token-bucket rate limiter."""

    def __init__(self, rate: float) -> None:
        self._rate = rate
        self._tokens = rate
        self._last_check = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_check
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_check = now
            if self._tokens < 1.0:
                sleep_time = (1.0 - self._tokens) / self._rate
                time.sleep(sleep_time)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# ---------------------------------------------------------------------------
# SIC cache (SQLite)
# ---------------------------------------------------------------------------


class _SicCache:
    """Persistent SQLite cache mapping CIK → (sic, sic_description)."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sic_cache "
            "(cik TEXT PRIMARY KEY, sic INTEGER, sic_description TEXT, cached_at TEXT)"
        )
        self._conn.commit()

    def get(self, cik: str) -> tuple[int, str] | None:
        row = self._conn.execute(
            "SELECT sic, sic_description FROM sic_cache WHERE cik = ?", (cik,)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def put(self, cik: str, sic: int, sic_description: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sic_cache (cik, sic, sic_description, cached_at) "
            "VALUES (?, ?, ?, ?)",
            (cik, sic, sic_description, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_json(url: str, limiter: _TokenBucket, retries: int = 3) -> dict | list:
    for attempt in range(retries):
        limiter.acquire()
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                return {}
            time.sleep(2**attempt)
    return {}


def _fetch_all_exchange_tickers(
    limiter: _TokenBucket,
) -> list[tuple[str, str, str, str]]:
    """
    Return list of (ticker, cik_padded, exchange, name) for Nasdaq/NYSE companies.

    The exchange JSON uses a data/fields format:
      {"fields": ["cik", "name", "ticker", "exchange"], "data": [[...], ...]}
    """
    data = _get_json(COMPANY_TICKERS_EXCHANGE_URL, limiter)
    if not isinstance(data, dict):
        return []

    fields: list[str] = data.get("fields", [])
    rows: list[list] = data.get("data", [])

    try:
        cik_idx = fields.index("cik")
        ticker_idx = fields.index("ticker")
        exchange_idx = fields.index("exchange")
        name_idx = fields.index("name")
    except ValueError:
        return []

    result: list[tuple[str, str, str, str]] = []
    for row in rows:
        if not row or len(row) <= max(cik_idx, ticker_idx, exchange_idx, name_idx):
            continue
        exchange = str(row[exchange_idx]) if row[exchange_idx] else ""
        if exchange not in TARGET_EXCHANGES:
            continue
        cik_padded = str(row[cik_idx]).zfill(10)
        ticker = str(row[ticker_idx]).upper()
        name = str(row[name_idx])
        result.append((ticker, cik_padded, exchange, name))

    return result


def _fetch_sic(cik_padded: str, limiter: _TokenBucket) -> tuple[int, str]:
    """Fetch SIC code for one company from EDGAR submissions endpoint."""
    url = f"{SUBMISSIONS_BASE}/CIK{cik_padded}.json"
    data = _get_json(url, limiter)
    if not isinstance(data, dict):
        return 0, ""
    sic_raw = data.get("sic", 0)
    sic_desc = data.get("sicDescription", "")
    return (int(sic_raw) if sic_raw else 0), str(sic_desc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_biotech_universe(
    cache_path: Path | None = None,
    output_path: Path | None = None,
    requests_per_second: float = 8.0,
    verbose: bool = False,
) -> list[UniverseEntry]:
    """
    Scan SEC EDGAR for all public biotech/pharma companies on Nasdaq/NYSE.

    Parameters
    ----------
    cache_path:
        SQLite cache file for SIC codes.
        Defaults to research/universe/.sic_cache.db.
    output_path:
        YAML output file. Pass None to skip writing.
        Defaults to research/universe/biotech_tickers.yaml.
    requests_per_second:
        Rate limit for EDGAR requests. Must stay ≤ 10 per EDGAR policy.
    verbose:
        Print progress to stdout.

    Returns
    -------
    list[UniverseEntry]
    """
    if requests_per_second > 10:
        raise ValueError("EDGAR policy limits requests to ≤10/s.")

    resolved_cache = cache_path or _DEFAULT_CACHE_PATH
    resolved_output = output_path if output_path is not None else _DEFAULT_OUTPUT_PATH

    cache = _SicCache(resolved_cache)
    limiter = _TokenBucket(requests_per_second)

    if verbose:
        print("Fetching company tickers from SEC EDGAR...", flush=True)

    all_companies = _fetch_all_exchange_tickers(limiter)

    if verbose:
        print(f"  {len(all_companies)} companies on Nasdaq/NYSE.", flush=True)
        print("Resolving SIC codes (cached where possible)...", flush=True)

    entries: list[UniverseEntry] = []
    new_api_calls = 0

    for i, (ticker, cik_padded, exchange, name) in enumerate(all_companies):
        cached = cache.get(cik_padded)
        if cached is not None:
            sic, sic_desc = cached
        else:
            sic, sic_desc = _fetch_sic(cik_padded, limiter)
            cache.put(cik_padded, sic, sic_desc)
            new_api_calls += 1

        if sic in BIOTECH_SIC_CODES:
            entries.append(
                UniverseEntry(
                    ticker=ticker,
                    cik=cik_padded,
                    company_name=name,
                    sic=sic,
                    sic_description=sic_desc,
                    exchange=exchange,
                )
            )

        if verbose and (i + 1) % 500 == 0:
            pct = (i + 1) / len(all_companies) * 100
            print(
                f"  [{pct:5.1f}%] {i+1}/{len(all_companies)} checked — "
                f"{len(entries)} biotech found — {new_api_calls} API calls",
                flush=True,
            )

    cache.close()

    if verbose:
        print(f"\nTotal biotech companies: {len(entries)}", flush=True)

    if resolved_output is not None:
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        with resolved_output.open("w") as fh:
            yaml.safe_dump(
                {
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                    "n_companies": len(entries),
                    "sic_codes": sorted(BIOTECH_SIC_CODES),
                    "exchanges": sorted(TARGET_EXCHANGES),
                    "companies": [e.to_dict() for e in entries],
                },
                fh,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        if verbose:
            print(f"Written to {resolved_output}", flush=True)

    return entries


# ---------------------------------------------------------------------------
# Targetability filter — second-pass classification
# ---------------------------------------------------------------------------

# Target type labels
TARGET_TYPE_DRUG_DEVELOPER = "drug_developer"    # pure-play drug developer
TARGET_TYPE_PLATFORM = "platform"                 # technology platform with pipeline
TARGET_TYPE_COMMERCIAL = "commercial"             # approved product + pipeline
TARGET_TYPE_DIAGNOSTICS = "diagnostics"           # diagnostics / testing focus
TARGET_TYPE_TOOLS_SERVICES = "tools_services"     # CRO / tools / research services
TARGET_TYPE_UNKNOWN = "unknown"

# Market cap buckets (USD millions)
MARKET_CAP_MICRO = "micro"     # < 300
MARKET_CAP_SMALL = "small"     # 300 – 2,000
MARKET_CAP_MID = "mid"         # 2,000 – 10,000
MARKET_CAP_LARGE = "large"     # > 10,000

# Lead asset stage labels
LEAD_STAGE_PRECLINICAL = "preclinical"
LEAD_STAGE_PHASE1 = "phase1"
LEAD_STAGE_PHASE2 = "phase2"
LEAD_STAGE_PHASE3 = "phase3"
LEAD_STAGE_COMMERCIAL = "commercial"
LEAD_STAGE_UNKNOWN = "unknown"

# SIC codes that are primarily diagnostics (not drug developers)
_DIAGNOSTICS_SIC: frozenset[int] = frozenset({2835})

# SIC codes that are unambiguously drug developers
_PHARMA_SIC: frozenset[int] = frozenset({2836, 2833})

# For SIC 8731 (commercial research), use name keywords to classify
_DRUG_DEVELOPER_KEYWORDS: tuple[str, ...] = (
    "therapeutics", "pharma", "biopharma", "biopharmaceuticals",
    "oncology", "biosciences", "biotech", "medicines", "drugs",
    "clinical", "gene therapy", "cell therapy",
)

_TOOLS_SERVICES_KEYWORDS: tuple[str, ...] = (
    "diagnostics", "genomics", "sequencing", "analytics", "solutions",
    "systems", "technologies", "instruments", "services", "laboratory",
    # More specific CRO/CDMO terms — "research" alone is too broad
    "cro", "cdmo", "contract research", "contract manufacturing",
)


def _infer_target_type(sic: int, company_name: str) -> str:
    """
    Infer target_type from SIC code and company name.

    SIC 2836 / 2833 → drug_developer (pharmaceutical)
    SIC 2835        → diagnostics
    SIC 8731        → keyword match on name; else unknown
    """
    name_lower = company_name.lower()

    if sic in _DIAGNOSTICS_SIC:
        return TARGET_TYPE_DIAGNOSTICS

    if sic in _PHARMA_SIC:
        # Still check for tools/services companies miscoded under pharma SIC
        if any(kw in name_lower for kw in _TOOLS_SERVICES_KEYWORDS):
            return TARGET_TYPE_TOOLS_SERVICES
        return TARGET_TYPE_DRUG_DEVELOPER

    if sic == 8731:
        if any(kw in name_lower for kw in _TOOLS_SERVICES_KEYWORDS):
            return TARGET_TYPE_TOOLS_SERVICES
        if any(kw in name_lower for kw in _DRUG_DEVELOPER_KEYWORDS):
            return TARGET_TYPE_DRUG_DEVELOPER
        return TARGET_TYPE_UNKNOWN

    return TARGET_TYPE_UNKNOWN


def _market_cap_bucket(market_cap_millions: float | None) -> str:
    if market_cap_millions is None:
        return MARKET_CAP_MICRO  # conservative default for unknown
    if market_cap_millions < 300:
        return MARKET_CAP_MICRO
    if market_cap_millions < 2_000:
        return MARKET_CAP_SMALL
    if market_cap_millions < 10_000:
        return MARKET_CAP_MID
    return MARKET_CAP_LARGE


def apply_targetability_filter(
    entries: list["UniverseEntry"],
    market_cap_lookup: dict[str, float] | None = None,
) -> list["UniverseEntry"]:
    """
    Enrich UniverseEntry objects with targetability fields and return only
    entries that belong in an M&A screen.

    Parameters
    ----------
    entries:
        Raw SIC-filtered universe from scan_biotech_universe().
    market_cap_lookup:
        Optional dict of ticker → market_cap_millions. If not provided,
        market_cap_bucket is set to MARKET_CAP_MICRO (most conservative).

    Returns
    -------
    list[UniverseEntry] where include_in_ma_screen is True.

    Targetability rules
    -------------------
    include_in_ma_screen = True when:
      - target_type in {drug_developer, platform, commercial}
      - NOT diagnostics-only or tools/services
      - market_cap_bucket != large (> $10B — too expensive for most acquirers
        or would be a transformative merger, not bolt-on)
    """
    mcap = market_cap_lookup or {}
    screened: list[UniverseEntry] = []

    for entry in entries:
        target_type = _infer_target_type(entry.sic, entry.company_name)
        mcap_bucket = _market_cap_bucket(mcap.get(entry.ticker))

        # Targetability gate
        include = (
            target_type in {TARGET_TYPE_DRUG_DEVELOPER, TARGET_TYPE_PLATFORM, TARGET_TYPE_COMMERCIAL}
            and mcap_bucket != MARKET_CAP_LARGE
        )

        # Write enriched fields back to entry
        entry.target_type = target_type
        entry.market_cap_bucket = mcap_bucket
        entry.include_in_ma_screen = include

        if include:
            screened.append(entry)

    return screened


def load_universe_yaml(path: Path | None = None) -> list[UniverseEntry]:
    """Load a previously-scanned universe YAML into UniverseEntry objects."""
    yaml_path = path or _DEFAULT_OUTPUT_PATH
    if not yaml_path.exists():
        return []
    with yaml_path.open() as fh:
        raw = yaml.safe_load(fh)
    companies: list[dict] = raw.get("companies", []) if isinstance(raw, dict) else []
    return [
        UniverseEntry(
            ticker=c["ticker"],
            cik=c["cik"],
            company_name=c["company_name"],
            sic=c["sic"],
            sic_description=c["sic_description"],
            exchange=c["exchange"],
            scanned_at=c.get("scanned_at", ""),
        )
        for c in companies
    ]
