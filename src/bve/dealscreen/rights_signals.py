"""Word classes for reading rights text (cycle R1 revision 10, review R1v9).

The quote reader (``rights_quote``) and the party-name check (``rights_allow``) sort the words of a text into the
classes below. They are generic deal and geography words, never names of companies, programs or diseases. The
readers fail closed: a class here makes a word *suspect*, and a reader passes a text only when every suspect word is
one it can account for. So a word missing from a class does not open a path into the top tiers; it only stops a
word being recognised as harmless.

Classes:

- ``RIGHT``: words about holding or moving rights, by kind (``right_kind``). A clause may use only the kinds that
  restate its own row (a license may say "licenses", "exclusive", "develop"; it may not say "option" or "holds").
- ``WIDE``: words that reach beyond named places ("worldwide", "other markets", "everywhere", "outside").
- ``TIME``: words that make a grant or an ending later, conditional or contested ("will", "intends", "notice",
  "disputed", "extended").
- ``HEDGE``: words that make an ending partial ("except", "most", "apart from", "still").
- ``SUB_PLACES``: places inside a buyer region that the territory reader does not know ("California", "Ontario",
  "Bavaria"), with the region they belong to.
"""

from __future__ import annotations

import re

#: Kinds of rights words, each a pattern over one lower-case word (hyphens kept).
_RIGHT_KINDS: tuple[tuple[str, str], ...] = (
    ("grant", (r"licen[cs]\w*|grant\w*|exclusiv\w*|non-exclusive|receiv\w*|obtain\w*|rights?|agreements?|deals?|"
              r"contracts?|territory|transaction\w*|signed|sign\w*|entered|enter\w*")),
    ("develop", (r"develop\w*|manufactur\w*|commerciali[sz]\w*|market|marketing|sell|distribut\w*|royalt\w*|"
                r"milestones?|upfront|payments?|fees?|equity|invest\w*|supply|regulatory|registration")),
    ("transfer", r"transferr?\w*|assign\w*"),
    ("option", r"options?|opt-?in|opt|opts|opted|exercis\w*|unexercised"),
    ("codev", (r"co-?develop\w*|co-?commerciali[sz]\w*|co-?promot\w*|co-?exclusiv\w*|co-?market\w*|joint\w*|"
              r"collaborat\w*|partner\w*|alliance\w*|shar\w*")),
    ("end", (r"terminat\w*|return\w*|revert\w*|reversion|regain\w*|reacquir\w*|end|ends|ended|ending|lapse\w*|"
            r"expir\w*|discontinu\w*|cancel\w*|rescind\w*|withdr[ae]w\w*|exit\w*")),
    ("acquire", (r"acqui\w*|merg\w*|purchas\w*|buy|buys|bought|takeover|tender|shares?|shareholders?|stake|"
                r"subsidiary|amalgamat\w*|sold|sell\w*|outstanding|completed?|completes|closed|wholly|owned|"
                r"definitive")),
    ("hold", (r"hold|holds|holding|holder|holders|held|belong\w*|retain\w*|keep\w*|kept|own|owns|owner\w*|controls?|controlled|possess\w*|"
             r"in-?licen\w*|out-?licen\w*|sub-?licen\w*|re-?licen\w*|"
             r"novat\w*|divest\w*|spun|spin\w*")),
    ("reach", (r"negotiat\w*|refusal|rofn|rofr|rofo|buy-?out|veto|pre-?emption|preemption|expan\w*|"
              r"first-?look|first-?refusal|first-?negotiation")),
)
_RIGHT = [(kind, re.compile(rf"^(?:{pattern})$")) for kind, pattern in _RIGHT_KINDS]

#: The kinds each row type may use when it restates itself. Anything else in a clause blocks.
RESTATES: dict[str, frozenset[str]] = {
    "LICENSE": frozenset({"grant", "develop", "transfer"}),
    "OPTION": frozenset({"grant", "develop", "option"}),
    "OPTION_EXERCISED": frozenset({"grant", "develop", "option"}),
    "CO_DEVELOPMENT": frozenset({"grant", "develop", "codev"}),
    "CO_PROMOTION_OPTION": frozenset({"grant", "develop", "option", "codev"}),
    "TERMINATION": frozenset({"grant", "develop", "end"}),
    "RIGHTS_RETURNED": frozenset({"grant", "develop", "end"}),
    "OPTION_LAPSED": frozenset({"grant", "option", "end"}),
    "ACQUISITION": frozenset({"grant", "develop", "acquire", "transfer"}),
}

#: Words that reach beyond named places. "global" and "international" before a clinical or corporate word
#: ("global phase 3 trial", "international headquarters") are removed before reading (``ORDINARY_WIDE``).
WIDE = re.compile(r"^(?:world\w*|global\w*|international\w*|everywhere|elsewhere|abroad|overseas|hemispheres?|"
                  r"continent\w*|markets|countries|regions|jurisdictions|geographies|territories|remainder|"
                  r"outside|beyond|excluding|except|ex|ex-\w+|non-\w+|rest|rotw|ww|latam|apac|emea|eu5|"
                  r"ex-?us|ex-?u\.s\.?|exregion)$")
ORDINARY_WIDE = re.compile(r"\b(?:global|international|worldwide)\s+(?:clinical\s+|pivotal\s+|registrational\s+)?"
                           r"(?:phase|trials?|stud(?:y|ies)|headquarters?|leader|company|biopharmaceutical|"
                           r"pharmaceutical|health\w*|network|presence|footprint|team|organi[sz]ation|"
                           r"biotechnology|offices?|sites?|patients?)\b", re.IGNORECASE)
#: "a treatment option", "therapeutic options": not an option over rights.
ORDINARY_OPTION = re.compile(r"\b(?:treatment|therapeutic|therapy|therapies|care|dosing|standard)\s+options?\b",
                             re.IGNORECASE)

#: Words that make a grant or an ending later, conditional or contested.
TIME = re.compile(r"^(?:will|shall|would|may|might|could|intends?|intended|intention|plans?|planned|planning|"
                  r"expects?|expected|anticipat\w*|effective|effect|notice|notif\w*|pending|until|upon|once|later|"
                  r"next|future|soon|schedul\w*|propos\w*|subject|conditions?|conditional\w*|closing|consummat\w*|"
                  r"transition\w*|disput\w*|arbitrat\w*|litigat\w*|contest\w*|challeng\w*|extend\w*|extension|"
                  r"renew\w*|still|continu\w*|remain\w*|stay\w*|thereafter|thereon|whereupon|tbd|tba|tbc|"
                  r"negotiating|discussions?|talks|considering|evaluat\w*|explor\w*)$")
#: The time words a grant row may use: a license announced as "X will receive exclusive rights", "subject to
#: customary closing conditions". On a row that ends rights, every time word blocks.
GRANT_TIME = frozenset({"will", "shall", "would", "subject", "conditions", "condition", "closing", "consummation",
                        "upon", "effective", "effect", "pending", "customary"})
#: Words that make an ending partial.
HEDGE = re.compile(r"^(?:except\w*|exception\w*|exclud\w*|apart|save|most|some|certain|part|partial\w*|partly|"
                   r"portion\w*|majority|minority|only|limited|other|others|remaining|plus|otherwise|besides|"
                   r"instead|aside)$")

#: Capitalised tokens that are signals, not names, read case-insensitively ("ROFN", "ROTW", "TBD", "WW").
CAP_SIGNALS = frozenset({"rofn", "rofr", "rofo", "row", "rotw", "ww", "na", "latam", "apac", "emea", "eu5", "tbd",
                         "tba", "tbc", "plus"})
#: Compass and area words: inside a party name they make it a place ("Tessaly Pharma North").
AREA_WORDS = frozenset({"north", "south", "east", "west", "northern", "southern", "eastern", "western", "central",
                        "mainland", "greater", "pacific", "atlantic", "nordic", "nordics", "baltic", "iberia",
                        "scandinavia", "benelux", "dach", "else", "elsewhere", "everywhere", "beyond", "remainder",
                        "rest", "other", "others", "otherwise", "abroad", "overseas", "hemisphere", "continental",
                        "upon", "exercise", "veto", "pre-emption", "preemption", "thereafter", "thereon"})

_US = ("alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii idaho "
       "illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota mississippi "
       "missouri montana nebraska nevada ohio oklahoma oregon pennsylvania tennessee texas utah vermont virginia "
       "washington wisconsin wyoming guam stateside")
_US_MULTI = ("new hampshire|new jersey|new mexico|new york|north carolina|north dakota|rhode island|south carolina|"
             "south dakota|west virginia|puerto rico|district of columbia|virgin islands|american samoa|"
             "northern mariana islands")
_CA = "alberta manitoba ontario quebec saskatchewan yukon nunavut"
_CA_MULTI = "british columbia|new brunswick|newfoundland and labrador|nova scotia|prince edward island|northwest territories"
_EU = ("austria belgium bulgaria croatia cyprus czechia denmark estonia finland france germany greece hungary ireland "
       "italy latvia lithuania luxembourg malta netherlands poland portugal romania slovakia slovenia spain sweden "
       "bavaria")
_EU_MULTI = "czech republic"
_UK = "england scotland wales"
_UK_MULTI = "northern ireland"
#: Places inside a buyer region the territory reader does not name, with the region.
SUB_PLACES: dict[str, str] = {
    **dict.fromkeys(_US.split(), "US"), **dict.fromkeys(_US_MULTI.split("|"), "US"),
    **dict.fromkeys(_CA.split(), "CA"), **dict.fromkeys(_CA_MULTI.split("|"), "CA"),
    **dict.fromkeys(_EU.split(), "EU"), **dict.fromkeys(_EU_MULTI.split("|"), "EU"),
    **dict.fromkeys(_UK.split(), "UK"), **dict.fromkeys(_UK_MULTI.split("|"), "UK"),
}
SUB_PLACE = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, SUB_PLACES), key=len, reverse=True)) + r")\b",
                       re.IGNORECASE)


def right_kind(word: str) -> str | None:
    """The rights kind of one lower-case word, or None."""
    for kind, pattern in _RIGHT:
        if pattern.match(word):
            return kind
    return None


def signal(word: str) -> str | None:
    """Why a lower-case word is suspect: 'right:<kind>', 'wide', 'time', 'hedge', or None for an ordinary word."""
    kind = right_kind(word)
    if kind:
        return f"right:{kind}"
    if WIDE.match(word):
        return "wide"
    if TIME.match(word):
        return "time"
    if HEDGE.match(word):
        return "hedge"
    return None


def sub_places(text: str) -> frozenset[str]:
    """Buyer regions named through a place the territory reader does not know ("Puerto Rico" -> US)."""
    return frozenset(SUB_PLACES[m.group(0).casefold()] for m in SUB_PLACE.finditer(text))


__all__ = ["AREA_WORDS", "CAP_SIGNALS", "GRANT_TIME", "HEDGE", "ORDINARY_OPTION", "ORDINARY_WIDE", "RESTATES",
           "SUB_PLACES", "TIME", "WIDE", "right_kind", "signal", "sub_places"]
