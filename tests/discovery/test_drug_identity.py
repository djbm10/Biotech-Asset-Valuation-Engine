"""Tests for canonical drug identity (code-name extraction + clustering key)."""
from __future__ import annotations

from bve.discovery.drug_identity import (
    canonical_drug_key,
    extract_code_names,
    share_identity,
)


class TestExtractCodeNames:
    def test_simple(self):
        assert extract_code_names("BEAM-201") == ["beam201"]

    def test_space_separator(self):
        assert extract_code_names("BEAM 201") == ["beam201"]

    def test_no_separator(self):
        assert extract_code_names("BEAM201") == ["beam201"]

    def test_in_parenthetical(self):
        assert "beam201" in extract_code_names("Allogeneic anti-CD7 CAR-T cells (BEAM-201)")

    def test_target_token_cd19_excluded(self):
        # CD19 looks like a code name but CD is a target prefix.
        assert "cd19" not in extract_code_names("anti-CD19 CAR-T")

    def test_single_digit_target_excluded(self):
        # CD7 / PD-1 have one digit → never match.
        assert extract_code_names("anti-CD7 PD-1 inhibitor") == []

    def test_il17_excluded(self):
        assert "il17" not in extract_code_names("IL-17 inhibitor")

    def test_multiple_codes(self):
        codes = extract_code_names("RLY-2608 plus VX-121")
        assert "rly2608" in codes and "vx121" in codes


class TestCanonicalDrugKey:
    def test_user_examples_all_same_key(self):
        variants = [
            "BEAM-201",
            "Allogeneic anti-CD7 CAR-T cells (BEAM-201)",
            "BEAM 201",
            "BEAM-201 CAR-T",
        ]
        keys = {canonical_drug_key(v) for v in variants}
        assert keys == {"beam201"}

    def test_synonym_promotes_code(self):
        # Descriptive primary name, code supplied as a synonym.
        assert canonical_drug_key("Allogeneic anti-CD7 CAR-T cells", "BEAM-201") == "beam201"

    def test_generic_fallback(self):
        assert canonical_drug_key("Vutrisiran") == "vutrisiran"

    def test_combo_takes_code(self):
        assert canonical_drug_key("VX-121/tezacaftor/deutivacaftor") == "vx121"

    def test_empty(self):
        assert canonical_drug_key("") == ""


class TestShareIdentity:
    def test_shared_code(self):
        assert share_identity(["BEAM-201"], ["Allogeneic anti-CD7 CAR-T cells (BEAM-201)"]) is True

    def test_different_codes(self):
        assert share_identity(["BEAM-201"], ["BEAM-302"]) is False

    def test_code_vs_generic_no_match(self):
        # One side has a code name, the other doesn't → treated as different.
        assert share_identity(["BEAM-201"], ["Vutrisiran"]) is False

    def test_synonym_bridges_code_and_generic(self):
        # CT.gov synonym set lets a generic truth match a code-named program.
        assert share_identity(["Allogeneic CAR-T", "BEAM-201"], ["BEAM-201"]) is True

    def test_generic_substring(self):
        assert share_identity(["tezacaftor ivacaftor"], ["tezacaftor"]) is True
