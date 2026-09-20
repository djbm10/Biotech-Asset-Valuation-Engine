"""Decide, per occurrence, whether the source is naming a study rather than a molecule.

``LEAP-004`` and ``AMG 404`` are the same shape, and no reading of either token alone can
separate them: companies name trials the way they name programs. What separates them is the
grammar around the token. One is the name the sentence gives a study; the other is the thing
the study administers. So the rule reads the sentence, and a lexical rule -- a prefix list, a
blacklist of known study families -- could only guess, and would go stale the moment a sponsor
coined a new acronym.

Two consequences follow from that and are the reason this module exists rather than a condition
inlined at the call site.

The verdict is about an *occurrence*, not a string. A code framed as a study in one document is
an intervention in the next, and the exclusion must not travel. So the caller asks about a span,
and a token survives as long as *some* occurrence of it was not study-framed.

And the framing must be explicit. Proximity to "phase" is not evidence: the ASCO title that
contributed ``AMG 404`` reads "A phase 1b study of blinatumomab with the ... antibody AMG 404",
where the study wording belongs to a different noun entirely. Only wording that attaches
*to the code itself* counts.
"""

from __future__ import annotations

import re

#: Wording a source puts between a study's name and the noun "study"/"trial". These describe a
#: trial's design, so they are the vocabulary of the construction rather than a list of things
#: observed in any one corpus -- a sponsor cannot coin a new one the way it coins an acronym.
_DESIGN_WORDS = (
    r"phase\s*[0-9IViv]+\s*(?:/\s*[0-9IViv]+)?[ab]?"
    r"|randomi[sz]ed|open[- ]label|double[- ]blind|single[- ]arm|placebo[- ]controlled"
    r"|multi[- ]?(?:centre|center)|pivotal|registrational|global|international"
    r"|first[- ]in[- ]human|dose[- ](?:escalation|expansion)|extension|pilot"
)

#: What must follow the code for the source to be naming a study with it. The separator admits
#: the colon and comma forms ("KEYNOTE-024: Phase III trial of ...") and the bare apposition
#: ("LEAP-004 Study of ..."), then at most a short run of design wording, then the noun itself.
#: The run is bounded because an unbounded one would reach across a clause and find the "study"
#: belonging to a different subject -- which is precisely the AMG 404 misreading.
#:
#: The noun must be **singular**, because only a singular one names a single study. The plural
#: is what conference session categories are called: "PB1983 TRIALS IN PROGRESS: PHASE II STUDY
#: OF PHE885" numbers an abstract and then announces a category, and reading that as "PB1983 is
#: the name of a trial" costs a real candidate. "The LEAP-004 trial" names a study; "LEAP-004
#: trials" names none.
#:
#: "Trial-in-progress" is excluded for the same reason from the other direction: it is a
#: conference *session category*, not a description of a study. It is the taxonomy ASCO
#: numbers with TPS####, and "PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF PHE885" uses it
#: to classify an abstract whose number happens to precede it. Reading that as "PB1983 names
#: a trial" would veto a real candidate on the strength of a heading.
_STUDY_FRAMING_RE = re.compile(
    rf"\A\s*[:,;–—-]?\s*(?:(?:{_DESIGN_WORDS})[\s,-]+){{0,3}}"
    rf"(?:study|trial)\b(?![-\s]*in[-\s]*progress)",
    re.IGNORECASE,
)

#: How far after the code to look. A study's name and the noun naming it are adjacent modulo a
#: short design phrase; anything further away belongs to another clause.
_LOOKAHEAD = 80


def frames_a_study(text: str, start: int, end: int) -> bool:
    """Whether ``text[start:end]`` is being used as the name of a clinical study.

    ``True`` means the source itself said so -- not that the token looks like a study name,
    which is a judgement nothing in the token supports.

    Only what follows the code is read. English puts the naming noun after the name in every
    form of this construction -- "LEAP-004 Study of", "the LEAP-004 trial", "KEYNOTE-024:
    Phase III trial" -- so a preceding article adds nothing the forward rule does not already
    have, while wording further back belongs to whatever else the sentence is about.
    """

    return _STUDY_FRAMING_RE.match(text[end : end + _LOOKAHEAD]) is not None
