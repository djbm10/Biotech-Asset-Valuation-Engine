"""Deterministic natural-language → :class:`SearchIntent` parser (M9C).

Rule-based on purpose. A language model reading the question would resolve targets by
plausibility, which is exactly the failure mode M9A was built to remove: this parser can
only recognize what the ontology snapshot and the closed registry vocabularies contain,
and everything else survives as a residual term rather than becoming an invented fact.

The same question always produces the same intent, so a shortlist is reproducible from
its query string alone.
"""

from __future__ import annotations

import re

from bve.se.intent.intent import INTENT_COMPILER_VERSION, IntentSpan, SearchIntent, SpanKind
from bve.se.ontology.modality import known_modalities, modality_aliases, normalize_modality
from bve.se.ontology.resolver import ResolutionStatus
from bve.se.ontology.targets import ontology_version, resolve_target
from bve.se.schemas.contracts import TargetOperator, TargetTerm

#: Longest phrase the vocabularies contain (``t cell redirecting bispecific``).
MAX_NGRAM = 5

#: English function words and query verbs. Deliberately not biomedical: nothing here
#: encodes what a target, disease, or programme is.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "any", "are", "as", "assets", "at", "be", "being", "best",
        "by", "candidates", "company", "companies", "development", "drug", "drugs", "find",
        "for", "from", "get", "in", "into", "is", "it", "list", "me", "of", "on", "or",
        "programme", "programmes", "program", "programs", "show", "someone", "that",
        "the", "their", "there", "therapies", "therapy", "to", "trials", "us", "what",
        "which", "who", "with", "against", "targeting", "targets", "target",
    }
)

_PHASE_PATTERN = re.compile(
    r"\b(?:early\s+phase\s*1|phase\s*(?:1|2|3|4|i{1,3}|iv)(?:\s*/\s*(?:1|2|3|4|i{1,3}|iv))*)\b",
    re.IGNORECASE,
)

_ROMAN_PHASES = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}

#: CT.gov's controlled status vocabulary — registry metadata, not biology.
_STATUS_ALIASES = {
    "recruiting": "RECRUITING",
    "not yet recruiting": "NOT_YET_RECRUITING",
    "active not recruiting": "ACTIVE_NOT_RECRUITING",
    "enrolling by invitation": "ENROLLING_BY_INVITATION",
    "completed": "COMPLETED",
    "terminated": "TERMINATED",
    "withdrawn": "WITHDRAWN",
    "suspended": "SUSPENDED",
    "ongoing": "RECRUITING",
    "active": "ACTIVE_NOT_RECRUITING",
}

#: Connectors that mean "both targets on one molecule" rather than "either target".
_ALL_CONNECTORS = ("and", "x", "×", "/", "plus", "bispecific")


def _tokenize(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in re.finditer(r"[^\s]+", text)]


def _clean(token: str) -> str:
    return token.strip(".,;:!?()[]\"'")


def _normalize_phase(text: str) -> list[str]:
    lowered = text.casefold()
    if lowered.startswith("early"):
        return ["EARLY_PHASE1"]
    digits = re.findall(r"\d|i{1,3}|iv", lowered.replace("phase", ""))
    phases: list[str] = []
    for digit in digits:
        value = _ROMAN_PHASES.get(digit, digit)
        token = f"PHASE{value}"
        if token not in phases:
            phases.append(token)
    return phases


def _match_status(phrase: str) -> str | None:
    return _STATUS_ALIASES.get(phrase.casefold())


def _match_modality(phrase: str) -> str | None:
    return normalize_modality(phrase)


def parse_query(query: str) -> SearchIntent:
    """Parse a question into an audited :class:`SearchIntent`.

    Matching is longest-phrase-first and non-overlapping, so ``bispecific t cell engager``
    resolves as one modality rather than as ``bispecific`` plus a separate engager term.
    """

    spans: list[IntentSpan] = []
    consumed: list[tuple[int, int]] = []
    warnings: list[str] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < c_end and end > c_start for c_start, c_end in consumed)

    # Phases first: their surface form ("phase 1/2") contains separators that would
    # otherwise be split across n-grams.
    for match in _PHASE_PATTERN.finditer(query):
        spans.append(
            IntentSpan(
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                kind=SpanKind.PHASE,
                resolved_to=",".join(_normalize_phase(match.group(0))),
                rule="phase_vocabulary",
            )
        )
        consumed.append((match.start(), match.end()))

    tokens = _tokenize(query)
    for size in range(MAX_NGRAM, 0, -1):
        for index in range(len(tokens) - size + 1):
            window = tokens[index : index + size]
            start, end = window[0][1], window[-1][2]
            if overlaps(start, end):
                continue
            phrase = " ".join(_clean(token) for token, _, _ in window).strip()
            if not phrase:
                continue

            status = _match_status(phrase)
            if status:
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.STATUS,
                        resolved_to=status,
                        rule="registry_status_vocabulary",
                    )
                )
                consumed.append((start, end))
                continue

            modality = _match_modality(phrase)
            if modality:
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.MODALITY,
                        resolved_to=modality,
                        rule="modality_vocabulary",
                    )
                )
                consumed.append((start, end))
                continue

            # Single tokens only for targets: a multi-word phrase reaching the resolver
            # would match approved *names* and pull in whole protein families.
            if size > 2 or phrase.casefold() in _STOPWORDS:
                continue
            result = resolve_target(phrase)
            if result is None:
                continue
            if result.status is ResolutionStatus.RESOLVED and result.entity is not None:
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.TARGET,
                        resolved_to=result.entity.canonical_symbol,
                        rule=result.rule,
                        explanation=(
                            result.basis.explain(result.entity.canonical_symbol)
                            if result.basis
                            else None
                        ),
                    )
                )
                consumed.append((start, end))
            elif result.status is ResolutionStatus.AMBIGUOUS:
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.AMBIGUOUS_TARGET,
                        rule=result.rule,
                        candidates=[candidate.canonical_id for candidate in result.candidates],
                    )
                )
                consumed.append((start, end))

    # Whatever no vocabulary claimed. Kept as free text, never promoted to a fact.
    for token, start, end in tokens:
        if overlaps(start, end):
            continue
        cleaned = _clean(token)
        if not cleaned or cleaned.casefold() in _STOPWORDS or cleaned.isdigit():
            continue
        spans.append(
            IntentSpan(
                text=cleaned,
                start=start,
                end=end,
                kind=SpanKind.RESIDUAL,
                rule="no_vocabulary_match",
            )
        )

    spans.sort(key=lambda span: (span.start, span.end))

    targets: list[TargetTerm] = []
    seen_targets: set[str] = set()
    for span in spans:
        if span.kind is not SpanKind.TARGET or not span.resolved_to:
            continue
        if span.resolved_to.casefold() in seen_targets:
            continue
        seen_targets.add(span.resolved_to.casefold())
        targets.append(TargetTerm(canonical_id=span.resolved_to, label=span.resolved_to))

    modalities = list(
        dict.fromkeys(
            span.resolved_to
            for span in spans
            if span.kind is SpanKind.MODALITY and span.resolved_to
        )
    )
    phases: list[str] = []
    for span in spans:
        if span.kind is SpanKind.PHASE and span.resolved_to:
            for phase in span.resolved_to.split(","):
                if phase and phase not in phases:
                    phases.append(phase)
    statuses = list(
        dict.fromkeys(
            span.resolved_to for span in spans if span.kind is SpanKind.STATUS and span.resolved_to
        )
    )
    residual_terms = list(
        dict.fromkeys(span.text for span in spans if span.kind is SpanKind.RESIDUAL)
    )
    ambiguous_terms = list(
        dict.fromkeys(span.text for span in spans if span.kind is SpanKind.AMBIGUOUS_TARGET)
    )

    operator, operator_rule = _infer_operator(query, spans)
    if len(targets) > 1:
        warnings.append(f"target operator {operator.value} inferred by {operator_rule}")
    if ambiguous_terms:
        warnings.append(
            "ambiguous terms left unresolved (escalate rather than guess): "
            + ", ".join(ambiguous_terms)
        )
    version = ontology_version()
    if version.startswith("no_snapshot"):
        warnings.append(
            "no ontology snapshot installed; no target can resolve and this intent will not compile"
        )
    if residual_terms:
        warnings.append(
            "unrecognized terms carried as free text, not as resolved criteria: "
            + ", ".join(residual_terms)
        )

    return SearchIntent(
        original_query=query,
        compiler_version=INTENT_COMPILER_VERSION,
        ontology_version=version,
        spans=spans,
        targets=targets,
        target_operator=operator,
        modalities=modalities,
        phases=phases,
        statuses=statuses,
        residual_terms=residual_terms,
        ambiguous_terms=ambiguous_terms,
        warnings=warnings,
    )


def _infer_operator(query: str, spans: list[IntentSpan]) -> tuple[TargetOperator, str]:
    """Decide whether multiple targets mean "either" or "both on one molecule".

    ``CD19xCD3`` and ``CD19 and BCMA`` mean one molecule hitting both; ``CD19 or BCMA``
    means either. The inference is recorded as a warning because it is the single most
    consequential reading of a query and the user should be able to overrule it.
    """

    target_spans = [span for span in spans if span.kind is SpanKind.TARGET]
    if len(target_spans) < 2:
        return TargetOperator.ANY, "single_target_default"
    between = query[target_spans[0].end : target_spans[-1].start].casefold()
    if re.search(r"\bor\b", between):
        return TargetOperator.ANY, "or_connector"
    if any(connector in between for connector in _ALL_CONNECTORS) or not between.strip():
        return TargetOperator.ALL, "conjunctive_connector"
    return TargetOperator.ANY, "default_disjunction"


def supported_modalities() -> tuple[str, ...]:
    """Vocabulary a question can name; useful for error messages and prompts."""

    return known_modalities()


def modality_surface_forms(canonical_id: str) -> tuple[str, ...]:
    return modality_aliases(canonical_id)
