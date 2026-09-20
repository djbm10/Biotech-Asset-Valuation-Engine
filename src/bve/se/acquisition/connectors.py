"""Generic, target/modality-only source connectors.

Every connector builds its query from the buyer's canonical target and modality vocabulary only.
No connector accepts or embeds a benchmark/reference asset name -- that boundary is what keeps the
benchmark honest. Connectors are injected with a ``search_fn`` so tests never touch the network;
the default ``search_fn`` performs the live request.

Each connector returns a :class:`SourceHealth` describing stages 1, 2, 4, 5 of acquisition and
writes every retrieved document into the :class:`CorpusStore`.
"""

from __future__ import annotations

import hashlib
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


def _filing_date(value: Any) -> date | None:
    """The exact date an EDGAR filing carries, or nothing.

    Distinct from :func:`_parse_year` on purpose. EDGAR states ``file_date`` as a full ISO
    date, so degrading it to January 1 of that year records a date the document was not
    published on -- and, because January 1 is earlier, makes every filing look up to eleven
    months older than it is. Where a source states the day, the day is what gets stored;
    ``_parse_year`` remains for the sources that really do publish a year only.
    """

    try:
        return date.fromisoformat(str(value or "")[:10])
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

    #: The venue's *documented* abstract/poster numbering convention, as a regular expression
    #: matching the identifier alone. Set only where the conference publishes its numbering
    #: and the container's titles actually carry it; ``None`` means this venue declares no
    #: convention, and the connector must then not guess at one. See
    #: ``_leading_bibliographic_id`` for why only an anchored prefix qualifies.
    abstract_id_pattern: str | None = None


CONFERENCE_VENUES: tuple[ConferenceVenue, ...] = (
    ConferenceVenue("conference_asco", "ASCO", ("Journal of Clinical Oncology",)),
    ConferenceVenue("conference_aacr", "AACR", ("Cancer Research",)),
    # Blood's Crossref titles carry no abstract number, so ASH declares no convention. That
    # absence is the only reason ASH never exposed the identifier-as-asset defect.
    ConferenceVenue("conference_ash", "ASH", ("Blood",)),
    # EHA congress abstracts appear as HemaSphere supplements. The casing is the Crossref
    # filter value verbatim: "Hemasphere" matches nothing. ``publisher`` names the society
    # whose meeting produced the abstract, not Wiley, who prints the journal.
    #
    # EHA numbers its abstracts S### (oral), P#### / PB#### / PF#### / PS#### (poster), and
    # prints that number as the first token of the title.
    ConferenceVenue(
        "conference_eha", "EHA", ("HemaSphere",), abstract_id_pattern=r"(?:S|P|PB|PF|PS)\d+"
    ),
)


def _leading_bibliographic_id(title: str, pattern: str | None) -> str:
    """The venue's own abstract identifier, when the title opens with it.

    Anchored deliberately. A bibliographic identifier is metadata because of *where* the
    source put it, not because of how it looks: the venue prints its number first, before the
    title proper. The same characters occurring later in a title are ordinary words of the
    title, and one of them may well be a real development code -- programs named in this shape
    are common, so a match anywhere would start deleting genuine assets.

    Returns "" when the venue declares no convention or the title does not open with one.
    """

    if not pattern or not title:
        return ""
    match = re.match(rf"({pattern})[:.]?\s+\S", title)
    return match.group(1) if match else ""


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
        # The query is built from the declared target vocabulary, not from asset names: asking
        # for a drug by name can only rediscover what is already known, and would tune the
        # source to the benchmark answer.
        #
        # Modality terms are deliberately not appended. `query.bibliographic` is a relevance
        # bag of words with no boolean OR, so adding the ~120-term modality vocabulary dilutes
        # the query instead of widening it -- measured: ASCO returned 63 items with the
        # modality bag and 200 without it, against the same budget. Modality is a property of
        # the asset a title mentions, and it is applied downstream during extraction and
        # gating, where it can be evaluated rather than guessed at from word overlap.
        del modality_terms
        raw: list[dict[str, Any]] = []
        seen_dois: set[str] = set()
        self.withheld_as_of: list[str] = []
        self.withheld_undated: list[str] = []
        try:
            for target in targets:
                query = " ".join(dict.fromkeys([target.canonical_id, *target.aliases]))
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
                # Recorded alongside the title, never cut out of it: custody keeps exactly
                # what the source said, and downstream identity nomination skips this one
                # token rather than this document.
                bibliographic_id=_leading_bibliographic_id(
                    title, self.venue.abstract_id_pattern
                ),
                as_of_date=as_of_date,
                publication_date=published,
                parser_status=parser_status,
                # Not a native snapshot: that flag means the document replays through a
                # dedicated CT.gov/PubMed adapter, and documents carrying it are excluded from
                # the generated source index. There is no Crossref adapter, so claiming it
                # would drop every item out of the replay silently.
                native_snapshot=False,
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


@dataclass(frozen=True)
class BulkArtifact:
    """An already-acquired bulk publication, named by where it came from and what it was.

    Bulk routes invert the usual acquisition shape: one large file is fetched once and then
    parsed repeatedly, so the bytes and the parse are separate events with separate failure
    modes. Separating them is what makes a re-parse cheap and a re-fetch unnecessary -- a
    parser bug must never be a reason to go back to the publisher.

    ``sha256`` is therefore not decoration. The connector refuses to parse a local file whose
    digest differs from the one recorded at acquisition, because silently parsing different
    bytes under the recorded URL's name is the one failure the receipt could not later reveal.

    ``published`` is the earliest independently verifiable timestamp for the artifact -- in
    practice the HTTP ``Last-Modified`` recorded when it was fetched. Session dates printed
    inside the document are more precise and are kept in the payload, but they are the
    document's own say-so, so they are not what the as-of policy is applied to.
    """

    source_url: str
    local_path: Path
    sha256: str
    published: date
    publisher: str
    source_family: str


_ABSTRACT_MARKER_RE = re.compile(r"^#\s*(\d{3,6})\s*$", re.MULTILINE)


def _split_abstracts(text: str) -> list[tuple[str, str]]:
    """Cut a proceedings text into (abstract number, body) at the printed number markers.

    The marker is the only structure the document states about itself unambiguously: a line
    containing nothing but ``#`` and the abstract number. Session headers, author blocks and
    affiliation footnotes have no reliable delimiter, so nothing is inferred about them --
    whatever precedes the first marker is preamble and is dropped rather than guessed at.
    """

    matches = list(_ABSTRACT_MARKER_RE.finditer(text))
    segments: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        segments.append((match.group(1), body))
    return segments


def _abstract_title(body: str) -> str:
    """The title a proceedings abstract leads with, or nothing if it does not lead with one.

    Titles here run to a sentence end and may wrap over lines; the author list that follows
    has no delimiter of its own. So the rule is the sentence, bounded: lines are joined until
    one ends a sentence, and if none does within the bound the title is left empty rather than
    filled with the first few authors' names.
    """

    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        lines.append(stripped)
        if stripped.endswith((".", "?", "!")):
            return " ".join(lines)
        if len(lines) >= 4 or sum(len(part) for part in lines) > 400:
            break
    return ""


class AacrBulkProceedingsConnector:
    """Read AACR's official public bulk proceedings PDF into per-abstract documents.

    This is the officially published machine-retrievable route for this venue, and it is a
    different kind of evidence from the Crossref metadata for the same meeting: Crossref
    gives a title, this gives the abstract as printed. So the documents it writes are
    ordinary conference abstracts, tiered and typed exactly as PubMed abstracts are, and they
    reach the same extraction and the same M11 identity gates. Nothing here classifies
    evidence itself; a bulk route is an acquisition route, not a new authority.

    Admission is by the buyer's declared target vocabulary, matched against the abstract text.
    That is the same axis every other connector queries on, and it is applied here rather than
    at the source because a bulk file has no query interface. Modality terms are recorded per
    abstract but deliberately not required: a bulk artifact is already bounded to one meeting,
    so an extra conjunct would narrow the corpus without the source-side cost that motivates
    narrowing elsewhere.
    """

    document_type = "conference_abstract"
    delivery_channel = "PUBLISHER_BULK_DOWNLOAD"

    def __init__(self, artifact: BulkArtifact, *, extract_fn: Callable[[Path], str] | None = None) -> None:
        self.artifact = artifact
        self.source_family = artifact.source_family
        self.extract_fn = extract_fn or _extract_pdf_text
        self.withheld_as_of: list[str] = []
        self.withheld_undated: list[str] = []

    def _verified_text(self) -> str:
        digest = hashlib.sha256()
        with self.artifact.local_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != self.artifact.sha256:
            raise ValueError(
                f"{self.artifact.local_path}: digest {digest.hexdigest()} does not match the "
                f"{self.artifact.sha256} recorded for {self.artifact.source_url}; refusing to "
                "parse bytes the acquisition receipt does not describe"
            )
        return self.extract_fn(self.artifact.local_path)

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        try:
            text = self._verified_text()
        except Exception as exc:
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=False,
                query_returned_results=False,
                error=str(exc),
            )

        published = self.artifact.published
        segments = _split_abstracts(text)
        if published > as_of_date:
            # The whole artifact post-dates the run, so the refusal is recorded once against
            # every abstract in it rather than being invisible in a zero document count.
            self.withheld_as_of = [number for number, _ in segments]
            return SourceHealth(
                source_family=self.source_family,
                connector_succeeded=True,
                query_returned_results=bool(segments),
                raw_record_count=len(segments),
            )

        target_terms = {
            term.casefold()
            for target in targets
            for term in (target.canonical_id, *target.aliases)
            if term
        }
        modality_lookup = {term.casefold() for term in modality_terms if term}
        parsed = failures = indexed = 0
        for number, body in segments:
            folded = body.casefold()
            matched = sorted(term for term in target_terms if term in folded)
            if not matched:
                continue
            parser_status = ParserStatus.OK if body else ParserStatus.EMPTY
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                # The bulk file's URL plus the abstract number: the abstract has no separate
                # public address on this route, and claiming one it does not have would be a
                # provenance fiction.
                source_url=f"{self.artifact.source_url}#{number}",
                publisher=self.artifact.publisher,
                document_type=self.document_type,
                source_tier=SourceTier.PRIMARY,
                raw_payload={
                    "abstract_number": number,
                    "text": body,
                    "bulk_source_url": self.artifact.source_url,
                    "bulk_sha256": self.artifact.sha256,
                    "delivery_channel": self.delivery_channel,
                    "matched_target_terms": matched,
                    "matched_modality_terms": sorted(
                        term for term in modality_lookup if term in folded
                    ),
                },
                text=body,
                title=_abstract_title(body),
                as_of_date=as_of_date,
                publication_date=published,
                parser_status=parser_status,
                # No dedicated replay adapter exists for a bulk route, so these documents
                # have to travel through the generated source index like every other
                # non-native family; claiming otherwise drops them out of replay silently.
                native_snapshot=False,
            )
        return SourceHealth(
            source_family=self.source_family,
            connector_succeeded=True,
            query_returned_results=bool(segments),
            raw_record_count=len(segments),
            documents_parsed=parsed,
            documents_indexed=indexed,
            parse_failures=failures,
        )


def _extract_pdf_text(path: Path) -> str:
    """Page text of a PDF, joined in page order.

    ``pypdf`` is imported here rather than at module scope so that an engine without the
    ``pdf`` extra installed fails on this one family instead of failing to import at all.
    """

    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install extras
        raise ValueError(
            "reading bulk PDF proceedings needs the 'pdf' extra (pip install -e '.[pdf]')"
        ) from exc

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


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


def _edgar_full_text_search(query: str) -> list[dict[str, Any]]:
    """One EDGAR full-text query, shared by the families that read filings.

    Both the filing family and the SEC-filed press-release family ask this same endpoint the
    same scientific question; only what they then admit differs. Sharing the call keeps the
    two from drifting apart in how they talk to the source.
    """

    payload = get_json(
        "https://efts.sec.gov/LATEST/search-index",
        params={"q": query},
    )
    if not isinstance(payload, dict):
        raise ValueError("SEC EDGAR returned a non-object JSON response")
    return payload.get("hits", {}).get("hits", [])


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
        return _edgar_full_text_search(query)

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
                publication_date=_filing_date(source.get("file_date")),
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


#: Language by which a document says of itself that it is a press release.
#:
#: Deliberately narrow, and deliberately not "EX-99". An EX-99 exhibit is whatever the issuer
#: attached -- a corporate deck, a credit agreement schedule, audited statements of an
#: acquiree -- and in practice most carry no description beyond the exhibit number itself.
#: Equating the exhibit number with a press release would relabel all of that as company
#: news, which is a claim about the document's genre that the filing does not make.
_PRESS_RELEASE_RE = re.compile(
    r"\b(?:press\s+release|news\s+release|for\s+immediate\s+release|media\s+release)\b",
    re.IGNORECASE,
)

_EXHIBIT_99_RE = re.compile(r"^EX-99(?:\.\d+)?$", re.IGNORECASE)


def _rejection(hit_id: str, reason: str, hit: dict[str, Any]) -> dict[str, Any]:
    """A refusal recorded with the metadata the refusal was made on.

    A bare ``{hit_id, reason}`` pair cannot be audited after the fact: asking whether a
    classifier is too strict means asking which forms, exhibit types and descriptions it
    turned away, and none of that survives in the accession number. Carrying the four fields
    the decision actually read makes the refusal census answerable from the receipt alone,
    without re-querying the source -- which is the only way to check a live-acquired family
    without paying for another live acquisition.
    """

    source = hit.get("_source", {})
    return {
        "hit_id": hit_id,
        "reason": reason,
        "form": str(source.get("form", "")),
        "file_type": str(source.get("file_type", "")),
        "file_description": str(source.get("file_description", "")),
        "file_date": str(source.get("file_date", "")),
    }


def _press_release_basis(hit: dict[str, Any], body: str) -> str | None:
    """On what mechanical ground, if any, is this exhibit a press release?

    Returns the field that said so, or None. The distinction being preserved is between
    ``SEC filing evidence`` and ``SEC-filed issuer press release``: the second is a stronger
    claim about what kind of communication this is, and it needs the document or its filing
    metadata to actually say it. When nothing says it, the answer is None and the caller
    keeps the weaker, true classification rather than upgrading on a guess.
    """

    source = hit.get("_source", {})
    if _PRESS_RELEASE_RE.search(str(source.get("file_description", ""))):
        return "file_description"
    # Only the opening of the document: a release says what it is in its header, whereas a
    # deck forty pages later may merely reference one.
    if _PRESS_RELEASE_RE.search(body[:2000]):
        return "document_header"
    return None


class SecFiledPressReleaseConnector:
    """Acquire issuer press releases that were filed with the SEC as 8-K exhibits.

    This is deliberately not a newsroom crawler, and the family name says so. Issuer-
    controlled newsroom and IR domains cannot be established generically -- SEC exposes no
    website field, so guessing domains would reintroduce exactly the hand-picking that makes
    a manifest answer-tuned. Press releases that matter to a program are, however, routinely
    filed as exhibits to an 8-K: those are issuer-authored, CIK-resolvable, dated by the
    filing, and reachable over the documented EDGAR route already in use.

    So the coverage function is different from a newsroom's, and the difference is recorded
    rather than papered over: this reaches SEC registrants only. Private companies, non-US
    companies without SEC registration, subsidiaries whose parent files, and very early-stage
    startups are all invisible here -- which is precisely the population the milestone
    ultimately needs, so registrant status must not become the definition of "company".

    Classification is mechanical and fails closed. Registrant/CIK present, then an eligible
    filing, then an EX-99.x exhibit, then the exhibit description or its own header saying it
    is a press or news release. An exhibit that clears the first three but not the fourth is
    not admitted here at all; it remains ordinary filing evidence, which ``SecEdgarConnector``
    already covers.
    """

    source_family = "company_press_release_sec_filed"

    #: Recorded on every document: how the release reached this pipeline. A later reader
    #: should not be able to mistake this family for a crawl of issuer newsrooms.
    delivery_channel = "SEC_EXHIBIT"

    #: Which filings may carry an issuer press release as an exhibit. 8-K is the current-report
    #: form on which domestic issuers disclose material events, and furnishing the release
    #: itself as EX-99 is the standard practice. 6-K is the same thing for foreign private
    #: issuers -- literally "Report of Foreign Private Issuer", whose routine content is the
    #: press release the company published at home. Admitting only 8-K therefore did not
    #: filter by genre, it filtered by the registrant's nationality, and silently excluded
    #: every non-US issuer from a family whose whole purpose is issuer-authored news. Kept as
    #: configuration rather than inlined so widening it stays an explicit, reviewable decision.
    eligible_root_forms = frozenset({"8-K", "6-K"})

    def __init__(
        self,
        search_fn: SearchFn | None = None,
        *,
        fetch_fn: Callable[[str], str] | None = None,
        max_documents: int = 25,
        max_searches: int = 60,
        search_ledger: Path | None = None,
    ) -> None:
        self.search_fn = search_fn or _edgar_full_text_search
        self.fetch_fn = fetch_fn or SecEdgarConnector._live_fetch
        self.max_documents = max_documents
        self.max_searches = max_searches
        self.search_ledger = search_ledger
        #: Populated by ``acquire``, so the rejection reasons are auditable rather than
        #: merely subtracted counts.
        self.rejected: list[dict[str, Any]] = []

    def _eligible(self, hit: dict[str, Any], as_of_date: date) -> str | None:
        """Why this hit is not an eligible press-release candidate, or None if it is."""

        source = hit.get("_source", {})
        if not [cik for cik in source.get("ciks", []) or [] if str(cik).strip()]:
            return "no_sec_registrant_cik"
        root_forms = {str(form).upper() for form in source.get("root_forms", []) or []}
        if not root_forms & self.eligible_root_forms:
            return "form_not_eligible"
        if not _EXHIBIT_99_RE.match(str(source.get("file_type", "")).strip()):
            return "not_an_ex99_exhibit"
        if not _filed_by(hit, as_of_date):
            return "filed_after_as_of_date"
        return None

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date: date,
    ) -> SourceHealth:
        by_phrase: list[list[dict[str, Any]]] = []
        trail: list[dict[str, Any]] = []
        seen: set[str] = set()
        searched = 0
        self.rejected = []
        try:
            for target in targets:
                for phrase in SecEdgarConnector._search_phrases(target, modality_terms):
                    if searched >= self.max_searches:
                        break
                    searched += 1
                    found: list[dict[str, Any]] = []
                    returned = 0
                    for hit in self.search_fn(phrase):
                        returned += 1
                        hit_id = str(hit.get("_id", ""))
                        if hit_id and hit_id in seen:
                            continue
                        reason = self._eligible(hit, as_of_date)
                        if reason is not None:
                            self.rejected.append(_rejection(hit_id, reason, hit))
                            continue
                        seen.add(hit_id)
                        found.append(hit)
                    by_phrase.append(found)
                    trail.append(
                        {
                            "phrase": phrase,
                            "target": target.canonical_id,
                            "hits_returned": returned,
                            "hits_eligible": len(found),
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
        parsed = failures = indexed = 0
        for hit in selected:
            url, document = SecEdgarConnector._filing_url(hit)
            source = hit.get("_source", {})
            display = " ".join(source.get("display_names", []) or [])
            try:
                body = _strip_html(self.fetch_fn(url))[:40000]
                parser_status = ParserStatus.OK if body else ParserStatus.EMPTY
            except Exception:
                body = ""
                parser_status = ParserStatus.FAILED
            basis = _press_release_basis(hit, body)
            if basis is None:
                # The last mechanical step failed. Not admitted as press-release evidence and
                # not counted as a parse failure either: the document parsed fine, it simply
                # is not this genre.
                self.rejected.append(
                    _rejection(str(hit.get("_id", "")), "no_press_release_indicator", hit)
                )
                continue
            if parser_status is ParserStatus.OK:
                parsed += 1
                indexed += 1
            else:
                failures += 1
            store.add(
                source_family=self.source_family,
                source_url=url,
                publisher=display or "SEC EDGAR",
                document_type="company_press_release",
                source_tier=SourceTier.COMPANY_AUTHORED,
                raw_payload={
                    "hit": hit,
                    "text": body,
                    "delivery_channel": self.delivery_channel,
                    "classification_basis": basis,
                    "exhibit_type": source.get("file_type"),
                },
                text=f"{display} {body}".strip(),
                title=display or document,
                as_of_date=as_of_date,
                publication_date=_filing_date(source.get("file_date")),
                parser_status=parser_status,
            )
        if self.search_ledger is not None:
            self.search_ledger.parent.mkdir(parents=True, exist_ok=True)
            self.search_ledger.write_text(
                json.dumps(
                    {
                        "source_family": self.source_family,
                        "delivery_channel": self.delivery_channel,
                        "as_of_date": as_of_date.isoformat(),
                        "phrases_searched": len(trail),
                        "eligible_hits": len(hits),
                        "documents_admitted": indexed + failures,
                        "trail": trail,
                        "rejected": self.rejected,
                    },
                    indent=1,
                    sort_keys=True,
                )
                + "\n"
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
