"""Generic, target/modality-only source connectors.

Every connector builds its query from the buyer's canonical target and modality vocabulary only.
No connector accepts or embeds a benchmark/reference asset name -- that boundary is what keeps the
benchmark honest. Connectors are injected with a ``search_fn`` so tests never touch the network;
the default ``search_fn`` performs the live request.

Each connector returns a :class:`SourceHealth` describing stages 1, 2, 4, 5 of acquisition and
writes every retrieved document into the :class:`CorpusStore`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

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


def _prose_terms(terms: Sequence[str]) -> list[str]:
    """Keep only terms a document could actually contain.

    The modality vocabulary mixes ontology identifiers with the words companies write:
    ``ANTIBODY_DRUG_CONJUGATE`` alongside ``antibody drug conjugate``. Full-text search over
    prose is answered by the latter and never by the former, so phrase-searching an
    identifier does not retrieve fewer documents -- it retrieves none, silently, which reads
    as "this source has no evidence" rather than "this query was unaskable".
    """

    return [term for term in dict.fromkeys(terms) if term and "_" not in term]


def _modality_or_group(modality_terms: Sequence[str]) -> str:
    terms = list(dict.fromkeys([*modality_terms, "CD3", "bispecific", "T-cell engager", "BiTE"]))
    return " OR ".join(terms)


def _strip_html(raw: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()


#     <meta property="article:published_time" content="2026-07-15T09:00:00Z">
#     <meta itemprop="datePublished" content="2026-07-15">
#     "datePublished": "2026-07-15"        (JSON-LD)
#     <time datetime="2026-07-15">
_PUBLISHED_RE = re.compile(
    r"(?:article:published_time|datePublished|date_published|citation_publication_date|"
    r"pubdate|DC\.date(?:\.issued)?)\D{0,40}?((?:19|20)\d{2}-\d{2}-\d{2})"
    r"|<time[^>]*\bdatetime=[\"']((?:19|20)\d{2}-\d{2}-\d{2})",
    re.IGNORECASE,
)


_HREF_RE = re.compile(r"""<a\b[^>]*\bhref=["']([^"'#?]+)""", re.IGNORECASE)


def _same_host_links(raw_html: str, index_url: str) -> list[str]:
    """Which documents does this index page point at, on this publisher's own site?

    The declared URL says where a source family publishes; following its links stays inside
    that scope. Off-host links are dropped rather than followed, so a newsroom's social,
    analytics and partner links cannot turn one declared page into an open web crawl.
    """

    base = urlsplit(index_url)
    links: list[str] = []
    for href in _HREF_RE.findall(raw_html):
        absolute = urljoin(index_url, href.strip())
        parts = urlsplit(absolute)
        if parts.scheme in {"http", "https"} and parts.netloc == base.netloc:
            if absolute.rstrip("/") != index_url.rstrip("/"):
                links.append(absolute)
    return list(dict.fromkeys(links))


def _published_on(raw_html: str) -> date | None:
    """When did this page say it was published?

    Read from the markup, before it is stripped: the date lives in meta tags and JSON-LD
    that `_strip_html` throws away. Only the page's own declaration counts -- a date found
    loose in body text could be a trial start, an enrolment window, or any other date the
    page happens to mention, and guessing wrong here manufactures lookahead rather than
    preventing it.
    """

    match = _PUBLISHED_RE.search(raw_html)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1) or match.group(2))
    except ValueError:
        return None


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


def _crossref_date(item: dict[str, Any]) -> date | None:
    """Read the earliest date Crossref asserts for an item, or None if it asserts none.

    Crossref carries several date fields and they disagree: a meeting supplement is often
    issued online months before the print issue it is bound into. The earliest asserted date
    is the one that answers "could an as-of run have seen this", so that is the one used.
    Partial dates (year only, year-month) are completed to the first of the period, which is
    the earliest day the assertion permits.
    """

    candidates: list[date] = []
    for key in ("published", "published-online", "published-print", "issued", "created"):
        parts = item.get(key)
        if not isinstance(parts, dict):
            continue
        date_parts = parts.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        head = date_parts[0]
        if not isinstance(head, list) or not head:
            continue
        try:
            year = int(head[0])
            month = int(head[1]) if len(head) > 1 else 1
            day = int(head[2]) if len(head) > 2 else 1
            candidates.append(date(year, month, day))
        except (TypeError, ValueError):
            continue
    return min(candidates) if candidates else None


@dataclass(frozen=True)
class ConferenceVenue:
    """Where a conference publishes its abstracts, stated as bibliographic identifiers.

    Conference organisers publish accepted abstracts as supplements to a journal, and those
    supplements are indexed by DOI like any other article. Naming the container journal is
    therefore enough to reach a meeting's abstracts through a public metadata API, with no
    conference-specific scraping and nothing that depends on which assets the benchmark
    expects to find.
    """

    source_family: str
    publisher: str
    container_titles: Sequence[str]


CONFERENCE_VENUES: tuple[ConferenceVenue, ...] = (
    ConferenceVenue("conference_asco", "ASCO", ("Journal of Clinical Oncology",)),
    ConferenceVenue("conference_aacr", "AACR", ("Cancer Research",)),
    ConferenceVenue("conference_ash", "ASH", ("Blood",)),
)


class CrossrefConferenceConnector:
    """Acquire conference-abstract metadata for one venue through the Crossref REST API.

    This is one mechanism parameterised by venue rather than three scrapers, because the
    three conferences differ only in which journal carries their supplements. It is also the
    non-circumventing route: the publishers' own abstract pages refuse an identified research
    client, and Crossref publishes the same items' bibliographic metadata openly.

    What it yields is title-and-DOI level only, so every mention it produces is
    DISCOVERY_EVIDENCE. It can surface an asset name worth resolving; it can never be the
    positive evidence that mints an identity alias. Full abstract text, if a licensed route
    is ever configured, would be a separate acquisition emitting richer typed evidence.
    """

    def __init__(
        self,
        venue: ConferenceVenue,
        search_fn: Callable[[str, str, date], list[dict[str, Any]]] | None = None,
        *,
        limit: int = 100,
    ) -> None:
        self.venue = venue
        self.source_family = venue.source_family
        self.search_fn = search_fn or self._live_search
        self.limit = limit

    def _live_search(self, container_title: str, query: str, as_of_date: date) -> list[dict[str, Any]]:
        from bve.se.acquisition.http import configured_contact_email

        payload = get_json(
            "https://api.crossref.org/works",
            params={
                "filter": ",".join(
                    [
                        f"container-title:{container_title}",
                        f"until-created-date:{as_of_date.isoformat()}",
                    ]
                ),
                "query.bibliographic": query,
                "rows": self.limit,
                "select": "DOI,title,subtitle,container-title,published,published-online,"
                "published-print,issued,created,type,page,volume,issue,publisher",
                "mailto": configured_contact_email(),
            },
        )
        if not isinstance(payload, dict):
            raise ValueError("Crossref returned a non-object JSON response")
        items = payload.get("message", {}).get("items", [])
        return [item for item in items if isinstance(item, dict)]

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        # The query is built from the target and modality vocabulary the problem declares, not
        # from asset names: asking for a drug by name can only rediscover what is already
        # known, and would tune the source to the benchmark answer.
        modality = " ".join(dict.fromkeys(modality_terms))
        raw: list[dict[str, Any]] = []
        seen_dois: set[str] = set()
        self.withheld_as_of: list[str] = []
        self.withheld_undated: list[str] = []
        try:
            for target in targets:
                aliases = " ".join(dict.fromkeys([target.canonical_id, *target.aliases]))
                query = f"{aliases} {modality}".strip()
                for container_title in self.venue.container_titles:
                    for item in self.search_fn(container_title, query, as_of_date):
                        doi = str(item.get("DOI", "")).lower()
                        if not doi or doi in seen_dois:
                            continue
                        seen_dois.add(doi)
                        raw.append(item)
        except Exception as exc:
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )

        parsed = failures = indexed = 0
        for item in raw:
            doi = str(item.get("DOI", ""))
            # Admission is fail-closed on date for the same reason as EDGAR and the declared
            # URL families: a metadata API answers as of today, and an undated item is not
            # known to predate the question.
            published = _crossref_date(item)
            if published is None:
                self.withheld_undated.append(doi)
                continue
            if published > as_of_date:
                self.withheld_as_of.append(doi)
                continue
            title = " ".join(
                str(part) for part in [*item.get("title", []), *item.get("subtitle", [])] if part
            ).strip()
            parser_status = ParserStatus.OK if title else ParserStatus.EMPTY
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=f"https://doi.org/{doi}" if doi else "https://api.crossref.org/works",
                publisher=self.venue.publisher,
                document_type="conference_abstract_metadata",
                source_tier=SourceTier.SECONDARY,
                raw_payload=item,
                text=title,
                title=title,
                as_of_date=as_of_date,
                publication_date=published,
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


def _filed_by(hit: dict[str, Any], as_of_date: date) -> bool:
    """Could the run have read this filing on its as-of date?

    EDGAR full-text search answers as of today, so a run replaying an August question is
    otherwise handed September disclosures and credited with having found them. An undated
    hit is refused for the same reason a contradicted alias is: unknown is not
    known-to-be-earlier, and the cost of dropping one filing is far below the cost of
    lookahead in a scored benchmark.
    """

    text = str(hit.get("_source", {}).get("file_date") or "")
    try:
        return date.fromisoformat(text[:10]) <= as_of_date
    except ValueError:
        return False


def _round_robin(
    groups: Sequence[Sequence[dict[str, Any]]], limit: int
) -> list[dict[str, Any]]:
    """Spend a document budget across the queries that were asked, not on the first one.

    One broad alias phrase returns far more hits than the budget, so taking hits in arrival
    order means every modality-qualified phrase is searched and then discarded -- the search
    bound buys nothing and the evidence is whatever the source happened to rank first for a
    single query. Interleaving keeps breadth while still preferring each phrase's own top
    hits.
    """

    picked: list[dict[str, Any]] = []
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if len(picked) >= limit:
                return picked
            if index < len(group):
                picked.append(group[index])
    return picked


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
        max_searches: int = 60,
        search_ledger: Path | None = None,
    ) -> None:
        self.search_fn = search_fn or self._live_search
        self.fetch_fn = fetch_fn or self._live_fetch
        self.max_documents = max_documents
        #: Where the phrase -> hits -> selection trail is written, if anywhere.
        #:
        #: The corpus records which 25 filings became evidence. It cannot record why those
        #: 25 and not others: that depends on how many hits each phrase returned, which the
        #: as-of filter dropped, and where round-robin selection stopped. Without the trail
        #: the selection is unreproducible, so a later question about whether a program was
        #: missed for want of a phrase or for want of budget has no answer.
        self.search_ledger = search_ledger
        #: A bound on requests made to the source, not on evidence admitted. The alias x
        #: modality product is order 10^3 phrases for one target, which is more traffic than
        #: a public filing search should be asked for when the document budget is 25. The
        #: broad alias-only phrases are ordered first so the budget spends on breadth.
        self.max_searches = max_searches

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
    def _search_phrases(
        target: TargetQuery, modality_terms: Sequence[str]
    ) -> list[str]:
        """The full-text queries that ask this source the run's scientific question.

        Two bands, both target-driven and neither naming an asset. The target alias alone is
        what finds a program a filing describes without using the modality words the
        ontology happens to know -- which is the preclinical and undisclosed-clinical case
        M12 exists to reach. The alias-plus-modality pairs then bias the bounded document
        budget toward filings that discuss a matching program rather than mentioning the
        target in a risk factor.
        """

        aliases = _prose_terms([target.canonical_id, *target.aliases])
        modalities = _prose_terms([*modality_terms, "bispecific", "T-cell engager"])
        phrases = [f'"{alias}"' for alias in aliases]
        phrases.extend(
            f'"{alias}" "{modality}"' for alias in aliases for modality in modalities
        )
        return list(dict.fromkeys(phrases))

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

    def _write_search_ledger(
        self,
        trail: list[dict[str, Any]],
        selected: Sequence[dict[str, Any]],
        by_phrase: Sequence[Sequence[dict[str, Any]]],
        as_of_date: date,
    ) -> None:
        """Record why these documents and not others.

        Two things are unreproducible from the corpus alone: which phrase surfaced a filing,
        and where the document budget ran out. Both are needed to tell "no filing discusses
        this program" apart from "a filing does, and the budget stopped one short" -- and
        those call for opposite responses.
        """

        if self.search_ledger is None:
            return
        origin = {
            str(hit.get("_id", "")): record["phrase"]
            for record, phrase_hits in zip(trail, by_phrase, strict=False)
            for hit in phrase_hits
        }
        self.search_ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.search_ledger.open("w") as handle:
            handle.write(
                json.dumps(
                    {
                        "record": "summary",
                        "source_family": self.source_family,
                        "as_of_date": as_of_date.isoformat(),
                        "phrases_searched": len(trail),
                        "max_searches": self.max_searches,
                        "search_budget_exhausted": len(trail) >= self.max_searches,
                        "hits_admitted": sum(len(group) for group in by_phrase),
                        "documents_selected": len(selected),
                        "selection": "round-robin across phrases in the order asked",
                    }
                )
                + "\n"
            )
            for record in trail:
                handle.write(json.dumps({"record": "phrase", **record}) + "\n")
            for rank, hit in enumerate(selected):
                hit_id = str(hit.get("_id", ""))
                url, _ = self._filing_url(hit)
                handle.write(
                    json.dumps(
                        {
                            "record": "selected",
                            "selection_rank": rank,
                            "hit_id": hit_id,
                            "source_url": url,
                            "selected_by_phrase": origin.get(hit_id),
                            "file_date": hit.get("_source", {}).get("file_date"),
                        }
                    )
                    + "\n"
                )

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        trail: list[dict[str, Any]] = []
        by_phrase: list[list[dict[str, Any]]] = []
        seen: set[str] = set()
        searched = 0
        try:
            for target in targets:
                for phrase in self._search_phrases(target, modality_terms):
                    if searched >= self.max_searches:
                        break
                    searched += 1
                    found: list[dict[str, Any]] = []
                    returned = withheld_as_of = duplicate = 0
                    for hit in self.search_fn(phrase):
                        returned += 1
                        hit_id = str(hit.get("_id", ""))
                        if hit_id and hit_id in seen:
                            duplicate += 1
                            continue
                        if not _filed_by(hit, as_of_date):
                            withheld_as_of += 1
                            continue
                        seen.add(hit_id)
                        found.append(hit)
                    by_phrase.append(found)
                    trail.append(
                        {
                            "phrase": phrase,
                            "target": target.canonical_id,
                            "hits_returned": returned,
                            "hits_admitted": len(found),
                            # Counted apart from each other: "the source had nothing for
                            # this phrase" and "the source had it but after the as-of date"
                            # are different answers to why a program is absent.
                            "withheld_after_as_of_date": withheld_as_of,
                            "already_seen": duplicate,
                            "admitted_hit_ids": [
                                str(hit.get("_id", "")) for hit in found
                            ],
                        }
                    )
        except Exception as exc:
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )
        hits = [hit for phrase_hits in by_phrase for hit in phrase_hits]
        selected = _round_robin(by_phrase, self.max_documents)
        self._write_search_ledger(trail, selected, by_phrase, as_of_date)
        parsed = failures = indexed = 0
        for hit in selected:
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

    A live web page answers as of today, so a run replaying an August question is otherwise
    handed September disclosures and credited with having found them. Each page must therefore
    declare when it was published, and a page published after the as-of date is refused. An
    undated page is refused for the same reason an undated filing is: unknown is not
    known-to-be-earlier, and the cost of dropping a page is far below the cost of lookahead in
    a scored benchmark. Set `require_publication_date=False` only outside scored replay.
    """

    def __init__(
        self,
        source_family: str,
        urls: Sequence[str],
        *,
        source_tier: SourceTier = SourceTier.COMPANY_AUTHORED,
        fetch_fn: Callable[[str], str] | None = None,
        require_publication_date: bool = True,
        follow_links: int = 0,
    ) -> None:
        self.source_family = source_family
        self.urls = list(dict.fromkeys(urls))
        self.source_tier = source_tier
        self.fetch_fn = fetch_fn or self._live_fetch
        self.require_publication_date = require_publication_date
        self.follow_links = follow_links
        self.visited: list[str] = []

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
        self.withheld_as_of: list[str] = []
        self.withheld_undated: list[str] = []
        self.visited = []
        succeeded = True
        errors: list[str] = []

        # An index page is a place to look, not a document: it carries no publication date, so
        # under the as-of contract it is inadmissible while the dated articles it links to are
        # exactly the evidence this family exists to reach. The per-index budget is spent on
        # links in the order the index presents them, which is the publisher's own ordering
        # rather than one we impose.
        documents: list[str] = []
        for url in self.urls:
            if self.follow_links <= 0:
                documents.append(url)
                continue
            try:
                index_html = self.fetch_fn(url)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                succeeded = False
                continue
            finally:
                self.visited.append(url)
            documents.extend(_same_host_links(index_html, url)[: self.follow_links])
        documents = list(dict.fromkeys(documents))

        for url in documents:
            published: date | None = None
            self.visited.append(url)
            try:
                raw = self.fetch_fn(url)
                published = _published_on(raw)
                body = _strip_html(raw)[:40000]
                parser_status = ParserStatus.OK if body else ParserStatus.EMPTY
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                body = ""
                parser_status = ParserStatus.FAILED
                succeeded = succeeded and False
            if self.require_publication_date and parser_status is ParserStatus.OK:
                # Withholding is not a parse failure: the page was read fine, it is just not
                # admissible for this question. Counting it as a failure would make a healthy
                # source look broken.
                if published is None:
                    self.withheld_undated.append(url)
                    continue
                if published > as_of_date:
                    self.withheld_as_of.append(url)
                    continue
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
                raw_payload={
                    "url": url,
                    "text": body,
                    "published_on": published.isoformat() if published else None,
                },
                text=body,
                title=url,
                as_of_date=as_of_date,
                publication_date=published,
                parser_status=parser_status,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=succeeded or not self.urls,
            query_returned_results=parsed > 0,
            # Documents considered, not URLs declared: with link-following one declared index
            # stands for many documents, and the health record should say how many were weighed.
            raw_record_count=len(documents),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
            error="; ".join(errors) or None,
        )
