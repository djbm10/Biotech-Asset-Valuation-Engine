"""Deterministic natural-language → :class:`SearchIntent` parser (M9C).

Rule-based on purpose. A language model reading the question would resolve targets by
plausibility, which is exactly the failure mode M9A was built to remove: this parser can
only recognize what the ontology snapshot and the closed registry vocabularies contain,
and everything else survives as a residual term rather than becoming an invented fact.

The same question always produces the same intent, so a shortlist is reproducible from
its query string alone.

**A scientifically meaningful phrase gets one of three fates, never a fourth.** It is
compiled into a constraint the gate can enforce, or reported unresolved by name, or the
question is refused. What it must never do is slip into residual free text while the run
proceeds as though the whole question had been applied — that failure is invisible from the
output, which makes it worse than any refusal. Phrases too vague to mean one thing
("promising", "effective") are not scientific phrases and stay residual on purpose.
"""

from __future__ import annotations

import re

from bve.se.intent.intent import INTENT_COMPILER_VERSION, IntentSpan, SearchIntent, SpanKind
from bve.se.ontology.modality import known_modalities, modality_aliases, normalize_modality
from bve.se.ontology.resolver import ResolutionStatus
from bve.se.ontology.targets import ontology_version, resolve_target
from bve.se.schemas.contracts import PhaseConstraintOperator, TargetOperator, TargetTerm

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

#: The separators a person actually writes a phase range with. "phase 1-2" used to match
#: only "phase 1" and drop the rest in silence, which is the dangerous failure here: the
#: phase gate is EXACT, so half a range is a different question with no sign it was misread.
_PHASE_SEPARATOR = r"(?:\s*[/\-‐-―]\s*|\s+(?:to|and|or)\s+)"
_PHASE_NUMERAL = r"(?:1|2|3|4|i{1,3}|iv)"
_PHASE_PATTERN = re.compile(
    rf"\b(?:early\s+phase\s*1|phase\s*{_PHASE_NUMERAL}(?:{_PHASE_SEPARATOR}{_PHASE_NUMERAL})*)\b",
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

#: Phrases that state, exactly, "there is efficacy evidence from humans" — the one thing
#: ``EvidenceFloor.human_poc_required`` means and the gate engine already checks against an
#: asset's ``human_poc_present`` fact.
#:
#: The list is closed and every entry carries its own "in humans" qualifier. Enthusiasm is
#: not a contract term: "promising", "effective" and "strong data" say nothing about who was
#: dosed, so they stay residual rather than inventing an evidence floor nobody asked for.
_HUMAN_POC_PHRASES = frozenset(
    {
        "human efficacy",
        "human efficacy data",
        "human efficacy evidence",
        "human proof of concept",
        "human poc",
        "efficacy in humans",
        "proof of concept in humans",
        "clinical efficacy",
        "clinical proof of concept",
        "human clinical efficacy",
    }
)

#: Phrases meaning "entered human clinical development", and nothing more precise.
#:
#: This maps onto ``EvidenceFloor.minimum_stage``, which the gate reads as
#: ``development_stage_order >= PHASE_1`` — an exact generic floor that admits every
#: clinical phase equally. It must never become a ``PhaseConstraint``: the question did not
#: name a phase, and the phase gate is EXACT, so guessing one would answer something else.
_CLINICAL_STAGE_PHRASES = frozenset(
    {
        "clinical stage",
        "clinical-stage",
        "in clinical development",
        "in the clinic",
    }
)

#: The stage floor a clinical-stage phrase compiles to, in ``gates.engine._STAGE_ORDER``
#: terms. PRECLINICAL and DISCOVERY sit below it; every clinical phase sits at or above.
CLINICAL_STAGE_FLOOR = "PHASE_1"

#: Head nouns that make a phrase a disease *class* rather than a disease.
#:
#: A class cannot be enforced: the strategic-sandbox gate tests membership of an asset's own
#: ``indication`` fact, which reads "systemic lupus erythematosus", never "autoimmune
#: disease". Compiling the class into that IN-list would build a constraint that can never
#: match and would send every asset to review for a reason the user never stated. So the
#: phrase is escalated by name instead.
#:
#: Deliberately only self-declaring class words. A bare disease name ("myeloma") is still
#: unrecognized here and still becomes free text — closing that needs a disease vocabulary,
#: and the published ontology snapshot contains TARGET and DRUG entities only.
_DISEASE_CLASS_HEADS = frozenset(
    {"disease", "diseases", "disorder", "disorders", "syndrome", "syndromes",
     "indication", "indications"}
)

#: Connectors that mean "both targets on one molecule" rather than "either target".
_ALL_CONNECTORS = ("and", "x", "×", "/", "plus", "bispecific")


#: Separators *inside* one whitespace token that join two targets: "CD19/BCMA", "CD19xBCMA".
#: This is the normal way a dual-target programme is written, and reading it as a single
#: unknown token resolved neither target and refused the whole question.
#:
#: The ``x`` form is deliberately narrow — an ``x`` between a symbol character and an
#: uppercase letter — so it cannot cut a name that merely contains the letter.
_TARGET_JOIN = re.compile(r"(?<=[0-9A-Za-z])(?:/|×|x(?=[A-Z]))")

#: Words that join targets and are never targets themselves. Without this, the ``x`` in
#: "CD19 x BCMA" resolves to a gene, and the engine asserts a third target the question
#: never named.
_CONNECTOR_TOKENS = frozenset({"x", "×", "/", "and", "or", "plus", "vs"})

#: Words that *state* "one molecule must hit every target named", rather than leaving it to
#: be inferred from whatever connector the question happened to use. The inference falls
#: back to ANY on an unrecognized connector, so a question that says "dual" and is read as
#: "either" would return single-target assets under a dual-target heading.
_CONJUNCTION_WORDS = frozenset({"dual", "dual-targeting", "dual-targeted", "bi-specific targeting"})


def _tokenize(text: str) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    for match in re.finditer(r"[^\s]+", text):
        token, offset = match.group(0), match.start()
        cursor = 0
        for separator in _TARGET_JOIN.finditer(token):
            piece = token[cursor : separator.start()]
            if piece:
                tokens.append((piece, offset + cursor, offset + separator.start()))
            cursor = separator.end()
        piece = token[cursor:]
        if piece:
            tokens.append((piece, offset + cursor, offset + len(token)))
    return tokens


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


#: Phrases that turn a named phase into a floor rather than an exact request. Anything not
#: listed here is read as EXACT, because admitting later phases is the error that costs a
#: user real money.
_MINIMUM_PREFIX = re.compile(r"(?:at\s+least|minimum\s+(?:of\s+)?|no\s+earlier\s+than)\s*$", re.IGNORECASE)
_MINIMUM_SUFFIX = re.compile(
    r"^\s*(?:\+|or\s+later|or\s+beyond|or\s+above|or\s+higher|or\s+more\s+advanced"
    r"|and\s+later|and\s+above|onwards?)",
    re.IGNORECASE,
)


def _minimum_cue(query: str, start: int, end: int) -> tuple[int, int] | None:
    """Return the span of a minimum cue attached to the phase at ``start:end``."""

    if match := _MINIMUM_SUFFIX.match(query[end:]):
        return (end, end + match.end())
    if match := _MINIMUM_PREFIX.search(query[:start]):
        return (match.start(), start)
    return None


def _match_status(phrase: str) -> str | None:
    return _STATUS_ALIASES.get(phrase.casefold())


def _phrase_key(phrase: str) -> str:
    """Casefold and flatten the separators a person writes, so "clinical-stage" matches."""

    return " ".join(re.split(r"[\s\-‐-―]+", phrase.casefold())).strip()


def _match_evidence(phrase: str) -> tuple[str, str] | None:
    """Match a controlled evidence phrase, returning ``(field, rule)``.

    Only exact controlled phrases match. A near-miss resolves to nothing and survives as
    residual text, which is the honest outcome: an evidence floor the user did not state is
    worse than one the engine admits it did not understand.
    """

    key = _phrase_key(phrase)
    if key in _HUMAN_POC_PHRASES:
        return ("human_poc_required", "evidence_human_poc_vocabulary")
    if key in _CLINICAL_STAGE_PHRASES:
        return ("minimum_stage", "evidence_clinical_stage_vocabulary")
    return None


def _match_disease_class(phrase: str) -> bool:
    """Whether this phrase names a disease *class* the engine cannot enforce.

    A single bare class word ("disease") is a word, not a constraint, so it takes at least
    a qualifier in front of it before the phrase is escalated.
    """

    words = _phrase_key(phrase).split()
    if len(words) < 2 or words[-1] not in _DISEASE_CLASS_HEADS:
        return False
    return not any(word in _STOPWORDS for word in words)


def _match_modality(phrase: str) -> str | None:
    """Resolve a modality phrase, tolerating the plural a question is normally asked in.

    "bispecifics" is the same request as "bispecific", but the vocabulary holds labelling
    spellings and a query that names no recognized modality refuses to compile at all. The
    depluralization lives here, in the question layer, rather than in the vocabulary, so the
    gating and labelling paths keep matching exactly what a source wrote.
    """

    if modality := normalize_modality(phrase):
        return modality
    for plural, singular in (("ies", "y"), ("es", ""), ("s", "")):
        if phrase.casefold().endswith(plural):
            if modality := normalize_modality(phrase[: -len(plural)] + singular):
                return modality
    return None


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
    minimum_cues = 0
    for match in _PHASE_PATTERN.finditer(query):
        start, end = match.start(), match.end()
        cue = _minimum_cue(query, start, end)
        if cue is not None:
            minimum_cues += 1
            start, end = min(start, cue[0]), max(end, cue[1])
        spans.append(
            IntentSpan(
                text=query[start:end],
                start=start,
                end=end,
                kind=SpanKind.PHASE,
                resolved_to=",".join(_normalize_phase(match.group(0))),
                rule="phase_minimum_vocabulary" if cue is not None else "phase_vocabulary",
            )
        )
        # The cue text is consumed with the phase so "or later" cannot fall through to the
        # n-gram pass and end up as a free-text indication.
        consumed.append((start, end))

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

            evidence = _match_evidence(phrase)
            if evidence:
                field, rule = evidence
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.EVIDENCE,
                        resolved_to=field,
                        rule=rule,
                    )
                )
                consumed.append((start, end))
                continue

            if _match_disease_class(phrase):
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.UNRESOLVED_SCIENTIFIC,
                        rule="disease_class_not_enforceable",
                    )
                )
                consumed.append((start, end))
                continue

            if phrase.casefold() in _CONJUNCTION_WORDS:
                spans.append(
                    IntentSpan(
                        text=phrase,
                        start=start,
                        end=end,
                        kind=SpanKind.TARGET_LOGIC,
                        resolved_to="ALL",
                        rule="conjunction_vocabulary",
                    )
                )
                consumed.append((start, end))
                continue

            # Single tokens only for targets: a multi-word phrase reaching the resolver
            # would match approved *names* and pull in whole protein families.
            if size > 2 or phrase.casefold() in _STOPWORDS:
                continue
            if phrase.casefold() in _CONNECTOR_TOKENS:
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
    if minimum_cues and len(phases) == 1:
        phase_operator = PhaseConstraintOperator.MINIMUM
    elif len(phases) > 1:
        phase_operator = PhaseConstraintOperator.ANY_OF
        if minimum_cues:
            warnings.append(
                "a 'later/at least' phase cue was read alongside several phases; the "
                "constraint was kept as the allowed set " + ", ".join(phases)
            )
    else:
        phase_operator = PhaseConstraintOperator.EXACT
    statuses = list(
        dict.fromkeys(
            span.resolved_to for span in spans if span.kind is SpanKind.STATUS and span.resolved_to
        )
    )
    human_poc_required = any(
        span.kind is SpanKind.EVIDENCE and span.resolved_to == "human_poc_required"
        for span in spans
    )
    minimum_stage = (
        CLINICAL_STAGE_FLOOR
        if any(
            span.kind is SpanKind.EVIDENCE and span.resolved_to == "minimum_stage"
            for span in spans
        )
        else None
    )
    unresolved_scientific_terms = list(
        dict.fromkeys(
            span.text for span in spans if span.kind is SpanKind.UNRESOLVED_SCIENTIFIC
        )
    )
    residual_terms = list(
        dict.fromkeys(span.text for span in spans if span.kind is SpanKind.RESIDUAL)
    )
    ambiguous_terms = list(
        dict.fromkeys(span.text for span in spans if span.kind is SpanKind.AMBIGUOUS_TARGET)
    )

    operator, operator_rule = _infer_operator(query, spans)
    conjunction_stated = any(span.kind is SpanKind.TARGET_LOGIC for span in spans)
    if conjunction_stated and operator_rule != "or_connector":
        # The user wrote the conjunction down. Only an explicit "or" can contradict it, and
        # that contradiction is a blocker rather than something to resolve by precedence.
        operator, operator_rule = TargetOperator.ALL, "conjunction_stated"
    if len(targets) > 1:
        # "inferred" is a claim about where the reading came from. When the question said
        # "dual" the engine inferred nothing, and saying otherwise invites the user to
        # argue with a guess they actually made themselves.
        verb = "stated by" if operator_rule == "conjunction_stated" else "inferred by"
        warnings.append(f"target operator {operator.value} {verb} {operator_rule}")
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
    # The unenforceable-phrase warning is deliberately *not* appended here: whether the
    # phrase is still unapplied depends on what the caller supplies at compile time, so it
    # is composed by ``SearchIntent.warnings_for`` instead of frozen at parse time.
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
        phase_operator=phase_operator,
        conjunction_stated=conjunction_stated,
        statuses=statuses,
        human_poc_required=human_poc_required,
        minimum_stage=minimum_stage,
        unresolved_scientific_terms=unresolved_scientific_terms,
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
