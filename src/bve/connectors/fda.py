"""
FDA announcements source connector.

Wraps ``bve.ingestion.fda`` (openFDA drug@drugsfda endpoint) and normalizes
NDA/BLA approval and action records into ``RawDocument`` objects.

Query logic
-----------
Searches by ``entity_hints.drug_name`` using the openFDA CDER drug approval
database (NDA/BLA submissions, review history, approval actions).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FDAConnector:
    """
    Fetches FDA drug approval and action records from openFDA.

    Parameters
    ----------
    include_supplements:
        When ``True``, include supplemental applications (sNDA/sBLA).
        Default: ``True``.
    """

    def __init__(self, include_supplements: bool = True) -> None:
        self._include_supplements = include_supplements

    @property
    def source_type(self) -> str:
        return "fda_website"

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> FetchResult:
        now = _utcnow()
        docs: list[RawDocument] = []
        errors: list[str]       = []

        if not entity_hints.drug_name:
            return FetchResult(
                source=self.source_type,
                fetch_errors=["entity_hints.drug_name is required for FDAConnector"],
            )

        try:
            from bve.ingestion.fda import search_approvals
        except ImportError as exc:
            return FetchResult(
                source=self.source_type,
                fetch_errors=[f"Import error: {exc}"],
            )

        try:
            results = search_approvals(entity_hints.drug_name, limit=min(limit, 20))
            for raw in results:
                try:
                    doc = self._to_document(raw, entity_hints, now)
                    if doc is None:
                        continue
                    if since and doc.published_at and doc.published_at < since:
                        continue
                    docs.append(doc)
                    if len(docs) >= limit:
                        break
                except Exception as exc:
                    errors.append(f"to_document: {exc}")
        except Exception as exc:
            errors.append(f"search_approvals({entity_hints.drug_name!r}): {exc}")

        return FetchResult(
            documents=docs,
            fetch_errors=errors,
            source=self.source_type,
            fetched_at=now,
        )

    def _to_document(
        self,
        raw: dict,
        entity_hints: EntityHints,
        retrieved_at: datetime,
    ) -> Optional[RawDocument]:
        try:
            products = raw.get("products", [{}])
            product  = products[0] if products else {}
            brand_name   = product.get("brand_name", "")
            generic_name = product.get("generic_name", "")
            drug_name    = brand_name or generic_name or entity_hints.drug_name or "Unknown"

            application_number = raw.get("application_number", "")
            sponsor_name       = raw.get("sponsor_name", "")
            submissions        = raw.get("submissions", [])

            if not submissions:
                return None

            # Build text from submission history (most recent first)
            sub_lines: list[str] = []
            latest_date: Optional[str] = None

            for i, sub in enumerate(submissions[:10]):
                sub_type   = sub.get("submission_type", "")
                sub_status = sub.get("submission_status", "")
                sub_date   = sub.get("submission_status_date", "")
                review_pri = sub.get("review_priority", "")
                sub_class  = sub.get("submission_class_code_description", "")
                sub_lines.append(
                    f"  [{i+1}] {sub_type} — {sub_status} — {sub_date}"
                    + (f" ({review_pri})" if review_pri else "")
                    + (f" [{sub_class}]" if sub_class else "")
                )
                if i == 0:
                    latest_date = sub_date

            all_brand_names = list({p.get("brand_name", "") for p in products if p.get("brand_name")})

            text_parts = [
                "FDA Drug Application Record",
                f"Application Number: {application_number}",
                f"Sponsor: {sponsor_name}",
                f"Drug: {drug_name}",
                f"Generic Name: {generic_name}" if generic_name != drug_name else "",
                f"Brand Names: {', '.join(all_brand_names)}",
                "",
                "Submission History:",
                *sub_lines,
            ]
            raw_text = "\n".join(t for t in text_parts if t is not None)

            title = (
                f"FDA {submissions[0].get('submission_type', 'Submission')} — "
                f"{drug_name} ({application_number})"
            )

            # Parse published_at from the latest submission date
            published_at: Optional[datetime] = None
            if latest_date:
                for fmt in ("%Y%m%d", "%Y-%m-%d"):
                    try:
                        published_at = datetime.strptime(latest_date[:8] if fmt == "%Y%m%d" else latest_date, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

            app_no_digits = application_number.replace("NDA", "").replace("BLA", "").replace("ANDA", "").strip()
            source_url = (
                f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
                f"?event=overview.process&ApplNo={app_no_digits}"
                if app_no_digits else None
            )

            hints = EntityHints(
                asset_id=entity_hints.asset_id,
                company_id=entity_hints.company_id,
                drug_name=drug_name,
                indication=entity_hints.indication,
                ticker=entity_hints.ticker,
                nct_id=entity_hints.nct_id,
            )

            return RawDocument.from_text(
                id=str(uuid.uuid4()),
                source=self.source_type,
                title=title,
                raw_text=raw_text,
                entity_hints=hints,
                retrieved_at=retrieved_at,
                source_url=source_url,
                published_at=published_at,
            )
        except Exception:
            return None
