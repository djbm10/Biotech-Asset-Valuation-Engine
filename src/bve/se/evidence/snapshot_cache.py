"""Read each sealed snapshot once per run instead of once per hit.

Discovery attaches several hits to the same document -- a single CT.gov protocol answers
more than one compiled query, and the M17 run produced 56,395 hits over 15,454 records --
and extraction re-read and re-parsed the file, then re-serialized it canonically, once for
every one of them. The bytes cannot have changed in between: a snapshot is content-
addressed and, under custody, sealed and immutable for the whole run. So the repeat work is
pure overhead, and removing it cannot change what is extracted.

This is the only kind of optimization this layer accepts. Discovery is 92% of a run's
runtime and is live HTTP against 1,265 distinct queries; that cost is what strict live
convergence *is*, and it is not available to be cached away.

**Contract:** the returned object is shared. Callers read it and must not mutate it. Every
extractor here treats a snapshot as a read-only record, which is why sharing is safe.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

#: Enough for the documents one run touches without holding an unbounded corpus in memory.
#: A miss costs exactly what the uncached path always cost, so the bound is a memory
#: decision rather than a correctness one.
_CACHE_SIZE = 4096


def _stat_key(path: Path) -> tuple[str, int, int]:
    """Identity of the bytes, not just of the name.

    A snapshot directory is rewritten between runs in the same process during tests, and a
    cache keyed on the path alone would then serve the previous run's document.
    """

    stat = path.stat()
    return (str(path), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=_CACHE_SIZE)
def _load(key: tuple[str, int, int]) -> dict:
    return json.loads(Path(key[0]).read_text())


@lru_cache(maxsize=_CACHE_SIZE)
def _text(key: tuple[str, int, int]) -> str:
    return Path(key[0]).read_text(encoding="utf-8", errors="replace")


@lru_cache(maxsize=_CACHE_SIZE)
def _canonical(key: tuple[str, int, int]) -> str:
    return json.dumps(_load(key), sort_keys=True, separators=(",", ":"))


def load_json(path: Path | str) -> dict:
    """The parsed snapshot. Shared and read-only; see the module contract."""

    return _load(_stat_key(Path(path)))


def load_text(path: Path | str) -> str:
    """The snapshot's text, decoded the same way the uncached read decoded it."""

    return _text(_stat_key(Path(path)))


def canonical_json(path: Path | str) -> str:
    """The snapshot serialized canonically, as the evidence locator records it."""

    return _canonical(_stat_key(Path(path)))


def clear() -> None:
    """Drop everything. For tests, and for a caller that has replaced a snapshot tree."""

    _load.cache_clear()
    _text.cache_clear()
    _canonical.cache_clear()
