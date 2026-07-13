"""Generic, target/modality-only source connectors.

Every connector builds its query from the buyer's canonical target and modality vocabulary only.
No connector accepts or embeds a benchmark/reference asset name -- that boundary is what keeps the
benchmark honest. Connectors are injected with a ``search_fn`` so tests never touch the network;
the default ``search_fn`` performs the live request.

Each connector returns a :class:`SourceHealth` describing stages 1, 2, 4, 5 of acquisition and
writes every retrieved document into the :class:`CorpusStore`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from bve.se.acquisition.corpus_store import CorpusStore, ParserStatus
from bve.se.acquisition.http import get_json, get_text, safe_get_public_page
from bve.se.acquisition.source_health import SourceHealth
from bve.se.schemas.contracts import SourceTier

SearchFn = Callable[[str], list[dict[str, Any]]]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class TargetQuery:
    """One canonical target and the alias vocabulary used to retrieve it generically."""

    canonical_id: str
    aliases: Sequence[str]

    def or_group(self) -> str:
        terms = list(dict.fromkeys([self.canonical_id, *self.aliases]))
        return " OR ".join(terms)


def _modality_or_group(modality_terms: Sequence[str]) -> str:
    terms = list(dict.fromkeys([*modality_terms, "CD3", "bispecific", "T-cell engager", "BiTE"]))
    return " OR ".join(terms)


def _strip_html(raw: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()


def _parse_year(value: Any) -> date | None:
    text = str(value or "")
    match = re.search(r"(19|20)\d{2}", text)
    if not match:
        return None
    try:
        return date(int(match.group(0)), 1, 1)
    except ValueError:
        return None


class ClinicalTrialsGovConnector:
    """Retrieve trial-registry records by target + modality (native replay format)."""

    source_family = "clinicaltrials_gov"

    def __init__(self, search_fn: SearchFn | None = None, *, page_size: int = 200) -> None:
        self.search_fn = search_fn or self._live_search
        self.page_size = page_size

    def _live_search(self, term: str) -> list[dict[str, Any]]:
        payload = get_json(
            "https://clinicaltrials.gov/api/v2/studies",
            params={"query.term": term, "pageSize": min(self.page_size, 1000)},
        )
        if not isinstance(payload, dict):
            raise ValueError("ClinicalTrials.gov returned a non-object JSON response")
        return [study.get("protocolSection", {}) for study in payload.get("studies", [])]

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        modality = _modality_or_group(modality_terms)
        raw: list[dict[str, Any]] = []
        try:
            for target in targets:
                raw.extend(self.search_fn(f"({target.or_group()}) AND ({modality})"))
        except Exception as exc:  # network / API boundary
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )
        parsed = failures = indexed = 0
        for protocol in raw:
            ident = protocol.get("identificationModule", {})
            nct = ident.get("nctId", "")
            title = ident.get("briefTitle", "") or ident.get("officialTitle", "")
            interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
            intervention_text = " ".join(
                " ".join(
                    [i.get("name", ""), i.get("description", ""), " ".join(i.get("otherNames", []) or [])]
                )
                for i in interventions
            )
            summary = protocol.get("descriptionModule", {}).get("briefSummary", "")
            sponsor = protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
            text = " ".join([title, ident.get("officialTitle", ""), summary, intervention_text, sponsor, nct])
            parser_status = ParserStatus.OK if text.strip() else ParserStatus.EMPTY
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=f"https://clinicaltrials.gov/study/{nct}" if nct else "https://clinicaltrials.gov/",
                publisher="ClinicalTrials.gov",
                document_type="trial_registry_record",
                source_tier=SourceTier.REGISTRY,
                raw_payload=protocol,
                text=text,
                title=title,
                as_of_date=as_of_date,
                parser_status=parser_status,
                native_snapshot=True,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=bool(raw),
            raw_record_count=len(raw),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
        )


class FdaLabelConnector:
    """Retrieve approved drug labels by mechanism (openFDA full-text over label body).

    This is the generic, regulatory-grade substitute for per-drug DailyMed lookups: it searches
    label prose for the target and modality, so it recovers approved target-directed engagers
    without ever naming a specific product.
    """

    source_family = "fda_label"

    def __init__(self, search_fn: SearchFn | None = None, *, limit: int = 25) -> None:
        self.search_fn = search_fn or self._live_search
        self.limit = limit

    def _live_search(self, query: str) -> list[dict[str, Any]]:
        payload = get_json(
            "https://api.fda.gov/drug/label.json",
            params={"search": query, "limit": self.limit},
            allow_not_found=True,
        )
        if payload is None:  # openFDA returns 404 for zero matches
            return []
        if not isinstance(payload, dict):
            raise ValueError("openFDA returned a non-object JSON response")
        return payload.get("results", [])

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        modality_clauses = " OR ".join(
            f'description:"{term}"' for term in dict.fromkeys([*modality_terms, "bispecific", "T-cell"])
        )
        raw: list[dict[str, Any]] = []
        seen_setids: set[str] = set()
        try:
            for target in targets:
                query = f'description:"{target.canonical_id}" AND ({modality_clauses})'
                for record in self.search_fn(query):
                    setid = record.get("set_id") or record.get("id") or ""
                    if setid and setid in seen_setids:
                        continue
                    seen_setids.add(setid)
                    raw.append(record)
        except Exception as exc:
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )
        parsed = failures = indexed = 0
        for record in raw:
            openfda = record.get("openfda", {})
            setid = record.get("set_id") or record.get("id") or ""
            brand = " ".join(openfda.get("brand_name", []) or [])
            generic = " ".join(openfda.get("generic_name", []) or [])
            substance = " ".join(openfda.get("substance_name", []) or [])
            body = " ".join(
                " ".join(record.get(field, []) or [])
                for field in ("description", "indications_and_usage", "mechanism_of_action", "clinical_pharmacology")
            )
            text = " ".join([brand, generic, substance, body])[:20000]
            parser_status = ParserStatus.OK if text.strip() else ParserStatus.EMPTY
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=(
                    f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"
                    if setid
                    else "https://dailymed.nlm.nih.gov/"
                ),
                publisher="FDA/DailyMed",
                document_type="approved_drug_label",
                source_tier=SourceTier.REGULATORY,
                raw_payload=record,
                text=text,
                title=(brand or generic or substance or "approved label").strip(),
                as_of_date=as_of_date,
                parser_status=parser_status,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=bool(raw),
            raw_record_count=len(raw),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
        )


class PubMedConnector:
    """Retrieve publication abstracts by target + modality (native replay format)."""

    source_family = "pubmed"

    def __init__(self, search_fn: SearchFn | None = None, *, limit: int = 100) -> None:
        self.search_fn = search_fn or self._live_search
        self.limit = limit

    def _live_search(self, term: str) -> list[dict[str, Any]]:
        from xml.etree import ElementTree

        search = get_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": term, "retmode": "json", "retmax": self.limit},
        )
        if not isinstance(search, dict):
            raise ValueError("PubMed search returned a non-object JSON response")
        ids = search.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        fetch = get_text(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            timeout=(5.0, 45.0),
        )
        root = ElementTree.fromstring(fetch)
        records: list[dict[str, Any]] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID") or ""
            title_node = article.find(".//ArticleTitle")
            title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
            abstract = " ".join(
                " ".join(node.itertext()) for node in article.findall(".//AbstractText")
            ).strip()
            year = article.findtext(".//PubDate/Year") or article.findtext(".//PubDate/MedlineDate") or ""
            records.append({"pmid": pmid, "title": title, "abstract": abstract, "publication_date": year})
        return records

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        modality = " OR ".join(
            f'"{term}"[Title/Abstract]'
            for term in dict.fromkeys([*modality_terms, "bispecific", "T-cell engager", "BiTE", "CD3"])
        )
        raw: list[dict[str, Any]] = []
        seen_pmids: set[str] = set()
        try:
            for target in targets:
                target_clause = " OR ".join(
                    f'"{alias}"[Title/Abstract]' for alias in dict.fromkeys([target.canonical_id, *target.aliases])
                )
                for record in self.search_fn(f"({target_clause}) AND ({modality})"):
                    pmid = str(record.get("pmid", ""))
                    if pmid and pmid in seen_pmids:
                        continue
                    seen_pmids.add(pmid)
                    raw.append(record)
        except Exception as exc:
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )
        parsed = failures = indexed = 0
        for record in raw:
            pmid = str(record.get("pmid", ""))
            title = str(record.get("title", ""))
            abstract = str(record.get("abstract", ""))
            text = f"{title} {abstract}".strip()
            parser_status = ParserStatus.OK if text else ParserStatus.EMPTY
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "https://pubmed.ncbi.nlm.nih.gov/",
                publisher="PubMed",
                document_type="publication_abstract",
                source_tier=SourceTier.PRIMARY,
                raw_payload=record,
                text=text,
                title=title,
                as_of_date=as_of_date,
                publication_date=_parse_year(record.get("publication_date")),
                parser_status=parser_status,
                native_snapshot=True,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=bool(raw),
            raw_record_count=len(raw),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
        )


class SecEdgarConnector:
    """Retrieve corporate-disclosure text via EDGAR full-text search by target + modality.

    ``search_fn`` returns full-text hit metadata; ``fetch_fn`` returns filing document text for a
    bounded number of top hits so that asset codes disclosed in filings become indexable evidence.
    """

    source_family = "sec_edgar"

    def __init__(
        self,
        search_fn: SearchFn | None = None,
        *,
        fetch_fn: Callable[[str], str] | None = None,
        max_documents: int = 25,
    ) -> None:
        self.search_fn = search_fn or self._live_search
        self.fetch_fn = fetch_fn or self._live_fetch
        self.max_documents = max_documents

    def _live_search(self, query: str) -> list[dict[str, Any]]:
        payload = get_json(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": query},
        )
        if not isinstance(payload, dict):
            raise ValueError("SEC EDGAR returned a non-object JSON response")
        return payload.get("hits", {}).get("hits", [])

    @staticmethod
    def _live_fetch(url: str) -> str:
        return get_text(url)

    @staticmethod
    def _filing_url(hit: dict[str, Any]) -> tuple[str, str]:
        hit_id = str(hit.get("_id", ""))
        source = hit.get("_source", {})
        ciks = source.get("ciks", []) or [""]
        adsh, _, document = hit_id.partition(":")
        cik = str(int(ciks[0])) if ciks and str(ciks[0]).isdigit() else str(ciks[0])
        accession = adsh.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
        return url, document

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            for target in targets:
                for term in dict.fromkeys([*modality_terms, "bispecific", "T-cell engager"]):
                    for hit in self.search_fn(f'"{target.canonical_id} {term}"'):
                        hit_id = str(hit.get("_id", ""))
                        if hit_id and hit_id in seen:
                            continue
                        seen.add(hit_id)
                        hits.append(hit)
        except Exception as exc:
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )
        parsed = failures = indexed = 0
        for hit in hits[: self.max_documents]:
            url, document = self._filing_url(hit)
            source = hit.get("_source", {})
            display = " ".join(source.get("display_names", []) or [])
            try:
                body = _strip_html(self.fetch_fn(url))[:40000]
                parser_status = ParserStatus.OK if body else ParserStatus.EMPTY
            except Exception:
                body = ""
                parser_status = ParserStatus.FAILED
            text = f"{display} {body}".strip()
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=url,
                publisher=display or "SEC EDGAR",
                document_type=str(source.get("file_type", "sec_filing")),
                source_tier=SourceTier.PRIMARY,
                raw_payload={"hit": hit, "text": body},
                text=text,
                title=display or document,
                as_of_date=as_of_date,
                publication_date=_parse_year(source.get("file_date")),
                parser_status=parser_status,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=bool(hits),
            raw_record_count=len(hits),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
        )


class DeclaredUrlConnector:
    """Fetch a declared list of public URLs (company pipeline/press/conference pages).

    The URL list is *retrieval configuration*, not asset-name search: it enumerates where a source
    family publishes, not which assets to find. Pages are fetched, stripped to text, and indexed.
    """

    def __init__(
        self,
        source_family: str,
        urls: Sequence[str],
        *,
        source_tier: SourceTier = SourceTier.COMPANY_AUTHORED,
        fetch_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.source_family = source_family
        self.urls = list(dict.fromkeys(urls))
        self.source_tier = source_tier
        self.fetch_fn = fetch_fn or self._live_fetch

    @staticmethod
    def _live_fetch(url: str) -> str:
        return safe_get_public_page(url)

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        parsed = failures = indexed = 0
        succeeded = True
        errors: list[str] = []
        for url in self.urls:
            try:
                body = _strip_html(self.fetch_fn(url))[:40000]
                parser_status = ParserStatus.OK if body else ParserStatus.EMPTY
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                body = ""
                parser_status = ParserStatus.FAILED
                succeeded = succeeded and False
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=url,
                publisher=self.source_family,
                document_type=self.source_family,
                source_tier=self.source_tier,
                raw_payload={"url": url, "text": body},
                text=body,
                title=url,
                as_of_date=as_of_date,
                parser_status=parser_status,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=succeeded or not self.urls,
            query_returned_results=parsed > 0,
            raw_record_count=len(self.urls),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
            error="; ".join(errors) or None,
        )
