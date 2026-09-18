"""Labelling a record against the ontology must not scan every alias in the snapshot.

`targets_in` tested ``term in lowered`` for all 562,413 terms the published snapshot
carries, once per hit. Extraction spent ~4 documents a minute on it -- a ~14 hour stage
for a 3,309-hit run -- while doing nothing an index cannot do exactly. These tests pin
both halves: the answers are identical to the naive scan, and the cost no longer follows
the size of the vocabulary.
"""

from __future__ import annotations

import time

from bve.se.discovery.adapters import QueryVocabulary, _fold


def _terms(*spellings: str) -> tuple[str, ...]:
    """Vocabulary terms arrive already folded; tests must build them the same way."""

    return tuple(sorted({_fold(spelling) for spelling in spellings}))


def _naive(vocabulary: QueryVocabulary, text: str) -> set[str]:
    lowered = _fold(text)
    return {
        canonical
        for canonical, terms in vocabulary.targets
        if any(term in lowered for term in terms)
    }


class TestIndexedMatchingAgreesWithTheNaiveScan:
    def test_the_ordinary_cases_agree(self):
        vocabulary = QueryVocabulary(
            targets=(
                ("PDCD1", _terms("pd-1", "pdcd1", "programmed cell death protein 1")),
                ("CD274", _terms("cd274", "pd-l1")),
                ("ERBB2", _terms("erbb2", "her2")),
            )
        )
        text = "A Study of Anti-PD-1 Therapy in HER2-Positive Tumors"
        assert vocabulary.targets_in(text) == _naive(vocabulary, text)
        assert vocabulary.targets_in(text) == {"PDCD1", "ERBB2"}

    def test_a_term_shorter_than_the_index_prefix_still_matches(self):
        """Short aliases cannot be bucketed by a 4-character prefix; they must not be lost."""

        vocabulary = QueryVocabulary(targets=(("KIT", ("kit",)), ("MET", ("met",))))
        text = "a trial of the kit inhibitor"
        assert vocabulary.targets_in(text) == _naive(vocabulary, text) == {"KIT"}

    def test_an_empty_term_matches_everything_exactly_as_it_did(self):
        """Degenerate, but the naive scan admitted it and an index must not silently differ."""

        vocabulary = QueryVocabulary(targets=(("EMPTY", ("",)),))
        assert vocabulary.targets_in("anything") == _naive(vocabulary, "anything")

    def test_a_term_matches_inside_a_word_as_substring_semantics_require(self):
        vocabulary = QueryVocabulary(targets=(("BRAF", ("braf",)),))
        text = "vemurafenib targets brafv600e"
        assert vocabulary.targets_in(text) == _naive(vocabulary, text) == {"BRAF"}

    def test_case_folding_is_unchanged(self):
        vocabulary = QueryVocabulary(targets=(("PDCD1", ("pdcd1",)),))
        assert vocabulary.targets_in("PDCD1 blockade") == {"PDCD1"}


class TestCostDoesNotFollowVocabularySize:
    def test_a_snapshot_sized_vocabulary_labels_a_record_quickly(self):
        """The published snapshot carries ~562k terms; a record is ~50KB of text."""

        targets = tuple(
            (f"TARGET{i}", (f"alias{i}", f"synonym-{i}", f"gene_symbol_{i}"))
            for i in range(60_000)
        )
        vocabulary = QueryVocabulary(targets=targets)
        text = ("a randomized study of alias7 in advanced solid tumors " * 900)[:50_000]

        vocabulary.targets_in("warm the index")
        started = time.perf_counter()
        found = vocabulary.targets_in(text)
        elapsed = time.perf_counter() - started

        assert "TARGET7" in found
        # The naive scan needs ~180k substring searches over 50KB for this vocabulary and
        # takes seconds. The bound is deliberately loose; it fails only on a rescan.
        assert elapsed < 1.0, f"labelling one record took {elapsed:.2f}s"
