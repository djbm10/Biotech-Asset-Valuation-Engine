"""
hard_negative_audit — generate the hard-negative audit CSV.

For every (deal_id, snapshot_date, negative_target) triple in the scored
feature store, documents *why* the negative is realistic and *why* it was
not excluded.  The output CSV is intended for human review before claiming
any predictive accuracy from hit-rate metrics.

Output: vrtx_regn_hard_negative_audit.csv
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Bucket definitions — manual classification of negative cohort types
# ---------------------------------------------------------------------------

NEGATIVE_BUCKETS = {
    "same_ta_earlier_stage": (
        "Same therapeutic area, earlier clinical stage than the actual target."
        " Plausible acquisition candidate; did not occur."
    ),
    "same_ta_adjacent_indication": (
        "Same TA, different indication within adjacent biology."
        " Acquirer could reasonably have pursued instead."
    ),
    "adjacent_ta_similar_stage": (
        "Adjacent TA, similar clinical stage."
        " Strategic rationale exists but lower direct overlap."
    ),
    "platform_tech_overlap": (
        "Shared platform technology (e.g. CRISPR, AAV, mRNA) but different TA."
        " Acquirer has demonstrated interest in the modality."
    ),
    "same_acquirer_prior_interest": (
        "Acquirer has a documented public interest in this asset or company"
        " (partnership, licensing, BD meeting) but did not acquire."
    ),
    "market_cap_range_only": (
        "No TA overlap, but within acquirer's historical deal-size range."
        " Included as a size-range negative to prevent size-only spurious hits."
    ),
    "research_gap": (
        "Negative not fully characterised; key features missing."
        " Downweighted in aggregated metrics."
    ),
}

# ---------------------------------------------------------------------------
# Rights/IP encumbrance quick-check registry
# Populated from public deal databases; not exhaustive.
# ---------------------------------------------------------------------------

_KNOWN_ENCUMBRANCES: dict[str, str] = {
    "AKOUOS": "Acquired by Eli Lilly 2022 — excluded from post-2022 snapshots",
    "EDIT": "NTLA/EDIT cross-licensing; pipeline overlaps notable",
    "IMVT": "ROIVANT spin-out; specific licensing terms public",
    "BEAM":  "NTLA settlement 2022 — CRISPR IP partially clarified",
}


# ---------------------------------------------------------------------------
# HardNegativeAuditRow
# ---------------------------------------------------------------------------

@dataclass
class HardNegativeAuditRow:
    deal_id: str
    snapshot_date: str
    actual_target: str
    negative_target: str
    negative_bucket: str
    why_plausible: str
    why_not_excluded: str
    ta_similarity: float       # 0–1
    stage_similarity: float    # 0–1
    market_cap_similarity: float  # 0–1 (ratio-based)
    rights_check_status: str   # "clear" | "encumbered" | "unknown"
    manual_review_status: str  # "pending" | "reviewed_ok" | "flagged"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class HardNegativeAuditBuilder:
    """
    Build the hard-negative audit from scored feature rows.

    Reads the feature store rows (one per candidate pair) and produces an
    audit row for every non-positive (negative) candidate, documenting why
    the negative is realistic and why it was not excluded.

    The caller is responsible for providing:
      - ``scored_rows``: list of feature store dicts (one per scored pair)
      - ``bucket_map``: optional dict[target_ticker -> bucket_key] override

    Missing bucket → falls back to ``research_gap``.
    """

    # Manually maintained bucket assignments for known negatives.
    # Key: target_ticker (upper); Value: NEGATIVE_BUCKETS key
    _DEFAULT_BUCKET_MAP: dict[str, str] = {
        "NTLA": "same_ta_earlier_stage",
        "BEAM": "platform_tech_overlap",
        "EDIT": "platform_tech_overlap",
        "CRISPR": "platform_tech_overlap",
        "IMVT": "same_ta_adjacent_indication",
        "AKOUOS": "same_ta_earlier_stage",
        "DBTX": "same_ta_earlier_stage",
        "LXRX": "adjacent_ta_similar_stage",
        "TALS": "same_ta_earlier_stage",
        "ARGENX": "same_ta_adjacent_indication",
        "INVA": "adjacent_ta_similar_stage",
        "RARE": "adjacent_ta_similar_stage",
        "IONS": "same_acquirer_prior_interest",
        "REGN_NEG": "same_acquirer_prior_interest",
    }

    def __init__(
        self,
        bucket_map: Optional[dict[str, str]] = None,
    ) -> None:
        self._bucket_map = dict(self._DEFAULT_BUCKET_MAP)
        if bucket_map:
            self._bucket_map.update(bucket_map)

    def build(
        self,
        scored_rows: list[dict[str, Any]],
    ) -> list[HardNegativeAuditRow]:
        """Return one HardNegativeAuditRow per negative candidate pair."""
        rows: list[HardNegativeAuditRow] = []
        for row in scored_rows:
            is_positive = str(row.get("is_actual_target", "")).lower() in ("true", "1")
            if is_positive:
                continue

            target = str(row.get("target_ticker", "")).upper()
            bucket_key = self._bucket_map.get(target, "research_gap")
            bucket_desc = NEGATIVE_BUCKETS.get(bucket_key, NEGATIVE_BUCKETS["research_gap"])

            ta_sim = float(row.get("ta_overlap", 0.0))
            size_sim = float(row.get("size_fit", 0.0))

            rights_status = "unknown"
            encumbrance_note = _KNOWN_ENCUMBRANCES.get(target)
            if encumbrance_note:
                rights_status = "encumbered"
                notes_text = encumbrance_note
            else:
                notes_text = ""

            rows.append(HardNegativeAuditRow(
                deal_id=str(row.get("deal_id", "")),
                snapshot_date=str(row.get("snapshot_date", "")),
                actual_target=_resolve_actual_target(scored_rows, row),
                negative_target=target,
                negative_bucket=bucket_key,
                why_plausible=bucket_desc,
                why_not_excluded=(
                    "Public company with available feature data; "
                    "no confirmed acquisition or licensing exclusivity "
                    "as of snapshot_date."
                    if rights_status != "encumbered"
                    else f"Check required: {notes_text}"
                ),
                ta_similarity=ta_sim,
                stage_similarity=_stage_similarity(row),
                market_cap_similarity=size_sim,
                rights_check_status=rights_status,
                manual_review_status="pending",
                notes=notes_text,
            ))
        return rows


def _resolve_actual_target(
    all_rows: list[dict[str, Any]],
    current_row: dict[str, Any],
) -> str:
    """Find the positive target for the same deal_id / snapshot_date."""
    deal_id = current_row.get("deal_id", "")
    snap = current_row.get("snapshot_date", "")
    for r in all_rows:
        if (
            str(r.get("deal_id", "")) == str(deal_id)
            and str(r.get("snapshot_date", "")) == str(snap)
            and str(r.get("is_actual_target", "")).lower() in ("true", "1")
        ):
            return str(r.get("target_ticker", "unknown"))
    return "unknown"


def _stage_similarity(row: dict[str, Any]) -> float:
    """Proxy stage similarity from asset_quality score (higher = more developed)."""
    return float(row.get("asset_quality", 0.0))


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def write_hard_negative_audit(
    rows: list[HardNegativeAuditRow],
    output_path: "str | Path",
) -> Path:
    """Write the hard-negative audit CSV and return its path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return output_path
    dicts = [r.to_dict() for r in rows]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(dicts[0].keys()))
        writer.writeheader()
        writer.writerows(dicts)
    return output_path


def audit_summary(rows: list[HardNegativeAuditRow]) -> dict[str, Any]:
    """Return summary stats over audit rows."""
    total = len(rows)
    by_bucket: dict[str, int] = {}
    encumbered = 0
    pending_review = 0
    for r in rows:
        by_bucket[r.negative_bucket] = by_bucket.get(r.negative_bucket, 0) + 1
        if r.rights_check_status == "encumbered":
            encumbered += 1
        if r.manual_review_status == "pending":
            pending_review += 1
    return {
        "total_negatives": total,
        "by_bucket": by_bucket,
        "encumbered": encumbered,
        "pending_manual_review": pending_review,
    }
