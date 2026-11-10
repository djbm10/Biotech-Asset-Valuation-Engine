"""A concrete next action for each UNKNOWN gate decision (cycle U1).

The S&E gates answer UNKNOWN with one generic next action per gate ("Obtain specific,
authority-comparable indication evidence."). DealScreen adds a diagnostic beside each UNKNOWN
decision on a program that is not excluded:

- ``class``: one value from a closed list, the relation between the record and the buyer's
  requirement (see ``research/dealscreen_unknown_actions_v1/ACCEPTANCE.md``);
- ``observed``: the values on record as written (an empty list: nothing on record);
- ``record``: what the record holds (a sentence) and ``summary``, the same in a short phrase;
- ``fact``: the cited fact that would settle the gate, ``field``, the field an analyst asserts it in, and
  ``closes``: ``"pass"`` when that fact can only pass the gate (the indication gate never fails on indication
  evidence), ``"decide"`` when it can pass or fail it;
- ``action``: the record sentence and the settling fact, with how to enter it.

Classes come only from the frozen NCIt authority, the target and modality readers and the buyer's own
requirement. A diagnostic never changes a gate, a disposition or a rank, and never says a program is
in or out of scope: a vendor cell can be wrong, so every action names the record it read.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from bve.dealscreen import indication_relations as ir
from bve.dealscreen.importer import split_list
from bve.dealscreen.targets import isoform_number

POLICY = "DealScreen unknown-gate diagnostic v2"

NO_RECORD = "NO_RECORD"
CONFLICTING = "CONFLICTING"
UNREADABLE = "UNREADABLE"
OTHER = "OTHER"
SOURCE_NAMES_REQUIRED_TARGET = "SOURCE_NAMES_REQUIRED_TARGET"
#: The text contains the required symbol or label in a form neither the authority nor DealScreen reads
#: ("ABC1A2"-like suffixes, "isoform A2"): never called another target (review U1 D4).
SOURCE_MAY_NAME_REQUIRED_TARGET = "SOURCE_MAY_NAME_REQUIRED_TARGET"
SOURCE_NAMES_OTHER_TARGETS = "SOURCE_NAMES_OTHER_TARGETS"
#: The only mention of the required target is negated ("X negative", "not X", "X knockout"; review U1 N6).
SOURCE_STATES_NOT_REQUIRED_TARGET = "SOURCE_STATES_NOT_REQUIRED_TARGET"
SOURCE_MODALITY_UNREADABLE = "SOURCE_MODALITY_UNREADABLE"
COMBINATION_PRODUCT = "COMBINATION_PRODUCT"

#: requirement id -> (fact type, assertable field) for the fixed S&E gates.
_GATES: dict[str, tuple[str, str | None]] = {
    "strategy.indication": ("indication", "indication"),
    "strategy.therapeutic_area": ("therapeutic_area", "therapeutic_area"),
    "target.expression": ("construct_target_set", "target"),
    "modality.required": ("modality_id", "modality"),
    "evidence.phase_constraint": ("development_stage_order", "phase"),
    "evidence.minimum_stage": ("development_stage_order", "phase"),
    "identity.distinct_asset": ("identity_valid", None),
    "evidence.human_poc": ("human_poc_present", None),
    "evidence.evaluable_patients": ("evaluable_patients", None),
}
#: fact type -> the field an analyst asserts to supply it.
_FIELD_OF_FACT = {"construct_target_set": "target", "modality_id": "modality", "development_stage_order": "phase",
                  "mechanism_direction": "mechanism", "indication": "indication",
                  "therapeutic_area": "therapeutic_area"}
#: Words of target text that names nothing ("Undisclosed Target", "PROPRIETARY", "Novel target", "TAA").
_PLACEHOLDER_WORDS = frozenset({
    "undisclosed", "not", "disclosed", "unknown", "n", "a", "na", "none", "tbd", "tba", "tbc", "other", "others",
    "applicable", "available", "multiple", "various", "proprietary", "confidential", "specified", "unspecified",
    "novel", "new", "target", "targets", "antigen", "antigens", "tumor", "tumour", "associated", "taa", "taas",
    "undefined", "pending", "to", "be", "determined", "announced", "confirmed", "", "-",
    # placeholder variants (review U1 N8): a modality word, a letter or a small number names no target
    "adc", "adcs", "unnamed", "candidate", "candidates", "program", "x", "y", "z", "1", "2", "3",
    "4", "5"})
#: A required symbol after one of these, or followed by "negative", is not the target ("not X", "X-negative",
#: "formerly X"; review U1 D5).
_NEGATED = re.compile(r"\b(?:not|non|no|formerly|former|previously|ex|lacking|without)\b[\s\-]*$",
                      re.IGNORECASE)
#: "absent" before a symbol negates it only at the start of the part: in "HER2 absent CLDN18.2 positive" it closes
#: the other target's phrase (review U1 R7 F4).
_ABSENT_BEFORE = re.compile(r"^\s*absent[\s\-]*$", re.IGNORECASE)
#: Explicit absence written after the symbol (review U1 N7). Expression levels ("low", "high") and engineering
#: words ("null-Fc", "loss-of-function") name the target, not its absence (review U1 D2); "-independent" does not
#: (D4).
_NEGATION_WORDS = (r"negative|neg|non[\s\-]?expressing|knock[\s\-]?out|independent|not[\s\-]expressed|absent|"
                   r"expression[\s\-]absent")  # "not expressed", "absent" (review U1 R6 E6)
_NEGATED_AFTER = re.compile(rf"^(?:[\s\-–—]*(?:{_NEGATION_WORDS})\b|\s*\(\s*(?:{_NEGATION_WORDS}|formerly|former|"
                            r"previously)\s*\))", re.IGNORECASE)
#: A symbol stated as both negative and positive ("X negative or positive", "X neg/pos", "X-negative and -positive")
#: is not stated to be absent (review U1 R4 D3).
#: Joins between the two states: "/", "or", "and", "and/or", "&", "&/or", ",", "+", "plus", "|" or a dash (review U1
#: R6 E3). A level ("low", "high") is a second state too, so "negative or low" and "low or negative" read alike (E6).
_STATE_JOIN = r"(?:\band/or\b|&/or|/|\bor\b|\band\b|&|,|\+|\bplus\b|\||-)"
#: A second state belongs to the negated target only when nothing but punctuation, a cohort word or the end of the
#: cell follows it: "X negative, positive PD-L1" is another target's state (review U1 R6 E2).
#: A full stop ends a state only at the end of the cell: in "pos. KLX9" it closes an abbreviation (review U1 R6 E2).
_STATE_END = r"\.?(?=\s*(?:$|[,;)]|(?:cohorts?|populations?|patients|subgroups?|status|expression|disease)\b))"
_BOTH_STATES = re.compile(rf"\b(?:negative|neg)\)?\s*{_STATE_JOIN}\s*-?\s*(?:positive|pos|low|high){_STATE_END}|"
                          rf"\b(?:positive|pos|low|high)\)?\s*{_STATE_JOIN}\s*-?\s*(?:negative|neg){_STATE_END}",
                          re.IGNORECASE)
#: The second state written right after a negated part that the list split off ("X neg" + "/pos"), never a positive
#: that belongs to another target ("X negative, positive for Y"; review U1 R5 N2).
_SECOND_STATE = re.compile(rf"^\s*{_STATE_JOIN}\s*-?\s*(?:positive|pos|low|high)\b{_STATE_END}", re.IGNORECASE)
#: Every Unicode dash and hyphen, read as "-" for matching only (one character each, so positions hold; review U1
#: R6 E4).
_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]")
#: A parenthesised note that is only a negation stays with its symbol ("X (formerly)"); any other is its own part.
_PAREN_NOTE = re.compile(r"\(([^()]*)\)")
_NEGATION_ONLY = re.compile(rf"^\s*(?:{_NEGATION_WORDS}|formerly|former|previously)\s*$", re.IGNORECASE)
#: "/" between two names ("X/Y", "X/4-1BB"), never inside "and/or", "N/A" or "X6/9" (review U1 N9, D9).
_SLASH = re.compile(r"(?<=[A-Za-z0-9.\-]{2})/(?=[A-Za-z0-9][A-Za-z0-9.\-]*[A-Za-z])")
#: Other list words between two names ("X + Y", "X and Y", "X, Y"), never before "isoform" (review U1 D9).
_LIST_WORDS = re.compile(r"\s+(?:\+|&|and|plus|with)\s+|\s*,\s+(?!isoform\b)", re.IGNORECASE)
#: Pair notation between two symbols ("X.2xY", "X.1 x Y"): split before matching (review U1 D5).
_PAIR = re.compile(r"(?<=\d)\s*[x×]\s*(?=[A-Za-z]|\d[\w\-]*[A-Za-z])")
_SYMBOL_SHAPE = re.compile(r"\d|[A-Z].*[A-Z]")

TargetReader = Callable[[str], "str | None"]


def _quoted(values: Iterable[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _how(field_name: str | None) -> str:
    if field_name is None:
        return "no DealScreen field supplies it"
    return f"enter it with `assert --field {field_name}`, the source URL and a verbatim quote"


def _result(cls: str, observed: list[str], record: str, summary: str, fact: str, field_name: str | None,
            scoped: bool = True, closes: str = "decide", how: str | None = None, also: str = "",
            **extra: Any) -> dict[str, Any]:
    """One diagnostic. ``scoped`` adds "for this program" after the fact in the action. ``closes`` says whether
    the fact can only pass the gate or can pass or fail it (review U1 D12). ``how`` replaces the field's entry
    instructions; ``also`` is a further sentence after them."""
    where = " for this program" if scoped else ""
    lead = "What would pass the gate" if closes == "pass" else "What decides the gate"
    action = f"{record} {lead}: {fact}{where}; {how or _how(field_name)}.{also}"
    if closes == "pass":
        action += " The gate never fails on this evidence, so a program for another indication stays open."
    return {"class": cls, "observed": observed, **extra, "record": record, "summary": summary, "fact": fact,
            "field": field_name, "closes": closes, "action": action}


def _conflict(what: str, values: list[str], fact: str, field_name: str) -> dict[str, Any]:
    """Values on record disagree: confirming the right claim also decides the gate."""
    record = f"{what} values on record disagree: {_quoted(values)}."
    return {"class": CONFLICTING, "observed": values, "record": record,
            "summary": f"{what.lower()} values disagree", "fact": fact, "field": field_name, "closes": "decide",
            "action": (f"{record} What decides the gate: confirming the right claim (and rejecting the wrong one), "
                       f"or {fact}; {_how(field_name)}.")}


def _words(code: str) -> str:
    return code.replace("_", " ").lower()


# -- indication ---------------------------------------------------------------------------------------
def _minimal(phrases: tuple[str, ...]) -> list[str]:
    """Drop a phrase that contains another named phrase ("renal kidney" when "renal" is named)."""
    return [p for p in phrases if not any(q != p and f" {q} " in f" {p} " for q in phrases)]


def _how_read(reading: ir.NameReading) -> str:
    """The clean-ups and choices behind a reading, in words (review U1 D3, D7, D11)."""
    parts = []
    if reading.steps:
        who = "" if reading.screen_reads else ", a clean-up the gate does not apply"
        parts.append(f" once {' and '.join(reading.steps)}{who}")
    if reading.notes:
        parts.append(f" ({'; '.join(reading.notes)})")
    return "".join(parts)


def _indication_sentence(reading: ir.NameReading) -> str:
    name = f"'{reading.name}'"
    concepts = "; ".join(dict.fromkeys(lab for lab, _ in reading.concepts))
    how = _how_read(reading)
    site = (f", although it names {' and '.join(_minimal(reading.sites))}, a requested site"
            if reading.sites else "")
    return {
        ir.READS_AS_REQUESTED: f"{name} reads as {concepts} (NCIt){how}, a requested indication or a subtype",
        ir.NAMES_REQUESTED_SITE: f"{name} names {' and '.join(_minimal(reading.sites))}, a requested site, but is not "
                                 "a name the NCIt authority reads",
        ir.AMBIGUOUS_NAME: (f"{name} is not a name the NCIt authority can read"  # review U1 R7 F3
                            if reading.unread or reading.baskets
                            else f"{name} matches several NCIt concepts{how}: "
                            + "; ".join(dict.fromkeys(f"{lab} ({rel})" for lab, rel in reading.concepts))),
        ir.AMBIGUOUS_NAME_ALL_BROADER: f"{name} matches several NCIt concepts{how}, all broader than requested: "
                                       f"{concepts}",
        ir.OVERLAPS_REQUESTED: f"{name} reads as {concepts} (NCIt){how}, which is neither broader nor narrower than "
                               "requested but shares subtypes with it",
        ir.BROADER_THAN_REQUESTED: f"{name} reads as {concepts} (NCIt){how}, broader than requested",
        ir.UNDER_REQUESTED_PARENT: f"{name} reads as {concepts} (NCIt){how}, which NCIt files under a broader "
                                   "parent of a requested indication (not under the request itself) and which "
                                   f"names {' and '.join(_minimal(reading.sites)) or 'a requested site'}",
        ir.BASKET: f"{name} names no disease or site (a basket)",
        ir.DIFFERENT_DISEASE: f"{name} reads as {concepts} (NCIt){how}, neither a requested indication nor a subtype "
                              f"of one{site}",
        ir.UNREADABLE: f"{name} is not a name the NCIt authority can read",
    }[reading.category] + _partly_read(reading)


def _partly_read(reading: ir.NameReading) -> str:
    """For a list of names joined by "or" that the authority reads only in part: what it reads, by relation, and
    what it does not (review U1 R6 E1). Empty otherwise."""
    if not reading.unread and not reading.baskets:
        return ""
    read = "; ".join(dict.fromkeys(f"{lab} ({rel})" for lab, rel in reading.concepts))
    parts = []
    names = [p for p in reading.unread if not ir.is_modifier_piece(p)]
    loose = [p for p in reading.unread if ir.is_modifier_piece(p)]
    if names:
        parts.append("does not read " + " or ".join(f"'{p}'" for p in names))
    if loose:  # "severe" set apart by commas is a modifier, not a name of the list (review U1 R9 N9)
        parts.append("does not read " + " or ".join(f"'{p}'" for p in loose) + " with the name before it")
    if reading.baskets:  # review U1 R8 D2
        parts.append("reads " + " and ".join(f"'{p}'" for p in reading.baskets)
                     + " as a basket of diseases, not one name")
    # the steps are shown, so a piece set aside is never silent (review U1 R8 D8)
    how = _how_read(reading) or ", a reading the gate does not apply"
    return (f" as a whole; of the names in its 'or' list it reads {read or 'none'} and {' and '.join(parts)} "
            f"(read{how})")


#: A short phrase per indication class: what the record holds, never a verdict.
_INDICATION_SUMMARY = {
    ir.REQUEST_NOT_ONE_CONCEPT: "the buyer's requested indication is not one NCIt concept",
    ir.READS_AS_REQUESTED: "a name that reads as requested only after a clean-up the gate does not apply",
    ir.NAMES_REQUESTED_SITE: "names a requested site in a name NCIt cannot read",
    ir.AMBIGUOUS_NAME: "a name with several NCIt readings, or an 'or' list read only in part",
    ir.OVERLAPS_REQUESTED: "a disease that shares subtypes with the request",
    ir.AMBIGUOUS_NAME_ALL_BROADER: "a name whose NCIt readings are all broader than requested",
    ir.BROADER_THAN_REQUESTED: "a disease broader than requested",
    ir.UNDER_REQUESTED_PARENT: "a subtype of a broader parent of the request, naming a requested site",
    ir.BASKET: "a basket naming no disease or site",
    ir.DIFFERENT_DISEASE: "a disease neither requested nor a subtype of one",
    ir.UNREADABLE: "no name the NCIt authority reads as a whole",
    ir.NO_RECORD: "no indication on record",
}


def _restate(request: ir.Request) -> str:
    """The buyer-file change that makes an unresolved request one concept, with a name verified to resolve."""
    examples = []
    for indication, labels in request.unresolved:
        if found := ir.restatement(indication):
            examples.append(f"for '{indication}', for example '{found[0]}', which the authority reads as {found[1]} "
                            "alone")
        elif len(labels) > 1:
            examples.append(f"for '{indication}', the buyer chooses among {'; '.join(dict.fromkeys(labels))}")
    example = f" ({'; '.join(examples)})" if examples else ""
    return f"the buyer's request restated as one NCIt concept in `strategic_gap.indications`{example}"


def _request_diagnostic(names: list[str], requested: list[str], request: ir.Request) -> dict[str, Any]:
    """A requested indication the gate cannot compare: no name is compared with a partial request (review U1 D1)."""
    parts = []
    for indication, labels in request.unresolved:
        reads = (f"its name matches {len(labels)} NCIt concepts: {'; '.join(labels)}" if len(labels) > 1
                 else "no NCIt concept has that name")
        parts.append(f"'{indication}' is not one NCIt concept ({reads}), so the gate cannot pass any record "
                     "through it")
    for indication in request.condition_rules:
        parts.append(f"'{indication}' is matched by the S&E's own condition rule, which DealScreen does not read")
    resolved = [i for i in requested if i not in {u for u, _ in request.unresolved} | set(request.condition_rules)]
    record = ("The requested indication " + "; ".join(parts) + ". This diagnostic classes no record name against a "
              "request it cannot read" + (f"; the gate itself still compares names with {' or '.join(resolved)}"
                                          if resolved else "")
              + ". " + (f"On record: {_quoted(names)}." if names else "No indication on record."))
    sources = [f"naming {' or '.join(resolved)} (or a subtype)"] if resolved else []
    sources += [f"naming the indication in words the S&E rule {rule} matches" for rule in request.condition_rules]
    readings = [ir.NameReading(n, ir.REQUEST_NOT_ONE_CONCEPT).to_dict() for n in names]
    summary = _INDICATION_SUMMARY[ir.REQUEST_NOT_ONE_CONCEPT]
    if not sources:
        return _result(ir.REQUEST_NOT_ONE_CONCEPT, names, record, summary, _restate(request), None, scoped=False,
                       closes="pass", how="edit the buyer file and rerun the screen", names=readings)
    also = (f" Or, for every program, {_restate(request)}; edit the buyer file and rerun the screen."
            if request.unresolved else "")
    return _result(ir.REQUEST_NOT_ONE_CONCEPT, names, record, summary, "a cited source " + ", or ".join(sources),
                   "indication", closes="pass", also=also, names=readings)


def indication_diagnostic(names: list[str], requested: list[str]) -> dict[str, Any]:
    if not any(r.strip() for r in requested):  # review U1 N12: nothing to compare a name with
        record = ("The buyer file requests no indication, so no record name is compared. "
                  + (f"On record: {_quoted(names)}." if names else "No indication on record."))
        return _result(OTHER, names, record, "no requested indication", "a requested indication in "
                       "`strategic_gap.indications`", None, scoped=False, how="edit the buyer file and rerun the screen")
    request = ir.read_request(requested)
    if not request.complete:
        return _request_diagnostic(names, requested, request)
    readings = [ir.classify_name(n, request.codes) for n in names]
    category = min((r.category for r in readings), key=ir.ORDER.index) if readings else ir.NO_RECORD
    wanted = " or ".join(requested) or "a requested indication"
    if not readings:
        record = "No indication on record."
    else:
        lead = next(r for r in readings if r.category == category)  # the first such name in record order (D9)
        rest = len(readings) - 1
        record = _indication_sentence(lead) + (f" (and {rest} other name(s) on record)." if rest else ".")
    return _result(category, names, record, _INDICATION_SUMMARY[category], f"a cited source naming {wanted} "
                   "(or a subtype)", "indication", closes="pass", names=[r.to_dict() for r in readings])


# -- target -------------------------------------------------------------------------------------------
def _symbol_pattern(symbol: str) -> str:
    """The symbol with an optional space or hyphen where letters meet digits ("QRX 7", "QRX-7")."""
    out = ""
    for i, ch in enumerate(symbol):
        if i and ch.isdigit() != symbol[i - 1].isdigit():
            out += r"[\s\-]?"
        out += re.escape(ch)
    return out


def _required_patterns(targets: list[Any]) -> list[tuple[str, re.Pattern[str], str | None]]:
    """(display, pattern, wanted isoform) for each required symbol, label and alias. The isoform suffix is read
    without backtracking, so "X.1xY" never matches X with the isoform dropped (review U1 D5)."""
    out = []
    for t in targets:
        gene = t.canonical_id
        wanted = isoform_number(t.label) if t.label else None
        symbol = re.compile(rf"(?<![A-Za-z0-9]){_symbol_pattern(gene)}"
                            r"(?:\s*\.\s*(?P<iso>\d+)|(?:['’]s)?,?\s+isoform\s+(?P<iso2>\d+))?+"
                            r"(?![A-Za-z0-9]|-(?-i:[A-Z]{1,4}\d))",
                            re.IGNORECASE)
        out.append((gene, symbol, wanted))
        for text in [t.label, *getattr(t, "aliases", [])]:
            if text and text.casefold() != gene.casefold():
                words = [re.escape(w) for w in re.split(r"[\s\-]+", text.strip()) if w]
                pattern = re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-]*".join(words) + r"(?![A-Za-z0-9.])",
                                     re.IGNORECASE)
                out.append((text, pattern, None))
    return out


def _stems(targets: list[Any]) -> list[re.Pattern[str]]:
    """The required symbol, or label without its isoform, at a word start, followed by anything: text that may
    name the required target in a form DealScreen does not read ("ABC1A2"-like, "<label> isoform A2")."""
    out = []
    for t in targets:
        out.append(re.compile(rf"(?<![A-Za-z0-9]){_symbol_pattern(t.canonical_id)}(?!\d)", re.IGNORECASE))
        if t.label:
            stem = re.sub(r"\s*\.\s*\d+\s*$", "", t.label.strip())
            words = [re.escape(w) for w in re.split(r"[\s\-]+", stem) if w]
            if words:
                out.append(re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-]*".join(words) + r"(?!\d)", re.IGNORECASE))
    return out


def _match_required(part: str, patterns: list[tuple[str, re.Pattern[str], str | None]]) -> tuple[str, str] | None:
    """("required", how) when this part names a required target; ("isoform", note) when it names another isoform
    of a required gene; ("negated", symbol) when its only mention is negated or former; None otherwise. The gene with
    no isoform counts, and says so."""
    other = None
    part = _DASHES.sub("-", part)
    for display, pattern, wanted in patterns:
        for m in pattern.finditer(part):
            if (_NEGATED.search(part[:m.start()]) or _ABSENT_BEFORE.match(part[:m.start()])
                    or _NEGATED_AFTER.match(part[m.end():])):
                other = other or ("negated", m.group(0).strip())
                continue
            iso = m.groupdict().get("iso") or m.groupdict().get("iso2")
            if wanted and iso and iso != wanted:
                other = ("isoform", f"isoform {iso} of {display}, not isoform {wanted}")
                continue
            return "required", ("" if iso or not wanted else f" without stating isoform {wanted}")
    return other


def _paren_parts(part: str) -> list[str]:
    """The text outside parentheses, then each parenthesised note, unless the note is only a negation of the
    text before it ("KLX9 (X negative)" -> "KLX9", "X negative"; "X (formerly)" stays whole; review U1 N6)."""
    notes = [n.strip() for n in _PAREN_NOTE.findall(part) if n.strip() and not _NEGATION_ONLY.match(n)]
    outside = _PAREN_NOTE.sub(lambda m: f" {m.group(0)} " if _NEGATION_ONLY.match(m.group(1)) else " ", part)
    return [" ".join(outside.split()), *notes]


def _parts(values: list[str], separator: str) -> list[str]:
    out = []
    for value in values:
        joined = re.sub(r"\s+and/or\s+", f"{separator} ", value, flags=re.IGNORECASE)
        for part in split_list(_LIST_WORDS.sub(separator, _SLASH.sub(separator, joined)), separator):
            for piece in _paren_parts(part):
                out += [p.strip() for p in _PAIR.split(piece) if p.strip()]
    return list(dict.fromkeys(out))


def _placeholder(part: str) -> bool:
    return all(w in _PLACEHOLDER_WORDS for w in re.split(r"[^a-z0-9]+", part.casefold()))


def _not_text(negated: dict[str, str]) -> str:
    return "; ".join(f"{_quoted([p])} states it is not {symbol}" for p, symbol in negated.items())


#: Words in capitals that are a state or a negation, never a target ("CLDN18.2 NEGATIVE"; review U1 R8 D7).
_STATE_SYMBOLS = frozenset({"NEGATIVE", "NEG", "NOT", "NON", "POSITIVE", "POS", "LOW", "HIGH", "ABSENT", "NULL",
                            "EXPRESSION", "EXPRESSING", "AND", "OR",
                            # function words of a cell in capitals ("CLDN18.2 NEGATIVE IN 2L"; review U1 R9 N8)
                            "IN", "OF", "ON", "AT", "BY", "TO", "FOR", "WITH", "THE", "AS", "VS"})


def _symbols(part: str) -> set[str]:
    """Target-like symbols in a part: mixed case with a digit, or in capitals ("KLX9", "HER2", "PD-L1"); never a
    state word written in capitals."""
    return {w for w in re.findall(r"[A-Za-z0-9][\w.\-]*[\w]|[A-Za-z0-9]", part)
            if ((any(c.isupper() for c in w) and any(c.isdigit() for c in w)) or (w.isupper() and len(w) > 1))
            and w.upper() not in _STATE_SYMBOLS}


#: A grade, line, stage or cycle token is not a target, though it has a digit ("G1/G2", "2L", "IV"; review U1 R9 N8).
_NOT_TARGET_TOKEN = re.compile(r"(?i)^(?:g[1-4x]|[1-4]l|l[1-4]|grade[1-4]|stage[1-4ivx]+[a-c]?|ecog\d?|q\d+w|"
                               r"[ivx]+[a-c]?|\d+[a-c]?)$")


def _other_target(part: str, symbol: str, read: TargetReader) -> bool:
    """A second symbol in a negated part that reads as a target, or has a target's shape (letters and a digit): an
    assay ("IHC") or a disease acronym ("GC") is not one (review U1 R8 D7), nor a grade or line token (R9 N8)."""
    return any(symbol.casefold() not in w.casefold()
               and not all(_NOT_TARGET_TOKEN.match(t) for t in re.split(r"[/,]+", w) if t)
               and (any(c.isdigit() for c in w) or read(w))
               for w in _symbols(part))


def _both_states(part: str, values: list[str]) -> bool:
    """The part itself states both negative and positive, or the second state follows it directly in its cell.
    Another target's "negative or positive" elsewhere in the cell does not count (review U1 R5 N2)."""
    part = _DASHES.sub("-", " ".join(part.split()))
    if len(_symbols(part)) > 1:  # "X negative KLX9 neg/pos": the second state is the other symbol's (review U1 R6 E2)
        return False
    if _BOTH_STATES.search(part):
        return True
    for raw in values:
        value, seek = _DASHES.sub("-", " ".join(raw.split())), part
        if seek not in value:  # a part rebuilt around a parenthesis: compare without them
            value, seek = re.sub(r"\s*[()]\s*", " ", value).strip(), re.sub(r"\s*[()]\s*", " ", seek).strip()
        start = value.find(seek)
        while start != -1:
            if _SECOND_STATE.match(value[start + len(seek):]):
                return True
            start = value.find(seek, start + 1)
    return False


def target_diagnostic(values: list[str], conflicting: bool, targets: list[Any], read: TargetReader,
                      separator: str) -> dict[str, Any]:
    required_ids = {t.canonical_id for t in targets}
    wanted = " or ".join(f"{t.canonical_id} ({t.label})" if t.label else t.canonical_id for t in targets)
    fact = "a cited construct-level target list"
    if not values:
        return _result(NO_RECORD, [], "No target on record.", "no target on record", fact, "target")
    if conflicting:
        return _conflict("Target", values, fact, "target")
    patterns, stems = _required_patterns(targets), _stems(targets)
    parts = _parts(values, separator)
    readings = {p: read(p) for p in parts}
    matches = {p: ("required", "") if readings[p] in required_ids else _match_required(p, patterns) for p in parts}
    # a target stated both negative and another state ("X negative or low", "X neg/pos") is named, whatever the
    # order of the states (review U1 R6 E6)
    matches = {p: ("required", "") if m and m[0] == "negated" and readings[p] is None and _both_states(p, values)
               else m for p, m in matches.items()}
    named = {p: m[1] for p, m in matches.items() if m and m[0] == "required"}
    isoforms = {p: m[1] for p, m in matches.items() if m and m[0] == "isoform"}
    negated = {p: m[1] for p, m in matches.items()
               if m and m[0] == "negated" and readings[p] is None and not _both_states(p, values)}
    placeholders = [p for p in parts if readings[p] is None and _placeholder(p)]
    maybe = [p for p in parts if p not in named and p not in isoforms and p not in negated and readings[p] is None
             and p not in placeholders and any(s.search(p) for s in stems)]
    unread = [p for p in parts if readings[p] is None and p not in named and p not in isoforms
              and p not in negated and p not in placeholders and p not in maybe]
    others = [f"{p} ({readings[p]})" if readings[p] and readings[p] != p else p for p in parts
              if p not in named and ((readings[p] and readings[p] not in required_ids) or p in isoforms)]
    others = [o + (f" ({isoforms[o]})" if o in isoforms else "") for o in others]
    symbols = " or ".join(t.canonical_id for t in targets)
    unread_names = [p for p in unread if _SYMBOL_SHAPE.search(p)]
    notes = ([f"not read as a target: {_quoted(p for p in unread if p not in unread_names)}"]
             if any(p not in unread_names for p in unread) else [])
    notes += [_not_text(negated)] if negated else []
    if named:
        how = "".join(sorted(set(named.values())))
        extra = notes + ([f"may name it in a form DealScreen does not read: {_quoted(maybe)}"] if maybe else [])
        rest = [p for p in parts if p not in named]
        why = f"; also on record: {_quoted(rest)}" if rest else ""
        return _result(SOURCE_NAMES_REQUIRED_TARGET, values,
                       f"{_quoted(named)} names {wanted}{how}, but no target set was built from it{why}"
                       + (f" ({'; '.join(extra)})" if extra else "") + ".",
                       "names the required target, but no target set was built", fact, "target")
    if maybe:
        rest = [p for p in parts if p not in maybe]
        also = f"; also on record: {_quoted(rest)}" if rest else ""
        return _result(SOURCE_MAY_NAME_REQUIRED_TARGET, values,
                       f"{_quoted(maybe)} contains {symbols} or its name, in a form neither the target "
                       f"authority nor DealScreen reads; the requirement is {wanted}{also}.",
                       "the required target in a form DealScreen does not read", fact, "target")
    if others or unread_names:
        sentences = [f"The record names {', '.join(others)}; none is {wanted}."] if others else []
        if unread_names:
            lead = "It also names" if others else "The record names"
            sentences.append(f"{lead} {_quoted(unread_names)}, which the target authority does not read; "
                             + ("it is not" if len(unread_names) == 1 else "none is")
                             + f" written as {symbols} or its name.")
        record = " ".join(sentences)
        if notes:
            record = f"{record[:-1]} ({'; '.join(notes)})."
        return _result(SOURCE_NAMES_OTHER_TARGETS, values, record, "names other targets only", fact, "target")
    if negated:
        # a negated part that names a second symbol: say so, never "no other target" (review U1 R7 F5)
        crowded = [p for p in negated if _other_target(_DASHES.sub("-", p), negated[p], read)]
        tail = (f"; {_quoted(crowded)} also names another target, which DealScreen does not read apart from it"
                if crowded else "; the record names no other target the authority reads")
        return _result(SOURCE_STATES_NOT_REQUIRED_TARGET, values, f"{_not_text(negated)}{tail}.",
                       "states it is not the required target", fact, "target")
    what = ("names no target" + (f" ({_quoted(placeholders)} is a placeholder)" if placeholders else "")
            if not unread else "names no target the authority reads")
    return _result(UNREADABLE, values, f"{_quoted(values)} {what}.", "no target the authority reads", fact, "target")


# -- modality and phase --------------------------------------------------------------------------------
def modality_diagnostic(values: list[str], conflicting: bool, combination: bool, allowed: list[str]) -> dict[str, Any]:
    words = [_words(a) for a in allowed]
    requirement = f" (the requirement: {'one of ' if len(words) > 1 else ''}{', '.join(words)})" if words else ""
    fact = f"a cited modality for the whole product{requirement}"
    if not values:
        return _result(NO_RECORD, [], "No modality on record.", "no modality on record", fact, "modality",
                       scoped=False)
    if conflicting:
        return _conflict("Modality", values, fact, "modality")
    if combination:
        return _result(COMBINATION_PRODUCT, values,
                       f"{_quoted(values)} is one modality stated for a combination of products.",
                       "one modality stated for a combination", fact, "modality", scoped=False)
    return _result(SOURCE_MODALITY_UNREADABLE, values, f"{_quoted(values)} is not a modality the authority can type.",
                   "a modality the authority cannot type", fact, "modality", scoped=False)


def phase_diagnostic(values: list[str], conflicting: bool) -> dict[str, Any]:
    fact = "a cited development phase"
    if not values:
        return _result(NO_RECORD, [], "No phase on record.", "no phase on record", fact, "phase")
    if conflicting:
        return _conflict("Phase", values, fact, "phase")
    return _result(UNREADABLE, values, f"{_quoted(values)} is not a phase label the profile reads.",
                   "a phase label the profile does not read", fact, "phase")


def other_diagnostic(values: list[str], field_name: str | None, generic: str | None,
                     fact_type: str | None = None) -> dict[str, Any]:
    """Any other gate. With no assertable field DealScreen reads no value for it, so it says that rather than
    "nothing on record" (review U1 D10)."""
    if field_name:
        record = f"On record: {_quoted(values)}." if values else "Nothing on record."
        summary = "a value on record (see the Diligence sheet)" if values else "nothing on record"
        return _result(OTHER, values, record, summary, f"a cited {_words(field_name)} value", field_name,
                       scoped=False)
    record = f"DealScreen maps no landscape field to this gate's fact{f' ({fact_type})' if fact_type else ''}."
    return {"class": OTHER, "observed": values, "record": record, "summary": "no DealScreen field for this fact",
            "fact": None, "field": None, "closes": "decide",
            "action": f"{record} S&E: {generic or 'see the rationale'}"}


# -- entry point ---------------------------------------------------------------------------------------
def _fact_and_field(requirement_id: str, problem: Any) -> tuple[str | None, str | None]:
    if requirement_id in _GATES:
        return _GATES[requirement_id]
    for requirement in problem.strategic_gap.required_biology:
        if requirement.requirement_id == requirement_id:
            return requirement.fact_type, _FIELD_OF_FACT.get(requirement.fact_type)
    return None, None


def diagnose(decisions: list[dict[str, Any]], *, claims: list[Any], facts: list[Any],
             unreadable: list[dict[str, Any]], problem: Any, read_target: TargetReader,
             separator: str) -> dict[str, dict[str, Any]]:
    """requirement id -> diagnostic, for each UNKNOWN decision. ``claims`` are the claims the screen read
    (rejected claims dropped, confirmed findings and active assertions added)."""
    out: dict[str, dict[str, Any]] = {}
    by_type = {f.fact_type: f for f in facts}
    gap = problem.strategic_gap
    for decision in decisions:
        if (decision.get("analyst_override") or decision["status"]) != "UNKNOWN":
            continue
        requirement_id = decision["requirement_id"]
        fact_type, field_name = _fact_and_field(requirement_id, problem)
        values = list(dict.fromkeys(c.value_as_written for c in claims if field_name and c.field == field_name))
        fact = by_type.get(fact_type) if fact_type else None
        conflicting = bool(fact is not None and fact.contradicting_claim_ids)
        if requirement_id == "strategy.indication":
            names = list(dict.fromkeys(n for v in values for n in split_list(v, separator)))  # record order (D9)
            diagnostic = indication_diagnostic(names, list(gap.indications))
        elif requirement_id == "target.expression" and (fact is None or conflicting):
            diagnostic = target_diagnostic(values, conflicting, list(gap.target_expression.targets), read_target,
                                           separator)
        elif requirement_id == "modality.required" and (fact is None or conflicting):
            combination = any(u["field"] == "modality" and "combination" in str(u.get("reason", ""))
                              for u in unreadable)
            diagnostic = modality_diagnostic(values, conflicting, combination, list(gap.modalities))
        elif requirement_id in {"evidence.phase_constraint", "evidence.minimum_stage"} and (fact is None or conflicting):
            diagnostic = phase_diagnostic(values, conflicting)
        else:
            diagnostic = other_diagnostic(values, field_name, decision.get("next_action"), fact_type)
        out[requirement_id] = {**diagnostic, "policy": POLICY}
    return out


__all__ = ["COMBINATION_PRODUCT", "CONFLICTING", "NO_RECORD", "OTHER", "POLICY", "SOURCE_MAY_NAME_REQUIRED_TARGET",
           "SOURCE_MODALITY_UNREADABLE", "SOURCE_NAMES_OTHER_TARGETS", "SOURCE_NAMES_REQUIRED_TARGET", "UNREADABLE",
           "diagnose", "indication_diagnostic", "modality_diagnostic", "other_diagnostic", "phase_diagnostic",
           "target_diagnostic"]
