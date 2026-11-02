"""The words a rights row's quote may use beside a clear position (cycle R1 revision 11, review R1v10).

Revision 10 blocked a quote only on capitalised names it could not place and on words in signal classes; any other
lower-case word passed, so "which has since licensed them to another company" read as a clean return (review R1v10
LOWER). Revision 11 reads every word. A word passes only when it is one of these:

- a grammar word, a press verb, an amount or a date (``FUNCTION_WORDS``);
- a generic drug-development word (``GENERAL_WORDS``);
- a word that restates the row's own type (``ROW_WORDS``): a license may say "licenses" and "royalties", a
  termination "terminated" and "returned" but not "licensed" or "licensee", an acquisition "acquires" and "shares";
- a word from the program's own landscape record (its indication, target, modality and names), which the caller
  passes in, so no disease or target name is written here.

Words that could point at another holder, another place or a later date ("another", "company", "party", "new",
"further", "any") are in no list, and ``NEVER`` keeps them out of the program's own words too. A word missing from
these lists blocks; it cannot open a path into the top tiers.
"""

from __future__ import annotations

import re

from bve.dealscreen.rights import (
    ACQUISITION,
    CO_DEVELOPMENT,
    CO_PROMOTION_OPTION,
    LICENSE,
    OPTION,
    OPTION_EXERCISED,
    OPTION_LAPSED,
    RIGHTS_RETURNED,
    TERMINATION,
)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


#: Grammar, press verbs, amounts. No negation, quantifier or deictic word that could point elsewhere.
FUNCTION_WORDS = _words("""
a an the of in on at to for from by with and or as its it their them they this that these those which who whose
is are was were be been being has have had under into per also both today announced announces announce announcing
said says stated terms term pursuant accordance following after prior now about up approximately total aggregate
million millions billion billions thousand cash percent net sales such than here herein hereby there all full
first second one two three four five six seven eight nine ten its own
""")

#: Generic drug-development words: what the program is, never who holds it.
GENERAL_WORDS = _words("""
antibody antibodies drug drugs conjugate conjugates adc adcs bispecific monoclonal candidate candidates compound
compounds molecule molecules biologic biologics therapy therapies therapeutic treatment treatments treat treating
patients patient cancer cancers tumor tumors tumour tumours solid advanced metastatic unresectable refractory relapsed
clinical trial trials study studies phase preclinical investigational novel potential first-in-class best-in-class
targeting targeted target targets directed positive expressing disease diseases indication indications product
products program programs programme asset assets oncology immunotherapy immuno-oncology medicine medicines therapeutics
breakthrough designation designations orphan fast track priority review food administration agency approval approved
""")

_GRANT = _words("""
license licence licenses licences licensed licensing grant grants granted granting exclusive exclusively
non-exclusive right rights agreement agreements deal transaction territory receive receives received obtain
obtains obtained enter enters entered sign signs signed signing develop develops developed development developing
commercialize commercializes commercialized commercialization commercialise commercialises commercialised
commercialisation commercializing commercialising manufacture manufactures manufacturing market marketing sell
selling sale distribute distribution royalty royalties tiered milestone milestones upfront up-front payment
payments pay pays paid fee fees equity investment invest invests regulatory registration supply eligible
consideration transfer transfers transferred covering covers covered collaboration collaborations
""")
_ENDING = _words("""
right rights agreement agreements license licence collaboration deal exclusive development commercialization
commercialisation commercial termination terminated terminates ended ends returned returns reverted reverts
reversion revert regained regains end reacquired reacquires handed hands back exits exited covering covers covered convenience strategic portfolio
review priorities
""")
_LAPSE = _words("""
option options right rights agreement lapse lapsed lapses expire expired expires expiry unexercised exercise not
did declined declines decline take let without
""")
_ACQUISITION = _words("""
acquire acquires acquired acquisition merger merge merges merged complete completes completed completion close
closes closed tender offer share shares shareholders stockholders stock per cash outstanding wholly owned
wholly-owned definitive agreement transaction deal value valued equity price premium purchase purchases purchased
buy buys bought takeover pay pays paid consideration enterprise sold sell sells sub
""")
#: The words each row type may use to restate itself.
ROW_WORDS: dict[str, frozenset[str]] = {
    LICENSE: _GRANT,
    OPTION: _GRANT | _words("option options exercisable"),
    OPTION_EXERCISED: _GRANT | _words("option options exercise exercised exercises"),
    CO_DEVELOPMENT: _GRANT | _words("""co-develop co-develops co-developed co-development co-commercialize
        co-commercializes co-commercialization co-commercialise co-commercialisation joint jointly collaboration
        collaborate collaborates share shared sharing profits losses costs equally"""),
    CO_PROMOTION_OPTION: _GRANT | _words("option options co-promote co-promotes co-promotion co-promoting"),
    TERMINATION: _ENDING,
    RIGHTS_RETURNED: _ENDING,
    OPTION_LAPSED: _LAPSE,
    ACQUISITION: _ACQUISITION,
}
#: Ending words that are allowed when every date in the clause is on or before the as-of date ("notice of
#: termination, effective March 1, 2025").
DATED_ENDING_WORDS = _words("effective notice notified notification provided provides gave given served delivered")
#: Never read as the program's own words, whatever its record says.
NEVER = _words("""
other others another any every each further additional more remaining rest new newly party parties company
companies holder holders partner partners licensee licensees licensor sublicensee entity affiliate affiliates not no
never none without third
""")
_NUMBER = re.compile(r"^(?:\$|€|£|¥)?\d[\d,.]*%?$|^nct\d+$|^\d+(?:st|nd|rd|th)$")


def program_vocabulary(texts: list[str]) -> frozenset[str]:
    """The program's own words, from its landscape record, minus ``NEVER`` and every signal word."""
    from bve.dealscreen.rights_signals import signal

    words = set()
    for text in texts:
        for w in re.findall(r"[a-z0-9][a-z0-9\-]*(?:\.\d+)*", (text or "").casefold()):
            for part in {w, *w.split("-")}:
                if part and part not in NEVER and not signal(part):
                    words.add(part)
    return frozenset(words)


def is_number(word: str) -> bool:
    return bool(_NUMBER.match(word))


__all__ = ["DATED_ENDING_WORDS", "FUNCTION_WORDS", "GENERAL_WORDS", "NEVER", "ROW_WORDS", "is_number",
           "program_vocabulary"]
