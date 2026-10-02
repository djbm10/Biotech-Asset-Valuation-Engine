"""TARGET_RELATION_READER v1: a target is the argument of an attributive slot, nothing less.

The fixture carries the synonyms that produced the failures, exactly as Open Targets
publishes them -- ``IV`` for ST6GALNAC4, ``CART`` for CARTPT, ``AMG`` for AMELX. They are
here so the collisions are *possible*; a reader that only stays quiet because the
vocabulary never contained the colliding spelling is not being tested.
Policy: ``docs/se_policies/target_relation_reader_v1.md``.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.evidence.construct_targets import (
    intervention_construct_targets,
    intervention_target_reading,
)
from bve.se.evidence.target_relations import (
    Slot,
    first_sentence,
    read_record_loci,
    relations_in,
)
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache

CD19 = "TARGET:CD19"
BCMA = "TARGET:TNFRSF17"
GPRC5D = "TARGET:GPRC5D"
FCRL5 = "TARGET:FCRL5"

#: symbol -> real OT synonyms that matter to the failure classes.
_GENES = {
    "CD19": (),
    "TNFRSF17": ("BCMA",),
    "GPRC5D": (),
    "FCRL5": ("FcRH5",),
    "CD3E": ("CD3",),
    "ST6GALNAC4": ("IV",),
    "CARTPT": ("CART",),
    "AMELX": ("AMG",),
    "MLPH": ("LN",),
    "PRB4": ("PO",),
    "IL7": ("IL-7",),
    "CCL19": (),
    "IL10": ("IL-10",),
    "IL15": ("IL-15",),
    "CYP3A4": (),
    "CYP2B6": ("P450",),
    "GNRH1": ("LHRH",),
    "HDAC9": ("HDAC",),
    "MAP2K7": ("MEK",),
    "SEPTIN4": ("MART",),
    "F5": (),
    "MLANA": ("MART-1",),
    "TNXA": ("XA",),
}


def _record(index: int, symbol: str, synonyms: tuple[str, ...]) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=f"ENSG{index:011d}",
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=symbol,
        aliases=[SourceAlias(value=value, alias_type=AliasType.SYMBOL) for value in synonyms],
        xrefs={"uniprot": [f"P{index:05d}"]},
    )


@pytest.fixture
def snapshot(tmp_path_factory, monkeypatch):
    snap = OntologySnapshot(
        sources=[
            SourceProvenance(
                source="open_targets",
                release="26.06",
                retrieved_at=date(2026, 8, 15),
                locator="ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06",
            )
        ],
        records=[
            _record(index, symbol, synonyms)
            for index, (symbol, synonyms) in enumerate(sorted(_GENES.items()), start=1)
        ],
    )
    path = tmp_path_factory.mktemp("relations") / "snapshot"
    snap.write(path)
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(path))
    reset_resolver_cache()
    try:
        yield snap
    finally:
        reset_resolver_cache()


def _targets(name: str, description: str = "", other_names=None, kind=None):
    return intervention_construct_targets(
        {"name": name, "description": description, "otherNames": other_names or []},
        intervention_type=kind,
    )


class TestNegativeControls:
    """§4.1: every failure class, each with the colliding spelling present."""

    def test_a_route_abbreviation_is_not_a_target(self, snapshot) -> None:
        assert _targets("Drug A", "anti-CD19 CAR-T cells given IV") == [CD19]

    def test_a_car_head_is_never_read_as_a_gene(self, snapshot) -> None:
        assert _targets("GB5005 CART", "Included patients receive GB5005 T-cell") is None

    def test_a_sponsor_code_prefix_is_not_a_target(self, snapshot) -> None:
        assert _targets(
            "AMG 103", "Anti-CD19 bispecific antibody", ["AMG-103", "AMG103"]
        ) == [CD19]

    def test_a_trial_code_prefix_is_not_a_target(self, snapshot) -> None:
        assert _targets("LN-145", "autologous TIL therapy") is None

    def test_armoring_transgenes_are_not_binding_arms(self, snapshot) -> None:
        assert _targets(
            "CD19 CAR-T Expressing IL7 CCL19",
            "fourth generation CD19 targeting CAR-T expressing IL7 CCL19",
        ) == [CD19]

    def test_a_car_head_juxtaposition_that_contradicts_an_explicit_slot_is_refused(
        self, snapshot
    ) -> None:
        assert _targets("Anti-CD19 IL-10/IL15 CAR-NK") is None

    def test_a_metabolising_enzyme_in_a_warning_is_not_a_target(self, snapshot) -> None:
        assert _targets(
            "Colchicine",
            "Colchicine 0.5 mg. Avoid lopinavir, ritonavir or any other CYP3A4 inhibitor.",
        ) is None

    @pytest.mark.parametrize(
        "name, description",
        [
            ("Cytochrome P450 inhibitor", ""),
            ("Leuprolide", "LHRH agonist"),
            ("Entinostat", "HDAC inhibitor"),
            ("Trametinib", "MEK Inhibitor"),
        ],
    )
    def test_pharmacology_cues_are_not_slots(self, snapshot, name, description) -> None:
        assert _targets(name, description) is None

    def test_another_therapys_target_is_refused(self, snapshot) -> None:
        targets = _targets(
            "Cevostamab",
            "Cevostamab (FcRH5×CD3) demonstrated 30.2% overall response rate in patients "
            "who underwent BCMA-targeted treatment",
        )
        assert BCMA not in (targets or [])

    def test_a_partial_hyphen_split_never_resolves(self, snapshot) -> None:
        targets = _targets("TCR PBL", "anti-MART-1 F5 TCR PBL infusion")
        assert "TARGET:SEPTIN4" not in (targets or [])
        assert "TARGET:F5" not in (targets or [])

    def test_a_two_letter_synonym_cannot_fill_a_slot(self, snapshot) -> None:
        assert _targets("Certoparin", "anti-XA activity monitoring") is None

    def test_a_list_feeding_a_slot_is_refused(self, snapshot) -> None:
        assert _targets("Claudin6, GPRC5D, or CD19 targeting CAR-NK") is None

    def test_a_slot_after_a_history_marker_is_refused(self, snapshot) -> None:
        assert _targets("Drug X", "for patients after prior anti-BCMA CAR-T") is None

    def test_later_description_sentences_are_not_read(self, snapshot) -> None:
        assert _targets("Drug X", "An oral tablet. Patients had BCMA-directed CAR-T.") is None


class TestPositiveControls:
    """§4.2."""

    def test_verbal_slot(self, snapshot) -> None:
        assert _targets(
            "ALLO-715", "ALLO-715 is an allogeneic CAR T cell therapy targeting BCMA"
        ) == [BCMA]

    def test_attributive_suffix_on_a_product_noun(self, snapshot) -> None:
        assert _targets(
            "Equecabtagene Autoleucel Injection (Eque-cel)",
            "Eque-cel is personalized, BCMA-targeted gene-modified autologous T-cell "
            "immunotherapy product. CAR specific to CD19 is not used.",
        ) == [BCMA]

    def test_directed_car_t(self, snapshot) -> None:
        assert _targets(
            "single dose of CNCT19",
            "Autologous 2nd generation CD19-directed CAR-T cells, infusion intravenously.",
        ) == [CD19]

    def test_specific_car_t(self, snapshot) -> None:
        assert _targets("CT053", "CT053 is a fully human BCMA-specific CAR-T") == [BCMA]

    def test_the_cd3_arm_is_an_effector_not_a_target(self, snapshot) -> None:
        assert _targets("CLN-978", "CD19-directed CD3 bispecific T-cell engager") == [CD19]

    def test_anti_prefix(self, snapshot) -> None:
        assert _targets("X", "anti-CD19 CAR-T cells") == [CD19]

    def test_slash_coordinated_dual_car(self, snapshot) -> None:
        assert _targets("BCMA/GPRC5D CAR-T cells") == [GPRC5D, BCMA]

    def test_arm_notation(self, snapshot) -> None:
        assert _targets("Teclistamab (BCMAxCD3)") == [BCMA]
        assert _targets("Cevostamab (FcRH5×CD3)") == [FCRL5]

    def test_a_hyphenated_dual_construct_before_the_head(self, snapshot) -> None:
        assert _targets("Universal BCMA-CD19 CART") == [CD19, BCMA]


class TestRecordRules:
    def test_loci_that_disagree_give_no_fact(self, snapshot) -> None:
        assert _targets("CD19 CAR-T", "BCMA-directed CAR-T cells") is None

    def test_loci_that_agree_give_one_fact(self, snapshot) -> None:
        assert _targets("CD19 CAR-T", "anti-CD19 CAR-T cells") == [CD19]

    def test_an_unresolvable_slot_argument_silences_the_record(self, snapshot) -> None:
        # A construct set must describe the whole construct; half of it is not one.
        assert _targets("ABC-1", "anti-CD19 x anti-ZZZ9 bispecific") is None

    def test_prose_words_in_a_slot_are_not_arguments(self, snapshot) -> None:
        assert _targets("X", "anti-tumor activity of a CD19-directed antibody") == [CD19]

    def test_a_class_noun_modifier_is_refused(self, snapshot) -> None:
        assert _targets("X", "standard anti-CD19 therapy") is None

    def test_non_molecular_records_are_not_read(self, snapshot) -> None:
        assert _targets("RT", "before the CD19 CART cell infusion", kind="RADIATION") is None


class TestProvenance:
    def test_each_relation_names_how_it_was_read(self, snapshot) -> None:
        reading = intervention_target_reading(
            {"name": "CT053", "description": "CT053 is a fully human BCMA-specific CAR-T"},
            intervention_type=None,
        )
        assert reading is not None and reading.targets == (BCMA,)
        (relation,) = reading.relations
        assert relation.slot == Slot.ATTRIBUTIVE_SUFFIX
        assert relation.locus == "description[0]"
        assert relation.surface == "BCMA"
        assert relation.tier == "SYNONYM"
        assert "S2_attributive_suffix:BCMA->TARGET:TNFRSF17" in relation.locator()

    def test_an_approved_symbol_is_tiered_as_such(self, snapshot) -> None:
        (relation,) = relations_in("anti-CD19", "name").relations
        assert relation.tier == "APPROVED"

    def test_a_refusal_says_why(self, snapshot) -> None:
        reading = read_record_loci("Anti-CD19 IL-10/IL15 CAR-NK", [], "")
        assert reading.refusal == "car_head_disagrees_with_explicit_slot"

    def test_reading_is_deterministic(self, snapshot) -> None:
        args = ("BCMA/GPRC5D CAR-T", ["BCMAxCD3"], "anti-BCMA and GPRC5D")
        assert read_record_loci(*args) == read_record_loci(*args)


def test_first_sentence_stops_at_the_first_boundary() -> None:
    assert first_sentence("A CD19 CAR. Dosed 1.0×10^6/kg; daily") == "A CD19 CAR."
