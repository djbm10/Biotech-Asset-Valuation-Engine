"""Which kinds of document may produce which decisional facts.

Most of what a source can support follows from what it contains, and needs no policy: a
title has no clinical result in it, so a title-only record was never going to establish
human proof-of-concept no matter what was allowed. That is how the conference tier held this
property for its first four venues -- not by rule, but because Crossref returned titles.

AACR is the first conference route that returns abstract bodies, and an oncology abstract is
largely made of efficacy prose. So the property stops being automatic exactly when it starts
to matter, and an unstated invariant that survives only while its precondition happens to
hold is one that disappears without any test failing.

Hence this module, and hence its narrowness. It is an *evidence-policy* statement, not a
claim about what conference abstracts contain and not a judgement about their quality. Early
oncology efficacy is frequently reported at a meeting well before it reaches a journal, and a
tool that can never read that will systematically miss the earliest clinically meaningful
data. Whether a genuine abstract reporting an attributable human response may establish human
PoC is a real question, and the honest way to answer it is against the corpus, under a
standard set before the result is known -- not by inheriting an answer from an accident of
what an API used to return.

The scope is deliberately one fact. Identity, target and development-stage evidence read
abstract bodies under exactly the rules they already applied to every other source, which is
the whole reason for acquiring the bodies.
"""

from __future__ import annotations

#: Document types whose text may be read for every other purpose, but may not produce
#: ``human_poc_present``. Conference abstracts only -- see the module docstring for why this
#: is a held position rather than a permanent one.
NON_DECISIONAL_FOR_HUMAN_POC = frozenset(
    {
        "conference_abstract_metadata",
        "conference_abstract",
    }
)


def may_establish_human_poc(document_type: str) -> bool:
    """Whether a document of this type may produce the human proof-of-concept fact.

    Permissive by default. The policy names what it excludes, so a source type it has never
    heard of is admitted: the exclusion is a claim about conference abstracts, and it says
    nothing at all about anything else. A default of refusal would silently disqualify every
    future source, which is the opposite failure and a much quieter one.
    """

    return document_type not in NON_DECISIONAL_FOR_HUMAN_POC
