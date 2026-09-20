"""Turn a retrieved HTML page into the text a reader would see, and nothing else.

A tag-stripping regex answers the wrong question. It removes what sits between angle
brackets, which leaves the *contents* of ``<script>`` and ``<style>`` standing as if they
were prose -- so a stylesheet's ``currentColor``, a script's ``parentNode`` and an SEO
plugin's schema graph all arrive downstream as things the company said about its pipeline.
Identity and the gates then reason faithfully about text that was never on the page.

So normalization is defined positively: visible text, with the separators that keep words
from adjacent elements apart and the ones inside a word together. What is excluded follows
from that definition rather than from a list of the junk strings any one source produced.

Raw snapshots are untouched; this runs downstream of custody, so a corpus can be re-derived.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_WS_RE = re.compile(r"\s+")
_HAS_MARKUP_RE = re.compile(r"<[a-zA-Z!/?]")

#: Elements whose contents are instructions to the browser, not words on the page. Dropped
#: whole: their text is implementation detail at every depth, not just in their attributes.
#:
#: Each name here is non-content *in itself*. ``head`` is deliberately absent even though
#: nothing in it is rendered: real pages carry unclosed void elements that make a lenient
#: parser nest ``body`` inside ``head``, and excluding a container by position would then
#: silently empty the entire document. Excluding only what is non-content by nature cannot
#: fail that way, and the machine metadata that lives in the head is reached anyway --
#: JSON-LD through ``script``, and everything else through attributes, which are never read.
_NON_CONTENT_TAGS = frozenset(
    {"script", "style", "noscript", "template", "svg", "math", "iframe", "object"}
)

#: Elements that sit *inside* a sentence. Everything else separates one run of text from the
#: next. The distinction is load-bearing in both directions: without a separator "EXB-101"
#: and "Phase 2" in neighbouring cells merge into a token no reader ever saw, and with one
#: everywhere, emphasis inside a word splits "idecabtagene" into "ide cabtagene".
_INLINE_TAGS = frozenset(
    {
        "a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "dfn", "em", "i", "kbd",
        "mark", "q", "rp", "rt", "ruby", "s", "samp", "small", "span", "strong", "sub",
        "sup", "time", "u", "var", "wbr", "font",
    }
)


def html_to_visible_text(raw: str) -> str:
    """Visible page text, whitespace-collapsed.

    Input that was never markup is returned as-is apart from whitespace collapsing: most
    sources hand over plain text, and it must not be subjected to a parser's guess at what
    it might have meant.
    """

    if not _HAS_MARKUP_RE.search(raw):
        return _WS_RE.sub(" ", raw).strip()

    # html.parser keeps fragments as written. The HTML parsers that enforce document
    # structure relocate or discard a bare <td>, which silently drops page text whenever a
    # source hands over part of a page rather than the whole of one.
    soup = BeautifulSoup(raw, "html.parser")

    for tag in soup.find_all(_NON_CONTENT_TAGS):
        tag.decompose()

    # Attributes are never visited: only the parser's text nodes are read, so a class name
    # or a style value cannot become content no matter what it contains.
    for tag in soup.find_all(True):
        if tag.name not in _INLINE_TAGS:
            tag.insert_before(" ")
            tag.insert_after(" ")

    return _WS_RE.sub(" ", soup.get_text("")).strip()
