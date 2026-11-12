"""How an indication name on record relates to the buyer's requested indications (cycle U1).

Used only to explain an UNKNOWN indication gate; the gate itself is unchanged. Relations come from the frozen S&E
NCIt authority and from the requested concepts' own names. Each rule below exists because the U1 review found a
statement that misread the authority or the record (``research/dealscreen_unknown_actions_v1/REVIEW.md``):

- The request. The gate compares names only with a requested indication that is exactly one NCIt concept
  (``disease_id``). A request that is not ("kidney cancer" matches several concepts), or that the S&E matches by its
  own condition rule, gets no relation at all: no record name is called "not requested" against a request that
  cannot be compared (D1).
- The name. The authority's name index may give one concept, several, or none. When several match and one of
  them is named exactly by its label, that concept is the reading ("Adenocarcinoma" is Adenocarcinoma, not one of
  its subtypes; D7). A population the index adds and the record does not state ("Childhood ...") is dropped by
  reading the concept's own ancestor of the same name without it (D7).
- Clean-ups. DealScreen's readings that the screen applies (``indications.indication_readings``) come first. Then
  U1's own, which the gate does not apply and every sentence shows: British spelling read as American, an inner
  acronym of the words just before it ("Head and Neck (HN)", checked letter by letter; "(RCC)" after
  "Adenocarcinoma" is not one, D3), and leading extent qualifiers.
- The ancestor graph: a concept is requested or a subtype, broader, sharing subtypes, or neither.
- Site phrases. NCIt names its by-site concepts "<site> Neoplasm" or "<site> Disorder". The sites of a requested
  concept are those phrases, taken whole ("head and neck", never "head"), from its ancestors that are not also
  morphology concepts (B-cell and lymphocytic neoplasms are lineages, not sites), where they occur in the
  concept's own names bounded by generic words (D2). An abbreviation of such a phrase among the concept's own
  names ("hn") is a site phrase too (D8). On the record side a site counts only where the name puts it: not
  after an exclusion ("excl.", "no", "ex-", "w/o", "apart from", "(... excluded)"), not as a metastatic site
  ("with liver metastases") and not as a type ("renal-type") (D6, J2).
- A name the authority reads as a concept that is neither requested, broader nor overlapping is a different
  disease, even when it names a requested site ("Renal Cyst"): the authority's reading outranks a shared word
  (J1). A requested site counts as a lead only in a name the authority cannot read.

No program, company, disease or target word from any landscape is written here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from functools import lru_cache

from bve.dealscreen.indications import (
    EXTENT_QUALIFIERS,
    GENERIC_REMAINDERS,
    QUALIFIERS,
    indication_readings,
)

READS_AS_REQUESTED = "READS_AS_REQUESTED"
NAMES_REQUESTED_SITE = "NAMES_REQUESTED_SITE"
AMBIGUOUS_NAME = "AMBIGUOUS_NAME"
AMBIGUOUS_NAME_ALL_BROADER = "AMBIGUOUS_NAME_ALL_BROADER"
OVERLAPS_REQUESTED = "OVERLAPS_REQUESTED"
BROADER_THAN_REQUESTED = "BROADER_THAN_REQUESTED"
#: Under a broader concept that is a direct parent of a requested concept, and naming a requested site, but not
#: under the request itself (a stage concept under the parent of a requested histology subtype; review U1 N1).
UNDER_REQUESTED_PARENT = "UNDER_REQUESTED_PARENT"
BASKET = "BASKET"
DIFFERENT_DISEASE = "DIFFERENT_DISEASE"
UNREADABLE = "UNREADABLE"
NO_RECORD = "NO_RECORD"
#: A requested indication is not exactly one NCIt concept, so no name is compared with the request (review D1).
REQUEST_NOT_ONE_CONCEPT = "REQUEST_NOT_ONE_CONCEPT"
#: A program's class is the first of its names' classes in this order.
ORDER: tuple[str, ...] = (REQUEST_NOT_ONE_CONCEPT, READS_AS_REQUESTED, NAMES_REQUESTED_SITE, AMBIGUOUS_NAME,
                          OVERLAPS_REQUESTED, AMBIGUOUS_NAME_ALL_BROADER, BROADER_THAN_REQUESTED,
                          UNDER_REQUESTED_PARENT, BASKET,
                          DIFFERENT_DISEASE, UNREADABLE, NO_RECORD)

REQUESTED, BROADER = "requested or a subtype", "broader than requested"
#: Neither broader nor narrower, but the two concepts share a subtype ("colon carcinoma" and "colorectal
#: adenocarcinoma" share "colon adenocarcinoma"): not a different disease.
OVERLAPS = "shares subtypes with a requested concept"
#: A sibling under a request's own site-level parent that names a requested site (review U1 N1).
SIBLING = "under a broader parent of a requested concept"
DIFFERENT = "not requested"

_FUNCTION = frozenset({"of", "the", "and", "or", "nos", "in", "with", "by", "to", "a", "an", "including", "for",
                       "at", "on"})
_POPULATION = frozenset({"adult", "adults", "pediatric", "paediatric", "childhood", "child", "children",
                         "patient", "patients", "participant", "participants", "subjects"})
#: Population words NCIt puts in a concept label ("Childhood Renal Cell Carcinoma", "Adult Hepatocellular Carcinoma").
_LABEL_POPULATION = frozenset({"adult", "childhood", "pediatric", "paediatric", "child", "juvenile", "infantile",
                               "adolescent", "neonatal"})
#: Words that name no disease or site: tumour and generic heads, extent and population words.
_BASKET_HEADS = frozenset({"tumor", "tumors", "tumour", "tumours", "neoplasm", "neoplasms", "neoplasia",
                           "neoplastic", "cancer", "cancers", "malignancy", "malignancies", "malignant",
                           "carcinoma", "carcinomas", "disease", "diseases", "disorder", "disorders",
                           "condition", "conditions"})
_PLURAL_HEADS = frozenset(h for h in _BASKET_HEADS if h.endswith("s"))
_BASKET_EXTRA = frozenset({"solid", "locally", "stage", "late", "other", "any", "all", "comers", "various",
                           "multiple", "selected", "select", "certain", "i", "ii", "iii", "iv"})
_QUALIFIER_WORDS = frozenset(w for q in (*EXTENT_QUALIFIERS, *QUALIFIERS) for w in re.split(r"[\s\-]+", q))
_BASKET_WORDS = _BASKET_HEADS | _BASKET_EXTRA | _QUALIFIER_WORDS | _POPULATION | _FUNCTION
#: Never a site word, whatever an ancestor is called.
_NOT_SITE = (_FUNCTION | GENERIC_REMAINDERS | _QUALIFIER_WORDS | _POPULATION | _BASKET_HEADS
             | frozenset({"primary", "secondary", "benign"}))
#: Words that may not appear in a site phrase (function words may: "head and neck"); a cell type is not a site
#: ("liver cells").
_NOT_IN_SITE = (_NOT_SITE - _FUNCTION) | frozenset({"non", "cell", "cells", "cellular"}) | frozenset({
    # cell lineages, differentiation and states, which NCIt files under by-site nodes but are not places
    # (review U1 N5); generic biology, no landscape word
    "neuroendocrine", "myoepithelial", "epithelial", "stromal", "histiocytic", "lymphoid", "myeloid", "mesenchymal",
    "germ", "differentiated", "lineage", "related", "associated", "induced", "syndrome", "hematologic",
    "hematopoietic", "lymphoproliferative", "myeloproliferative", "transplant", "post"})
#: NCIt's by-site naming: "<site> Neoplasm", "Malignant <site> Neoplasm", "Non-Neoplastic <site> Disorder".
_SITE_SHAPE = re.compile(r"^(?:(?:malignant|benign|non neoplastic|primary|secondary) )?(?P<site>[a-z0-9 ]+?) "
                         r"(?:neoplasm|neoplasms|disorder|disorders)$")

# -- record-side reading: exclusions and roles (review D6, J2) -------------------------------------------
#: Everything after one of these, within its clause, is excluded ("solid tumors other than renal").
_CUTS = ("other than", "excluding", "excl", "except", "exclusive of", "without", "w o", "apart from", "besides",
         "not including", "not in", "outside")
#: The word after one of these is excluded ("non-renal", "ex-renal", "no renal", "not renal"); "not"
#: scopes over one word only, so "not previously treated renal cancer" still names renal.
_NEXT_WORD = frozenset({"non", "ex", "no", "not"})
#: A clause that contains one of these is excluded ("(renal cancer excluded)").
_POST = frozenset({"excluded", "excepted", "exempted"})
#: A site followed by one of these is not the disease site ("liver metastases", "renal-type").
_ROLE_AFTER = frozenset({"metastasis", "metastases", "metastatic", "mets", "type", "like", "outlet",
                         # a site used for a therapy, a toxicity or a state, not the disease (review U1 N5)
                         "therapy", "therapies", "treatment", "resistant", "refractory", "toxicity", "toxicities",
                         "associated", "related", "induced", "insufficiency"})
#: A site after one of these is a metastatic site ("metastatic to the liver").
_ROLE_BEFORE = ("metastatic to", "metastases to", "metastasis to", "metastases in", "metastatic in", "spread to")
#: British spellings read as American (a DealScreen clean-up the gate does not apply). Spelling only.
_SPELLING = (("oesophag", "esophag"), ("haemat", "hemat"), ("haem", "hem"), ("anaem", "anem"),
             ("leukaem", "leukem"), ("paediatr", "pediatr"), ("oedem", "edem"), ("oestr", "estr"),
             ("gynaec", "gynec"), ("coeli", "celi"), ("ischaem", "ischem"), ("foet", "fet"), ("tumour", "tumor"),
             ("orthopaed", "orthoped"), ("diarrhoea", "diarrhea"), ("glycaem", "glycem"), ("septicaem", "septicem"),
             ("uraem", "urem"), ("lipaem", "lipem"))
_PAREN = re.compile(r"\s*\(([^()]{1,12})\)")
#: A hyphen between two letters ("Tracheo-esophageal"), which a clean-up may join.
_HYPHEN = re.compile(r"(?<=[A-Za-z])-(?=[A-Za-z])")


def _authority() -> dict:
    from bve.se.ontology.indication_compatibility import _authority as load

    return load()


def norm(text: str) -> str:
    """The authority's name key: lower case, non-alphanumerics as single spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def us_spelling(text: str) -> str:
    """British spellings at a word start, or after "o" ("tracheooesophageal", "hypoglycaemia"), never inside a word
    ("tracheoesophageal" keeps its "oesophag"; review U1 N3)."""
    out = text
    for british, american in _SPELLING:
        out = re.sub(rf"(?<![a-np-z]){british}", american, out, flags=re.IGNORECASE)
    return out


def _variants(text: str) -> list[list[str]]:
    """Token lists: hyphens as spaces, and words joined across a hyphen ("tracheo-esophageal")."""
    folded = us_spelling(text).casefold()
    return [norm(folded).split(), norm(_HYPHEN.sub("", folded)).split()]


@lru_cache(maxsize=1)
def _names_by_code() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, codes in _authority()["names"].items():
        for code in codes:
            out.setdefault(code, []).append(name)
    return out


@lru_cache(maxsize=1)
def _code_by_label() -> dict[str, str]:
    return {norm(n["label"]): code for code, n in _authority()["nodes"].items()}


@lru_cache(maxsize=8192)
def ancestors(code: str) -> frozenset[str]:
    nodes = _authority()["nodes"]
    seen: set[str] = set()
    stack = [code]
    while stack:
        for parent in nodes.get(stack.pop(), {}).get("parents", []):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return frozenset(seen)


@lru_cache(maxsize=1)
def _children() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for code, node in _authority()["nodes"].items():
        for parent in node.get("parents", []):
            out.setdefault(parent, []).append(code)
    return out


@lru_cache(maxsize=256)
def descendants(code: str) -> frozenset[str]:
    seen: set[str] = set()
    stack = [code]
    while stack:
        for child in _children().get(stack.pop(), []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return frozenset(seen)


@lru_cache(maxsize=1)
def _site_roots() -> frozenset[str]:
    return frozenset(c for c, n in _authority()["nodes"].items() if n["label"].casefold().endswith(" by site"))


@lru_cache(maxsize=1)
def _morphology_roots() -> frozenset[str]:
    return frozenset(c for c, n in _authority()["nodes"].items()
                     if n["label"].casefold().endswith(" by morphology"))


def label(code: str) -> str:
    return _authority()["nodes"].get(code, {}).get("label", code)


def disease_code(name: str) -> str | None:
    from bve.se.ontology.indication_compatibility import disease_id

    return disease_id(name)


def _under_site(code: str) -> bool:
    roots = _site_roots()
    return code not in roots and bool(ancestors(code) & roots)


@lru_cache(maxsize=8192)
def _site_names(code: str) -> frozenset[str]:
    """The site a by-site concept names, from its label and names shaped "<site> Neoplasm|Disorder". None for a
    concept that is also a morphology concept: its first words are a lineage or a histology, not a site."""
    lineage = ancestors(code)
    if not _under_site(code) or code in _morphology_roots() or lineage & _morphology_roots():
        return frozenset()
    out = set()
    for name in {norm(label(code)), *_names_by_code().get(code, [])}:
        match = _SITE_SHAPE.match(name)
        if match and _clean_site(match["site"]):
            out.add(match["site"])
    return frozenset(s for s in out if s in _neoplasm_sites())


@lru_cache(maxsize=1)
def _neoplasm_sites() -> frozenset[str]:
    """Site phrases that some by-site concept names as "<site> Neoplasm": an anatomical place. A phrase only a
    "<site> Disorder" node names is often a condition or state ("pregnancy", "immunodeficiency"), so it is not a
    site here (review U1 N5). The cost is an understatement for a few real sites named only by disorders."""
    out = set()
    for code, node in _authority()["nodes"].items():
        if not _under_site(code) or code in _morphology_roots():
            continue
        for name in {norm(node["label"]), *_names_by_code().get(code, [])}:
            found = re.match(r"^(?:(?:malignant|benign|primary|secondary) )?(?P<site>[a-z0-9 ]+?) neoplasms?$", name)
            if found:
                out.add(found["site"])
    return frozenset(out)


#: Tissues NCIt names as "<tissue> Neoplasm" under its by-site nodes; a tissue runs through every organ, so it is
#: not the site a borrowed ending would drop (review U1 R11 Q3). Generic biology, no landscape word.
_TISSUES = frozenset({"vascular", "neural", "fibrous", "endocrine", "connective tissue", "soft tissue", "nervous system"})


@lru_cache(maxsize=1)
def _place_sites() -> frozenset[str]:
    """Site phrases a dropped modifier may hold (review U1 R11 Q3, Q4): "<site> Neoplasm" phrases of by-site concepts
    that are not also morphology concepts, and "<histology> of (the) <site>" phrases, both cleaned as ``_site_names``
    cleans them, so a lineage or a histology word ("neuroendocrine", "neural", "vascular") is not a site."""
    out = {s for code in _authority()["nodes"] for s in _site_names(code)}
    for code, names in _names_by_code().items():
        if any(" of " in n for n in names):
            out |= _of_sites(code)
    return frozenset(out - _TISSUES)


def _initials(short: str, words: list[str]) -> bool:
    """Whether ``short`` abbreviates the end of ``words`` (Schwartz-Hearst): its letters occur in order, right to
    left, and its first letter starts a word."""
    letters = [c for c in short.casefold() if c.isalnum()]
    text = " ".join(words).casefold()
    if len(letters) < 2 or not text:
        return False
    i = len(text) - 1
    for k in range(len(letters) - 1, -1, -1):
        while i >= 0 and (text[i] != letters[k] or (k == 0 and i > 0 and text[i - 1].isalnum())):
            i -= 1
        if i < 0:
            return False
        i -= 1
    return True


def _clean_site(site: str) -> bool:
    tokens = site.split()
    return bool(tokens) and tokens[0] not in _FUNCTION and tokens[-1] not in _FUNCTION and not set(tokens) & _NOT_IN_SITE


def _of_sites(code: str) -> frozenset[str]:
    """Sites the concept's own names put after its histology: "<histology> of (the) <site>" ("carcinoma of the
    <junction between two organs>"), where the histology is the name of a morphology concept in its lineage. NCIt has no
    by-site node shaped "<site> Neoplasm" for some sites (some junctions between organs); this is where it names
    them."""
    histology = {n for a in ancestors(code) if a not in _morphology_roots() and ancestors(a) & _morphology_roots()
                 for n in {norm(label(a)), *_names_by_code().get(a, [])}}
    out = set()
    for name in _names_by_code().get(code, []):
        found = re.fullmatch(r"(?P<histology>.+?) of (?:the )?(?P<site>.+)", name)
        if found and found["histology"] in histology and _clean_site(found["site"]):
            out.add(found["site"])
    return frozenset(out)


def _abbreviates(token: str, phrase: str) -> bool:
    """Whether ``token`` abbreviates the multi-word ``phrase`` ("hn" for "head and neck"): it is not one
    of its words, starts with its first letter, and holds the initial of every content word in order (so "head" does
    not abbreviate "head and neck")."""
    words = phrase.split()
    content = [w for w in words if w not in _FUNCTION]
    if len(words) < 2 or token in words or token[0] != phrase[0] or not _initials(token, words):
        return False
    letters = iter(token)
    return all(any(c == w[0] for c in letters) for w in content)


@lru_cache(maxsize=256)
def site_phrases(code: str) -> frozenset[str]:
    """Site phrases of a requested concept, whole, where its own names put them between generic words."""
    lineage = ancestors(code)
    sites = {s for a in (lineage | {code}) for s in _site_names(a)} | _of_sites(code)
    generic = {w for a in lineage if a not in _site_roots() and not _under_site(a)
               for n in _names_by_code().get(a, []) for w in n.split()} | _NOT_SITE
    sites = {s for s in sites if not set(s.split()) & (generic - _FUNCTION)}
    phrases: set[str] = set()
    names = _names_by_code().get(code, [])
    for name in names:
        tokens = name.split()
        taken = [False] * len(tokens)
        for site in sorted(sites, key=lambda s: -len(s.split())):
            words = site.split()
            for i in range(len(tokens) - len(words) + 1):
                if tokens[i:i + len(words)] != words or any(taken[i:i + len(words)]):
                    continue
                j = i + len(words)
                edges = (tokens[i - 1] if i else None, tokens[j] if j < len(tokens) else None)
                if all(t is None or t in generic for t in edges):
                    phrases.add(site)
                taken[i:j] = [True] * len(words)  # a longer site owns its words, bounded or not
    for name in names:  # an abbreviation of a site phrase among the concept's own names ("carcinoma hn")
        tokens = name.split()
        for i, token in enumerate(tokens):
            edges = (tokens[i - 1] if i else None, tokens[i + 1] if i + 1 < len(tokens) else None)
            if (2 <= len(token) <= 6 and token not in generic and all(t is None or t in generic for t in edges)
                    and any(_abbreviates(token, p) for p in phrases)):
                phrases.add(token)
    for a in lineage | {code}:  # a site's other names on the same by-site node ("pancreas", "pancreatic"; review U1 D1)
        names_here = _site_names(a)
        if names_here & phrases and len(names_here) <= 3:
            phrases |= {n for n in names_here if " " not in n and n not in generic}
    return frozenset(phrases)


def _clause_tokens(clause: str) -> list[str]:
    """One clause's tokens, with excluded words and non-disease roles masked ("_")."""
    folded = us_spelling(clause).casefold().replace("w/o", " without ")
    tokens = norm(folded).split()
    if set(tokens) & _POST:
        return ["_"] * len(tokens)
    text = f" {' '.join(tokens)} "
    for phrase in _CUTS:
        hit = text.find(f" {phrase} ")
        if hit >= 0:
            kept = text[:hit + 1].split()
            tokens = kept + ["_"] * (len(tokens) - len(kept))
            text = f" {' '.join(tokens)} "
    masked = list(tokens)
    for i, token in enumerate(tokens):
        if token in _NEXT_WORD and i + 1 < len(tokens):
            masked[i + 1] = "_"
    for phrase in _ROLE_BEFORE:
        words = phrase.split()
        for i in range(len(tokens) - len(words) + 1):
            if tokens[i:i + len(words)] == words:
                j = i + len(words)
                j += 1 if j < len(tokens) and tokens[j] == "the" else 0
                masked[j:j + 2] = ["_"] * len(masked[j:j + 2])
    return masked


def _record_tokens(name: str) -> list[list[str]]:
    """Token lists for site matching: clauses split at punctuation and joined by a barrier, hyphens as spaces or
    joined."""
    out = []
    for joined in (False, True):
        text = _HYPHEN.sub("", name) if joined else name
        tokens: list[str] = []
        for clause in re.split(r"[,;()\[\]]", text):
            tokens += _clause_tokens(clause) + ["|"]
        out.append(tokens)
    return out


_STATE_ROLES = frozenset({"metastatic", "refractory", "resistant"})
_TUMOUR_HEADS = frozenset({"cancer", "cancers", "tumor", "tumors", "tumour", "tumours", "neoplasm", "neoplasms",
                           "malignancy"})


def _tumour_head(word: str) -> bool:
    return word in _TUMOUR_HEADS or word.endswith(("carcinoma", "carcinomas", "sarcoma", "sarcomas"))


def _role_after(tokens: list[str], at: int) -> bool:
    """Whether the word at ``at`` makes the site before it a role, not the disease site: a role word ("therapy",
    "outlet"), a role word joined across a hyphen ("therapyresistant"), or "<word> type" ("foveolar type";
    review U1 D1, D6). A state word followed by a tumour head ("Gastric metastatic adenocarcinoma") leaves the site
    the disease's own; "liver metastatic disease" stays a role (review U1 R6 E7)."""
    after = tokens[at] if at < len(tokens) else None
    if after is None:
        return False
    if after in _ROLE_AFTER or any(after.startswith(r) for r in _ROLE_AFTER if len(r) >= 6):
        state = after in _STATE_ROLES or after.endswith(("refractory", "resistant"))
        return not (state and at + 1 < len(tokens) and _tumour_head(tokens[at + 1]))
    # "<site> <word> type" is a role ("foveolar type"), but not when the word is a tumour head ("gastric cancer type
    # 2"; review U1 R4 D8)
    return at + 1 < len(tokens) and tokens[at + 1] == "type" and after not in _BASKET_HEADS


def sites_named(name: str, phrases: frozenset[str]) -> list[str]:
    """Requested site phrases the name puts as its disease site, judged per occurrence: "gastric cancer with gastric
    outlet obstruction" names its first "gastric" as the site (review U1 D6)."""
    for tokens in _record_tokens(name):
        hits = set()
        for phrase in phrases:
            words = phrase.split()
            for i in range(len(tokens) - len(words) + 1):
                if tokens[i:i + len(words)] == words and not _role_after(tokens, i + len(words)):
                    hits.add(phrase)
        if hits:
            return sorted(hits)
    return []


def is_basket(name: str) -> bool:
    """Every word is a basket word, and no word written in capitals is a name the authority reads ("ALL" is
    acute lymphoblastic leukemia, not "all"; review U1 N4). A basket's own acronym is removed first ("Advanced solid
    tumors (AST)"; review U1 R4 D4)."""
    name = _acronyms_removed(name)[0]
    tokens = _variants(name)[0]
    if any(_acronym(m.group(0)) and not _before_basket_word(name, m.end())
           for m in re.finditer(r"\b[A-Z][A-Z0-9]{1,}\b", name)):
        return False
    return bool(tokens) and all(t in _BASKET_WORDS for t in tokens)


def _before_basket_word(name: str, end: int) -> bool:
    """Whether a word in capitals is followed by a basket word, so it reads as an ordinary word: "ALL COMERS",
    "ALL SOLID TUMORS" (review U1 D3). "RELAPSED ALL", "ALL, RELAPSED" and "ALL in adults" are the acronym (review U1
    R4 D1, R5 N1)."""
    after = re.match(r"[\s\-]+([A-Za-z]+)", name[end:])
    # only a tumour head, "solid" or "comers": a qualifier or population word after "ALL" ("ALL relapsed", "ALL in
    # adults") keeps it the acronym (review U1 R5 N1)
    # and only a plural head: "ALL disease" and "ALL malignancy" are the acronym (review U1 R6 E5)
    return after is not None and after.group(1).casefold() in _PLURAL_HEADS | {"solid", "comers"}


def _acronym(token: str) -> bool:
    """A short word in capitals that the index reads as one disease: "ALL", not a Roman numeral ("IV" reads as stage
    concepts) and not a whole word in capitals ("CANCER"; review U1 D3)."""
    if len(token) > 4 or re.fullmatch(r"[IVX]+", token):
        return False
    codes = _index(token)
    return len(codes) == 1 and not label(codes[0]).casefold().startswith("stage ")


@dataclass(frozen=True)
class Lookup:
    codes: tuple[str, ...] = ()
    #: Clean-up steps, in words.
    steps: tuple[str, ...] = ()
    #: Whether the screen applies every step (DealScreen's own readings), or U1 alone does.
    screen_reads: bool = True
    #: Notes on how a reading was chosen (exact label, population dropped).
    notes: tuple[str, ...] = ()
    #: Names joined by "or" that the authority does not read on their own (review U1 R6 E1).
    unread: tuple[str, ...] = ()
    #: Pieces of an "or" list that name no disease ("other solid tumors"; review U1 R8 D2).
    baskets: tuple[str, ...] = ()


def _reading_steps(qualifier: str) -> list[str]:
    """DealScreen reading steps in words ("qualifiers ['generalized']" -> "qualifier 'generalized' removed")."""
    out = []
    for step in qualifier.split("; "):
        found = re.fullmatch(r"qualifiers \[(.*)\]", step)
        if found:
            out.append(f"qualifier(s) {found.group(1)} removed")
        elif step.startswith("biomarker subset"):
            out.append(f"{step} read as the disease")
        elif re.fullmatch(r"[a-z][a-z\-]*", step):
            out.append(f"'{step}' set aside as a disease-state word")  # review U1 N11: never "once relapsed"
        else:
            out.append(step)
    return out


def _acronyms_removed(name: str) -> tuple[str, list[str]]:
    """Remove each parenthetical that abbreviates the words just before it ("Head and Neck (HN)"); keep the rest."""
    steps: list[str] = []

    def drop(match: re.Match[str]) -> str:
        before = re.findall(r"[A-Za-z0-9]+", name[:match.start()])
        short = match.group(1).strip()
        if re.fullmatch(r"[A-Za-z]{2,6}", short) and _initials(short, before[-8:]):
            steps.append(f"acronym '({short})' removed")
            return ""
        return match.group(0)

    return _PAREN.sub(drop, name).strip(), steps


def _index(name: str) -> list[str]:
    return list(_authority()["names"].get(norm(name), []))


def _screen_readings(name: str) -> tuple[list[str], list[str]]:
    readings = indication_readings(name)
    codes = [c for r in readings if (c := disease_code(r["read_as"]))]
    steps = [s for r in readings for s in _reading_steps(r["qualifier"])]
    return list(dict.fromkeys(codes)), list(dict.fromkeys(steps))


#: The joins of a list of names: "A or B", "A, B or C", "A and/or B".
_OR_JOIN = re.compile(r"\s*,\s*(?:(?:and/)?or\s+)?|\s+(?:and/)?or\s+", re.IGNORECASE)
_HAS_OR = re.compile(r"(?<![\w/])(?:and/)?or(?![\w/])", re.IGNORECASE)
#: Words that modify a disease name and name none: stages, grades, lines, extent, state and population words
#: (review U1 R7 F1, F2). A piece made only of these is never looked up on its own.
_MODIFIER_WORDS = (_BASKET_EXTRA | _QUALIFIER_WORDS | _POPULATION | _LABEL_POPULATION | _FUNCTION
                   | GENERIC_REMAINDERS | frozenset({
                       "grade", "grades", "stage", "stages", "type", "line", "lines", "phase", "monotherapy",
                       "combination", "recurrent", "relapsed", "refractory", "resistant", "persistent", "early",
                       "advanced", "moderate", "moderately", "severe", "severely", "mild", "mildly", "active",
                       "localized", "localised", "unresectable", "metastatic", "newly", "diagnosed", "previously",
                       "treated", "untreated", "high", "low", "risk", "intermediate", "chronic", "acute", "first",
                       "second", "third"})) - frozenset({  # a symptom or a finding is a name (review U1 R8 D2)
                       "pain", "infection", "infections", "inflammation", "syndrome", "syndromes", "illness"})
#: Modifier words that can make another NCIt concept ("chronic" myeloid leukemia, "type 2" diabetes; review U1 R8
#: D1, D3). Such a piece is tried with the name's head before it is folded or set aside.
_DEFINING = frozenset({"acute", "chronic", "severe", "mild", "moderate", "juvenile", "adult", "adults", "pediatric",
                       "paediatric", "childhood", "infantile", "adolescent", "neonatal", "early", "late", "high", "low",
                       "type", "grade", "non"})
_STAGE_TOKEN = re.compile(r"^(?:[0-4][a-c]?|i{1,3}[a-c]?|iv[a-c]?|[1-4]l|\d+(?:st|nd|rd|th)?)$")
#: A biomarker or a state written as a piece ("HER2+", "PD-L1 positive"): set aside, not a disease name.
_MARKER_PIECE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*[+\-−]$|^[A-Z0-9][\w.\-]*\s+(?:positive|negative|high|low)$")


def _modifier_only(piece: str, caps: bool = False) -> bool:
    """Only modifier words; an acronym in capitals ("ALL") is a name, a Roman stage ("IV") is not."""
    words = [w for w in re.split(r"[\s\-/]+", piece) if w]
    return bool(words) and all(_modifier_word(w, caps) for w in words)


def _modifier_word(word: str, caps: bool = False) -> bool:
    """``caps``: the whole cell is in capitals, so a word in capitals is not an acronym by its shape; only "ALL"
    stays a name (review U1 R8 D4)."""
    folded = word.casefold()
    if bool(_STAGE_TOKEN.match(folded)) or folded == "r":
        return True
    if folded not in _MODIFIER_WORDS:
        return False
    return folded != "all" if caps else not (word.isupper() and len(word) > 1)


def _caps(name: str) -> bool:
    return any(c.isalpha() for c in name) and name == name.upper()


def _defining(piece: str) -> bool:
    return any(w.casefold() in _DEFINING for w in re.split(r"[\s\-/]+", piece) if w)


def _state_removed(piece: str, caps: bool = False) -> str:
    """The piece without leading state and extent words ("Relapsed/refractory adult ALL" -> "adult ALL"); a
    population word stays, it is part of the disease name."""
    words = piece.split()
    while len(words) > 1 and all(_modifier_word(w, caps) and w.casefold() not in _POPULATION | _LABEL_POPULATION
                                 for w in re.split(r"[\-/]+", words[0]) if w):
        words = words[1:]
    return " ".join(words)


_PEOPLE_WITH = re.compile(r"^(?:(?:adult|adults|pediatric|paediatric|juvenile|childhood|elderly)\s+)?(?:patients|"
                          r"adults|children|subjects|participants|people|persons|individuals)\s+(?:with|having)\s+|"
                          r"^(?:adult|adults|pediatric|paediatric|juvenile|childhood)\s+", re.IGNORECASE)


def _population_removed(piece: str) -> str:
    """The piece without a leading population ("Patients with UC", "Adult UC" -> "UC"; review U1 R8 D5)."""
    return _PEOPLE_WITH.sub("", piece, count=1).strip()


def _head(piece: str, caps: bool) -> str:
    """The name without its leading modifier words ("acute myeloid leukemia" -> "myeloid leukemia")."""
    words = piece.split()
    while len(words) > 1 and all(_modifier_word(w, caps) or w.casefold() == "non"
                                 for w in re.split(r"[\-/]+", words[0]) if w):
        words = words[1:]
    return " ".join(words)


def _heads(piece: str, caps: bool) -> list[str]:
    """The heads a leading modifier may borrow from the next name: the name without its modifier words, or else its
    longest ending that is itself a disease name, of two words at least ("progressive multiple sclerosis" -> "multiple
    sclerosis"). A one-word ending ("adenocarcinoma") would drop the site, and so does an ending that leaves out a
    site word ("Metastatic or pancreatic neuroendocrine carcinoma"; review U1 R10 P4)."""
    first = _head(piece, caps)
    if first != piece:
        return [first]
    words = piece.split()
    tail = next((t for k in range(1, len(words) - 1)
                 if not _names_site(piece, k) and _named(t := " ".join(words[k:]))), None)
    return [tail] if tail else []


def _names_site(piece: str, k: int) -> bool:
    """Whether a site phrase starts in the first ``k`` words of ``piece``, the words a borrowed ending drops
    ("pancreatic" in "pancreatic neuroendocrine carcinoma", "extrahepatic bile duct" in "extrahepatic bile duct
    carcinoma"): the ending would then name no site the record names (review U1 R10 P4, R11 Q4). The sites are
    ``_place_sites``, so a lineage word is not one (R11 Q3)."""
    folded = norm(us_spelling(piece)).split()
    cut = len(norm(us_spelling(" ".join(piece.split()[:k]))).split())
    sites = _place_sites()
    return any(" ".join(folded[i:j]) in sites for i in range(cut) for j in range(i + 1, len(folded) + 1))


def _named(text: str) -> bool:
    return bool(_index(text) or _index(us_spelling(text)))


def _basket_piece(piece: str) -> bool:
    """A piece of an "or" list that names a group of diseases ("other solid tumors", "all comers")."""
    tokens = _variants(piece)[0]
    return is_basket(piece) and any(t in _BASKET_HEADS | {"comers"} for t in tokens)


#: Words a number defines in an "or" list: "Type 1 or 2 diabetes", "Grade 1 or 2 follicular lymphoma".
_NUMBERED = frozenset({"type", "grade", "stage", "class"})


def _numbered(piece: str, before: str, steps: list[str]) -> str:
    """"2 diabetes mellitus" after "Type 1" is "Type 2 diabetes mellitus": the number keeps the word it numbers, and
    is never removed as a stage token (review U1 R9 N3)."""
    first = piece.split()[0] if piece.split() else ""
    prior = before.split()
    if (len(prior) == 2 and prior[0].casefold() in _NUMBERED and _number(prior[1]) and _number(first)):
        steps.append(f"'{piece}' read as '{prior[0]} {piece}'")
        return f"{prior[0]} {piece}"
    return piece


def _number(token: str) -> bool:
    """A stage, type or grade number ("2", "III", "3a"), not a line of therapy ("2L", "1st"; review U1 R10 P6, R11
    Q6)."""
    folded = token.casefold()
    return bool(_STAGE_TOKEN.match(folded)) and not re.fullmatch(r"[1-4]l|\d+(?:st|nd|rd|th)", folded)


def _numbered_piece(piece: str) -> bool:
    """"type 1", "grade 2", "stage III": a numbered word, which may make another concept with a name."""
    words = piece.split()
    return len(words) == 2 and words[0].casefold() in _NUMBERED and _number(words[1])


def is_modifier_piece(piece: str) -> bool:
    """A piece of an "or" list made only of modifier words ("severe", "moderate to severe")."""
    return _modifier_only(piece, _caps(piece))


@dataclass(frozen=True)
class _Pieces:
    names: list[str]
    steps: list[str]
    #: modifier pieces that may make another concept but that the authority does not read with the name
    unread: list[str]
    baskets: list[str]


def _list_pieces(name: str) -> _Pieces | None:
    """The record's own "or" list as names, and the steps that made it. A modifier piece first in the list belongs to
    the name after it ("Locally advanced or metastatic X", "Stage III or IV X" are one name), unless with the name's
    head it is another NCIt concept ("Chronic or acute myeloid leukemia": chronic and acute myeloid leukemia; review
    U1 R8 D1). A modifier set apart by commas later in the list is the inverted modifier of the name before it when
    the two make an NCIt concept ("Myeloid leukemia, chronic"; R8 D3), otherwise it is set aside; one that may make
    another concept is named as unread, never set aside in silence. A basket piece ("other solid tumors") is kept as
    a basket (R8 D2). A parenthesised list is part of the list ("IBD (UC or CD)"). None when fewer than two parts
    remain."""
    if not _HAS_OR.search(name):
        return None
    caps = _caps(name)
    text = re.sub(r"\(([^()]*)\)", lambda m: f", {m.group(1)}" if _HAS_OR.search(m.group(1)) else m.group(0), name)
    text = re.sub(r"^\s*either\s+", "", text, flags=re.IGNORECASE)  # review U1 R8 D9
    raw = [p.strip(" ,;") for p in _OR_JOIN.split(text) if p.strip(" ,;")]
    out = _Pieces([], [], [], [])
    carry, set_aside, after_basket = "", False, False
    base: str | None = None  # the name before its first inverted modifier ("GVHD" in "GVHD, acute or chronic")
    for i, piece in enumerate(raw):
        if _basket_piece(piece) and not carry:
            out.baskets.append(piece)
            after_basket = True  # an inverted modifier after a basket has no name before it (review U1 R10 P7)
            continue
        if out.names and i and _numbered_piece(raw[i - 1]) and _number(piece):
            # "Diabetes mellitus, type 1 or 2": the number keeps the word it numbers (review U1 R10 P5)
            out.steps.append(f"'{piece}' read as '{raw[i - 1].split()[0]} {piece}'")
            piece = f"{raw[i - 1].split()[0]} {piece}"
        if _modifier_only(piece, caps) or _MARKER_PIECE.match(piece):
            if not out.names and i + 1 < len(raw):
                # any leading modifier, not only a listed one, with the next name's head or its last words: NCIt
                # decides whether it makes a concept ("Relapsing or progressive multiple sclerosis"; review U1 R9 N1)
                head = next((h for h in _heads(raw[i + 1], caps) if _named(f"{piece} {h}")), None)
                if not carry and not _MARKER_PIECE.match(piece) and head is not None:
                    out.names.append(f"{piece} {head}")
                    out.steps.append(f"'{piece}' read as '{piece} {head}'")
                else:
                    carry = f"{carry}{piece} or "
            elif out.names and after_basket and (_defining(piece) or _numbered_piece(piece)):
                out.unread.append(piece)
            elif out.names and (_defining(piece) or _numbered_piece(piece)) and not _MARKER_PIECE.match(piece):
                # "GVHD, acute or chronic": each modifier with the same name, never with the last result (R9 N5)
                shown = base if base is not None else out.names[-1]
                # "type 2 <base>", or "<base> type 2" where NCIt puts the number after the name (review U1 R11 Q5)
                tries = [f"{piece} {shown}", *([f"{shown} {piece}"] if _numbered_piece(piece) else [])]
                inverted = next((t for t in tries if _named(t)), tries[0])
                if _named(inverted):
                    out.steps.append(f"'{shown}, {piece}' read as '{inverted}'")
                    if base is None:
                        base = out.names[-1]
                        out.names[-1] = inverted
                    else:
                        out.names.append(inverted)
                elif _numbered_piece(piece) and piece.split()[0].casefold() == "stage":
                    # a stage the authority does not read with the name qualifies it and is set aside, as before
                    # revision 11 (review U1 R11 Q2)
                    out.steps.append(f"'{piece}' set aside as a modifier, not a name")
                    set_aside = True
                else:
                    out.unread.append(piece)
            else:
                out.steps.append(f"'{piece}' set aside as a modifier, not a name")
                # a grade or stage alternative ("grade 1, 2 or 3a") is not a modifier of one name
                set_aside = set_aside or not all(_STAGE_TOKEN.match(w.casefold())
                                                 for w in re.split(r"[\s\-/]+", piece) if w)
            continue
        if not carry:  # "Grade 1 or 2 obesity" keeps the record's words when it is read whole (review U1 R10 P6)
            piece = _numbered(piece, raw[i - 1] if i else "", out.steps)
        out.names.append(carry + piece)
        carry, base, after_basket = "", None, False
    # "X (first or second line)": one name once its modifiers are set aside (review U1 R8 D9)
    # one name beside an unread piece is still a list: the name is read and the piece named (review U1 R11 Q2)
    if not out.names or (len(out.names) + len(out.baskets) < 2 and not set_aside and not out.unread):
        return None
    count = len(out.names) + len(out.baskets)
    split = f"its 'or' list split into {count} names" if count > 1 else "its 'or' list read as one name"
    return _Pieces(out.names, [split, *out.steps],
                   out.unread, out.baskets)


def _conjuncts(name: str) -> Lookup | None:
    """Each name in the record's own "or" list, read on its own, whatever path reads the name (review U1 R6 E1, R7
    F1). A bare site ("Pancreatic, gastric or esophageal adenocarcinoma") is read with the last name's head. None when
    the name is not a list of two or more disease names."""
    listed = _list_pieces(name)
    if listed is None:
        return None
    pieces, steps, caps = listed.names, listed.steps, _caps(name)
    head = pieces[-1].split()
    codes: list[str] = []
    unread = list(listed.unread)
    for piece in pieces:
        inner = _lookup(piece)
        found = _alone(piece, inner.codes, name)
        if found and _synonyms_only(piece, found) and (borrowed_codes := _borrow(piece, head, steps)):
            found = borrowed_codes  # the record's own coordination outranks an index synonym (review U1 R11 Q1)
            codes += found
            continue
        if found and not inner.screen_reads and _HAS_OR.search(piece):  # a nested list U1 split (R10 P8)
            steps += [f"in '{piece}', {' and '.join(inner.steps)}"] if inner.steps else []
        if not found and (bare := _state_removed(piece, caps)) != piece and (found := _lookup(bare).codes):
            steps.append(f"'{piece}' read as '{bare}'")
        if not found and (bare := _population_removed(_state_removed(piece, caps))) not in {piece, ""} and (
                found := _lookup(bare).codes):
            found, bare = _with_population(piece, found, bare)
            steps.append(f"'{piece}' read as '{bare}'")
        if not found:
            found = _borrow(piece, head, steps)
        if found:
            codes += found
        else:
            unread.append(piece)
    return Lookup(tuple(dict.fromkeys(codes)), tuple(steps), screen_reads=False, unread=tuple(unread),
                  baskets=tuple(listed.baskets))


def _borrow(piece: str, head: list[str], steps: list[str]) -> tuple[str, ...]:
    """The piece read with the last name's head ("Central" with "diabetes insipidus"), longest first."""
    for k in range(len(head) - 1, 0, -1):
        candidate = f"{piece} {' '.join(head[-k:])}"
        borrowed = _lookup(candidate)
        if borrowed.codes:
            steps.append(f"'{piece}' read as '{candidate}'")
            if not borrowed.screen_reads:  # a nested list U1 split shows its own steps (review U1 R10 P8)
                steps += [f"in '{candidate}', {' and '.join(borrowed.steps)}"] if borrowed.steps else []
            return borrowed.codes
    return ()


def _label_words(code: str) -> list[str]:
    return [w for w in norm(label(code)).split() if w not in _FUNCTION]


def _synonym(word: str, code: str) -> bool:
    """A reading of a one-word piece whose label holds neither the word nor its initials ("hives" -> Urticaria)."""
    lab = _label_words(code)
    return bool(lab) and word not in lab and not _initials(word, lab)


def _synonyms_only(piece: str, codes: tuple[str, ...]) -> bool:
    words = norm(piece).split()
    return len(words) == 1 and all(_synonym(words[0], c) for c in codes)


@lru_cache(maxsize=1)
def _word_uses() -> tuple[dict[str, int], dict[str, int]]:
    """How often NCIt uses each word as the head (last word) of a label, and as another word of a label."""
    heads: dict[str, int] = {}
    others: dict[str, int] = {}
    for node in _authority()["nodes"].values():
        lab = [w for w in norm(node["label"]).split() if w not in _FUNCTION]
        if lab:
            heads[lab[-1]] = heads.get(lab[-1], 0) + 1
        for w in set(lab[:-1]):
            others[w] = others.get(w, 0) + 1
    return heads, others


def _modifier_synonym(word: str, code: str) -> bool:
    """An index reading of a one-word piece that is an ordinary modifier word, not the word's own disease (review U1
    R11 Q1). NCIt uses the word more often inside labels than as their head ("central", "sensitive"; for a reading
    that the word abbreviates, "cold" for Chronic Obstructive Pulmonary Disease, in three labels at least, so "aml"
    stays), or never as a head while the label holds a modifier of the same stem ("recurrence" -> Recurrent
    Neoplasm). "sepsis", "epilepsy", "infection" and "hives" are kept: NCIt uses them as heads as often."""
    heads, others = _word_uses()
    lab = _label_words(code)
    initials = _initials(word, lab)
    if others.get(word, 0) > heads.get(word, 0) and (others.get(word, 0) >= 3 or not initials):
        return True
    return not initials and not heads.get(word) and any(len(os.path.commonprefix([word, w])) >= 6 for w in lab[:-1])


def _alone(piece: str, codes: tuple[str, ...], name: str) -> tuple[str, ...]:
    """The readings of a one-word piece that are that word's own disease. The index holds adjectives as synonyms of
    specific concepts ("diffuse" -> Gastric Diffuse Adenocarcinoma, "symptomatic" -> a COVID-19 concept): the word
    is a word of the label, but not its head. Such a reading is refused unless the word is the first of a two-word
    label ("diabetes" -> Diabetes Mellitus) or every word of the label is in the record (review U1 R9 N2). Every other
    reading is kept, in any letter case: the label's head ("myeloma" -> Multiple Myeloma), an acronym ("mCRPC",
    "iCCA", "aml") and a synonym ("hives" -> Urticaria) hold no non-head word of the label (R10 P2, P3)."""
    words = norm(piece).split()
    if len(words) != 1:
        return codes
    word, record = words[0], set(norm(us_spelling(name)).split())
    kept = []
    for code in codes:
        lab = [w for w in norm(label(code)).split() if w not in _FUNCTION]
        if word not in lab and _modifier_synonym(word, code) and not set(lab) <= record:
            continue
        if not lab or word not in lab[:-1] or (len(lab) == 2 and lab[0] == word) or set(lab) <= record:
            kept.append(code)
    return tuple(kept)


#: The population word NCIt puts in a label, for a population the record states (review U1 R9 N4).
_POPULATION_LABEL = {"children": "childhood", "child": "childhood", "childhood": "childhood", "pediatric": "childhood",
                     "paediatric": "childhood", "juvenile": "childhood", "adult": "adult", "adults": "adult"}


def _with_population(piece: str, codes: tuple[str, ...], bare: str) -> tuple[tuple[str, ...], str]:
    """A piece read without its population ("Children with ALL" -> "ALL") is read as the concept's own population
    child when NCIt has one ("Childhood Acute Lymphoblastic Leukemia"), so a pediatric record is never shown as the
    parent of an adult request (review U1 R9 N4)."""
    pop = next((_POPULATION_LABEL[w] for w in norm(piece).split()[:3] if w in _POPULATION_LABEL), None)
    if pop is None:
        return codes, bare
    kids = [k for c in codes if (k := _code_by_label().get(norm(f"{pop} {label(c)}"))) and k in descendants(c)]
    return (tuple(dict.fromkeys(kids)), f"{pop} {bare}") if kids else (codes, bare)


def _whole(name: str) -> Lookup | None:
    """A name with "or" inside an NCIt label ("… with MYC and BCL2 or BCL6 rearrangements"), read whole once its
    leading qualifiers are removed, before the list is split (review U1 R8 D6)."""
    cleaned, steps = us_spelling(name), []
    while True:
        hit = next((q for q in (*EXTENT_QUALIFIERS, *QUALIFIERS) if cleaned.casefold().startswith(q + " ")), None)
        if hit is None or re.match(r"(?:and/)?or\s", cleaned[len(hit) + 1:].strip(), re.IGNORECASE):
            break
        cleaned = cleaned[len(hit) + 1:].strip()
        steps.append(f"'{hit}' removed")
    codes = _index(cleaned)
    return Lookup(tuple(codes), tuple(steps), screen_reads=False) if codes and steps else None


def _softened(name: str) -> str:
    """A cell in capitals with its modifier words in lower case, so they read as words, not acronyms ("MODERATE OR
    SEVERE UC" -> "moderate OR severe UC"; review U1 R8 D4). "ALL" stays a name."""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).lower() if _modifier_word(m.group(0), caps=True)
                  and not _STAGE_TOKEN.match(m.group(0).casefold()) else m.group(0), name)


def _as_written(found: Lookup, name: str) -> Lookup:
    """Pieces quoted from a softened cell in the record's own letters, which are all capitals ("CHILD-PUGH A", not
    "child-PUGH a"; review U1 R9 N7). The step "its 'or' list" keeps its own word."""
    def own(m: re.Match[str]) -> str:
        return m.group(0) if m.group(1).casefold() == "or" else f"'{m.group(1).upper()}'"

    return replace(found, steps=tuple(re.sub(r"'([^']+)'", own, s) for s in found.steps),
                   unread=tuple(u.upper() for u in found.unread), baskets=tuple(b.upper() for b in found.baskets))


def _raw_lookup(name: str) -> Lookup:
    if codes := _index(name):
        return Lookup(tuple(codes))
    if _caps(name) and (soft := _softened(name)) != name:
        found = _raw_lookup(soft)
        if found.codes:
            codes, steps = _screen_readings(name)
            # the gate reads the cell the same way (review U1 R9 N6), and U1 read all of it: an unread or basket
            # piece is never dropped for the gate's smaller reading (R10 P1)
            if set(codes) == set(found.codes) and not found.unread and not found.baskets:
                return Lookup(tuple(codes), tuple(steps))
            return _as_written(replace(found, steps=("modifier words in capitals read as ordinary words",
                                                     *found.steps), screen_reads=False), name)
    if _HAS_OR.search(name) and (whole := _whole(name)) is not None:
        return whole
    if (each := _conjuncts(name)) is not None:  # the record's own list, before any clean-up (review U1 R7 F1)
        return each
    codes, steps = _screen_readings(name)
    if codes:
        return Lookup(tuple(codes), tuple(steps))
    cleaned, steps = name, []
    if (spelled := us_spelling(cleaned)) != cleaned:
        cleaned = spelled
        steps.append("British spelling read as American")
    cleaned, acronyms = _acronyms_removed(cleaned)
    steps += acronyms
    while True:
        folded = cleaned.casefold()
        hit = next((q for q in (*EXTENT_QUALIFIERS, *QUALIFIERS) if folded.startswith(q + " ")), None)
        if hit is None:
            break
        cleaned = cleaned[len(hit) + 1:].strip()
        steps.append(f"'{hit}' removed")
        # "moderate or severe X": the qualifier's own "or" goes with it (review U1 R7 F1)
        cleaned = re.sub(r"^(?:(?:and/)?or|to)\s+", "", cleaned, flags=re.IGNORECASE)
    joined = _HYPHEN.sub("", cleaned)
    if joined != cleaned and not _index(cleaned) and _index(joined):
        words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)+", cleaned)
        steps.append("hyphen joined (" + ", ".join(f"'{w}' as '{w.replace('-', '')}'" for w in words) + ")")
        cleaned = joined
    if not steps:
        return Lookup()
    if codes := _index(cleaned):
        return Lookup(tuple(codes), tuple(steps), screen_reads=False)
    codes, more = _screen_readings(cleaned)
    return Lookup(tuple(codes), tuple(steps + more), screen_reads=False) if codes else Lookup()


def _without_population(code: str, name: str) -> str | None:
    """The concept's own ancestor named by its label without a population word the record does not state
    ("Childhood Renal Cell Carcinoma" -> "Renal Cell Carcinoma"); None when the record states one or there is none."""
    words = norm(label(code)).split()
    if not set(words) & _LABEL_POPULATION or set(_variants(name)[0]) & (_LABEL_POPULATION | _POPULATION):
        return None
    base = _code_by_label().get(" ".join(w for w in words if w not in _LABEL_POPULATION))
    return base if base and base in ancestors(code) else None


def _lookup(name: str) -> Lookup:
    """NCIt codes for a name, with every clean-up and choice shown (review D3, D7)."""
    found = _raw_lookup(name)
    codes, notes = list(found.codes), list(found.notes)
    if len(codes) > 1:
        exact = [c for c in codes if norm(label(c)) in {norm(name), norm(us_spelling(name))}]
        if len(exact) == 1:
            notes.append(f"the concept its label names exactly, of {len(codes)} index entries")
            codes = exact
    swapped = []
    for i, code in enumerate(codes):
        base = _without_population(code, name)
        if base:
            swapped.append(f"'{label(code)}' read as '{label(base)}' (the record states no population)")
            codes[i] = base
    notes += swapped
    for code in dict.fromkeys(codes):  # review U1 N1: the edition is in NCIt's label, not in the record
        edition = re.search(r"AJCC v\d+", label(code))
        if edition and edition.group(0).casefold() not in name.casefold():
            notes.append(f"'{edition.group(0)}' is part of NCIt's label; the record states no edition")
    return Lookup(tuple(dict.fromkeys(codes)), found.steps, found.screen_reads, tuple(dict.fromkeys(notes)),
                  found.unread, found.baskets)


def _parents(code: str) -> list[str]:
    return list(_authority()["nodes"].get(code, {}).get("parents", []))


def _stage_concept(code: str) -> bool:
    """An NCIt stage concept: its label starts "Stage", or it sits under a "... by AJCC vN Stage" grouping."""
    if label(code).casefold().startswith("stage "):
        return True
    return any(re.search(r"\bby (?:ajcc v\d+ )?stage$", label(a).casefold()) for a in ancestors(code))


def _sibling(code: str, requested: frozenset[str]) -> bool:
    """Whether the concept is a stage concept under a by-site ancestor of a requested concept, adds no
    category the request lacks (every ancestor not under a site is an ancestor of the request: no virus-related,
    squamous or other non-site lineage), and names one of that request's sites ("Stage IV <site> Cancer" beside a
    "<site> adenocarcinoma" request). Every ancestor the request lacks must be a stage grouping, so a stage concept of
    a neuroendocrine, small-cell or sarcoma lineage filed under the same site is not one (review U1 R4 D2). Other
    concepts under the same parent, such as a lymphoma, a sarcoma or another organ's cancer, stay different diseases
    (review U1 D1, J1). Cost: stage concepts NCIt files under a population or staging-system node the request lacks
    ("Stage … Adult Liver Cancer AJCC v7", "… Endometrial Cancer FIGO 2023") are different diseases too."""
    if not _stage_concept(code):
        return False
    lineage = ancestors(code)
    categories = frozenset(a for a in lineage if not _under_site(a) and a not in _site_roots())
    for q in requested:
        if not any(_under_site(a) for a in lineage & ancestors(q)):  # a by-site ancestor they share
            continue
        if not categories <= ancestors(q) | {q}:
            continue
        # NCIt files some lineages (neuroendocrine, sarcoma, small-cell) under by-site roots, so the test above does
        # not see them: every ancestor the request lacks must be a stage grouping (review U1 R4 D2).
        if not all("stage" in label(a).casefold() for a in lineage - ancestors(q) - {q}):
            continue
        phrases = site_phrases(q)
        if any(sites_named(n, phrases) for n in {label(code), *_names_by_code().get(code, [])}):
            return True
    return False


def relation(code: str, requested: frozenset[str]) -> str:
    if code in requested or ancestors(code) & requested:
        return REQUESTED
    if any(code in ancestors(q) for q in requested):
        return BROADER
    if any(code in ancestors(d) for q in requested for d in descendants(q)):
        return OVERLAPS
    if _sibling(code, requested):
        return SIBLING
    return DIFFERENT


@dataclass(frozen=True)
class NameReading:
    name: str
    category: str
    #: (NCIt label, relation) per matching concept.
    concepts: tuple[tuple[str, str], ...] = ()
    steps: tuple[str, ...] = ()
    sites: tuple[str, ...] = ()
    #: Whether the screen applies the clean-up steps (False: U1 alone does).
    screen_reads: bool = True
    notes: tuple[str, ...] = ()
    #: Names in an "or" list the authority does not read on their own (review U1 R6 E1).
    unread: tuple[str, ...] = ()
    #: Pieces of an "or" list that name a group of diseases (review U1 R8 D2).
    baskets: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        out = {"name": self.name, "class": self.category,
               "ncit": [{"label": lab, "relation": rel} for lab, rel in self.concepts],
               "steps": list(self.steps), "screen_applies_steps": self.screen_reads, "notes": list(self.notes),
               "site_words": list(self.sites)}
        return (out | ({"unread_parts": list(self.unread)} if self.unread else {})
                | ({"basket_parts": list(self.baskets)} if self.baskets else {}))


def _shown_sites(hits: list[str], phrases: frozenset[str]) -> tuple[str, ...]:
    """Sites as shown: an abbreviation with the phrase it stands for ("HN (head and neck)"), and not at
    all when that phrase is named too."""
    out = []
    for hit in hits:
        full = sorted(p for p in phrases if p != hit and _abbreviates(hit, p))
        if not full:
            out.append(hit)
        elif full[0] not in hits:
            out.append(f"{hit.upper()} ({full[0]})")
    return tuple(out)


def _split(found: Lookup) -> bool:
    return any(step.startswith("its 'or' list split") for step in found.steps)


def classify_name(name: str, requested: frozenset[str]) -> NameReading:
    """One name's class. Order: basket, then the authority, then site words (ACCEPTANCE U1; review J1)."""
    if is_basket(name):
        return NameReading(name, BASKET)
    phrases = frozenset().union(*(site_phrases(q) for q in requested))
    sites = _shown_sites(sites_named(name, phrases), phrases)
    found = _lookup(name)
    if not found.codes:
        return NameReading(name, NAMES_REQUESTED_SITE if sites else UNREADABLE, sites=sites)
    rel = {c: relation(c, requested) for c in found.codes}
    shared = {label(c) for c in rel if sum(label(d) == label(c) for d in rel) > 1}
    # two NCIt codes with one label are shown with their codes, so the sentence does not contradict itself (review
    # U1 R11 Q7)
    concepts = tuple((f"{label(c)} ({c})" if label(c) in shared else label(c), r) for c, r in rel.items())
    if found.unread or found.baskets:
        # part of an "or" list is not read, or names a basket: never a class from the other part alone (review U1
        # R6 E1, R8 D2); a list that reads a requested name is ambiguous, not unreadable (R7 F3)
        category = (AMBIGUOUS_NAME if REQUESTED in rel.values() else NAMES_REQUESTED_SITE if sites else UNREADABLE)
        return NameReading(name, category, concepts, found.steps, sites, found.screen_reads, found.notes,
                           found.unread, found.baskets)
    kinds = set(rel.values())
    if kinds == {BROADER}:
        category = BROADER_THAN_REQUESTED if len(rel) == 1 else AMBIGUOUS_NAME_ALL_BROADER
    elif kinds == {OVERLAPS} and len(rel) == 1:
        category = OVERLAPS_REQUESTED
    elif kinds <= {SIBLING, BROADER} and SIBLING in kinds and sites:
        # the record itself must name a requested site, not only NCIt's synonyms (review U1 D1)
        category = UNDER_REQUESTED_PARENT
    elif kinds <= {SIBLING, DIFFERENT} or kinds == {DIFFERENT}:
        category = DIFFERENT_DISEASE
    elif len(rel) == 1 or (kinds == {REQUESTED} and _split(found)):
        category = READS_AS_REQUESTED  # every name of the record's own list is requested (review U1 R7 F1)
    else:
        category = AMBIGUOUS_NAME
    return NameReading(name, category, concepts, found.steps, sites, found.screen_reads, found.notes)


def requested_codes(indications: list[str]) -> frozenset[str]:
    return frozenset(c for c in (disease_code(i) for i in indications) if c)


@dataclass(frozen=True)
class Request:
    """The buyer's requested indications as the gate reads them."""
    codes: frozenset[str]
    #: (request as written, NCIt labels its name matches) for each request that is not exactly one concept.
    unresolved: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: Requests the S&E matches by its own condition rule, not by an NCIt concept.
    condition_rules: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not (self.unresolved or self.condition_rules)


def restatement(indication: str) -> tuple[str, str] | None:
    """A name the gate reads as the one concept whose label is the request, and that label (review U1 D1). Only that
    concept: when no reading's label is the request, the readings may be different diseases ("pnh"), so none is
    suggested and the buyer chooses (review U1 N2). Never a name that is itself ambiguous."""
    exact = [c for c in _index(indication) if norm(label(c)) == norm(indication)]
    if len(exact) != 1:
        return None
    code = exact[0]
    if disease_code(label(code)) == code:
        return label(code), label(code)
    # Only an acronym is shown: the index's other names are normalised keys and adjectives ("lymphomatous", "neural
    # crest tumor malignant"; review U1 N11, D8).
    acronyms = [n for n in _names_by_code().get(code, [])
                if re.fullmatch(r"[a-z]{2,6}", n) and disease_code(n) == code and n not in norm(label(code)).split()
                and n not in _BASKET_WORDS]  # an English word, not an acronym ("tumor"; review U1 R4 D9)
    return (min(acronyms, key=lambda n: (len(n), n)).upper(), label(code)) if acronyms else None


def read_request(indications: list[str]) -> Request:
    from bve.se.ontology.indications import is_indication_concept

    codes, unresolved, rules = set(), [], []
    for indication in indications:
        if is_indication_concept(indication):
            rules.append(indication)
        elif code := disease_code(indication):
            codes.add(code)
        else:
            unresolved.append((indication, tuple(label(c) for c in _index(indication))))
    return Request(frozenset(codes), tuple(unresolved), tuple(rules))


__all__ = [
    "AMBIGUOUS_NAME",
    "AMBIGUOUS_NAME_ALL_BROADER",
    "BASKET",
    "BROADER",
    "BROADER_THAN_REQUESTED",
    "DIFFERENT",
    "DIFFERENT_DISEASE",
    "NAMES_REQUESTED_SITE",
    "NO_RECORD",
    "ORDER",
    "OVERLAPS",
    "OVERLAPS_REQUESTED",
    "READS_AS_REQUESTED",
    "REQUESTED",
    "REQUEST_NOT_ONE_CONCEPT",
    "SIBLING",
    "UNDER_REQUESTED_PARENT",
    "UNREADABLE",
    "Lookup",
    "NameReading",
    "Request",
    "classify_name",
    "is_basket",
    "read_request",
    "requested_codes",
    "restatement",
    "site_phrases",
    "sites_named",
    "us_spelling",
]
