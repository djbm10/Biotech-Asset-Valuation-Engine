"""A trial's phase belongs to its investigational programs.

Policy: ``docs/se_policies/trial_stage_attribution_amendment_6.md`` (+ 6.1). Explicit trial roles
decide; a bare record defers to the drug's other trials, leave-one-out.
"""

from __future__ import annotations

from bve.se.evidence.stage_attribution import StageRoleIndex, stage_attribution, stage_method

EXPLICIT = "STAGE_FROM_EXPLICIT_INVESTIGATIONAL"
STRUCTURED = "STAGE_FROM_STRUCTURED_INTERVENTION"
_counter = iter(range(10_000_000, 99_999_999))


def _int(name, description="", kind="DRUG"):
    return {"name": name, "type": kind, "description": description}


def _arm(label, members, kind="EXPERIMENTAL", description=""):
    return {
        "label": label,
        "type": kind,
        "description": description,
        "interventionNames": [f"Drug: {m['name']}" for m in members],
    }


def _protocol(interventions, *, arms=None, title="A Study in B-cell Lymphoma", official=None):
    return {
        "identificationModule": {
            "nctId": f"NCT{next(_counter)}",
            "briefTitle": title,
            "officialTitle": official,
        },
        "armsInterventionsModule": {
            "interventions": interventions,
            "armGroups": arms if arms is not None else [_arm("Treatment", interventions)],
        },
    }


def _support_trial(drug="Cyclophosphamide"):
    return _protocol([_int("CAR-T X"), _int(drug, "Chemotherapy for lymphodepletion")])


def _investigational_trial(drug="Cyclophosphamide"):
    return _protocol([_int(drug, "Given orally")])


def _bare_trial(drug="Cyclophosphamide"):
    return _protocol([_int("CAR-T X"), _int(drug, "Given IV"), _int("Other Y", "Given IV")])


class TestReasonCodes:
    def test_title_subject(self) -> None:
        protocol = _protocol([_int("Cyclophosphamide")], title="Anti-CD19-CAR-T Cells in NHL")
        assert stage_attribution(protocol, "Anti-CD19-CAR-T Cells in NHL") == (
            "STAGE_FROM_TRIAL_TITLE_SUBJECT"
        )

    def test_unresolved(self) -> None:
        assert stage_attribution(_protocol([_int("Cyclophosphamide")]), "KTE-X19") == (
            "WITHHELD_UNRESOLVED"
        )

    def test_explicit_investigational_sole_product(self) -> None:
        assert stage_attribution(_protocol([_int("KITE-363")]), "KITE-363") == EXPLICIT

    def test_structured_intervention_when_bare_and_no_history(self) -> None:
        protocol = _bare_trial()
        assert stage_attribution(protocol, "Cyclophosphamide", StageRoleIndex()) == STRUCTURED

    def test_control_role(self) -> None:
        drug, new = _int("Rituximab"), _int("AZD0486")
        arms = [_arm("Experimental", [new, drug]), _arm("SOC", [drug], kind="ACTIVE_COMPARATOR")]
        protocol = _protocol([new, drug], arms=arms)
        assert stage_attribution(protocol, "Rituximab") == "WITHHELD_CONTROL_ROLE"
        assert stage_attribution(protocol, "AZD0486") == EXPLICIT

    def test_non_product(self) -> None:
        protocol = _protocol([_int("CAR-T X"), _int("Leukapheresis", kind="PROCEDURE")])
        assert stage_attribution(protocol, "Leukapheresis") == "WITHHELD_NON_PRODUCT"

    def test_support_role(self) -> None:
        assert stage_attribution(_support_trial(), "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"

    def test_support_dominant(self) -> None:
        index = StageRoleIndex.from_protocols([_support_trial() for _ in range(3)])
        assert stage_attribution(_bare_trial(), "Cyclophosphamide", index) == (
            "WITHHELD_SUPPORT_DOMINANT"
        )


class TestReferents:
    def test_tricar_regimen_named_in_own_description(self) -> None:
        # NCT03910842: fludarabine and cyclophosphamide are not registered interventions.
        car = _int(
            "CD19-TriCAR-T/SILK",
            "A conditioning chemotherapy regimen of fludarabine and cyclophosphamide may be "
            "administered, followed by a single infusion of CD19-TriCAR-T cells.",
        )
        assert stage_attribution(_protocol([car]), "CD19-TriCAR-T/SILK") == EXPLICIT

    def test_ala_101_post_conditioning(self) -> None:
        # NCT07518329.
        ala = _int(
            "ALA-101",
            "Single IV infusion of ALA-101 post chemotherapy conditioning with Fludarabine and "
            "Cyclophosphamide",
        )
        flu = _int("Fludarabine", "Given IV")
        protocol = _protocol([ala, flu])
        assert stage_attribution(protocol, "ALA-101") == EXPLICIT
        assert stage_attribution(protocol, "Fludarabine") == "WITHHELD_SUPPORT_ROLE"

    def test_car_nk_treatment_follows_lymphodepletion(self) -> None:
        # NCT05410041.
        car = _int(
            "CAR-NK-CD19 Cells",
            "CAR-NK-CD19 Cells, 1-3x10^7 /KG, treatment follows a lymphodepletion.",
        )
        assert stage_attribution(_protocol([car]), "CAR-NK-CD19 Cells") == EXPLICIT

    def test_arm_description_names_conditioning_agents(self) -> None:
        # NCT07038447: the agents are named inside the phrase, the product after "followed by".
        kite, flu, cy = _int("KITE-363"), _int("Fludarabine", "IV"), _int("Cyclophosphamide", "IV")
        arms = [
            _arm(
                "Phase 1a: KITE-363",
                [kite, flu, cy],
                description="Participants will receive lymphodepleting chemotherapy with "
                "cyclophosphamide and fludarabine followed by 2 dose escalations of KITE-363",
            )
        ]
        protocol = _protocol([kite, flu, cy], arms=arms)
        assert stage_attribution(protocol, "KITE-363") == EXPLICIT
        assert stage_attribution(protocol, "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"
        assert stage_attribution(protocol, "Fludarabine") == "WITHHELD_SUPPORT_ROLE"

    def test_sc291_with_lymphodepleting_therapy(self) -> None:
        sc291 = _int("SC291", "SC291 is an allogeneic CAR T cell therapy")
        arms = [_arm("LN Cohort", [sc291], description="SC291 with lymphodepleting therapy")]
        assert stage_attribution(_protocol([sc291], arms=arms), "SC291") == EXPLICIT

    def test_allo_329_without_lymphodepletion(self) -> None:
        allo, cy = _int("ALLO-329"), _int("Cyclophosphamide", "Chemotherapy for lymphodepletion")
        arms = [
            _arm(
                "ALLO-329",
                [allo],
                description="Participants receive ALLO-329 without a lymphodepletion regimen.",
            ),
            _arm(
                "ALLO-329, Cyclophosphamide",
                [allo, cy],
                description="Participants receive ALLO-329 following lymphodepletion regimen "
                "comprised of cyclophosphamide.",
            ),
        ]
        protocol = _protocol([allo, cy], arms=arms)
        assert stage_attribution(protocol, "ALLO-329") == EXPLICIT
        assert stage_attribution(protocol, "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"

    def test_transpocart19_administered_following(self) -> None:
        car = _int(
            "TranspoCART19",
            "Autologous CD19-directed CAR-T cell therapy administered following lymphodepleting "
            "chemotherapy.",
        )
        assert stage_attribution(_protocol([car]), "TranspoCART19") == EXPLICIT

    def test_before_product_needs_a_subject(self) -> None:
        # Amendment 6.1: the marker opening the clause does not make the CAR-T support.
        car = _int("Anti-CD19 CAR-T cells", "Prior to cellular infusion, patients are assessed.")
        cy = _int(
            "Cyclophosphamide", "Cyclophosphamide will be given for 3 days prior to CAR-T infusion."
        )
        other = _int("NKTR-255", "Given SC")
        protocol = _protocol([car, cy, other])
        assert stage_attribution(protocol, "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"
        assert stage_attribution(protocol, "Anti-CD19 CAR-T cells") != "WITHHELD_SUPPORT_ROLE"


class TestCorpusPrior:
    def test_leave_one_out_at_a_support_trial(self) -> None:
        # Exactly three bare+support trials: at one of them only two others remain.
        bare_support = [
            _protocol(
                [
                    _int("CAR-T X"),
                    _int("Cyclophosphamide", "Given IV"),
                    _int("Other Y", "Given IV"),
                ],
                arms=[
                    _arm(
                        "Treatment",
                        [_int("CAR-T X"), _int("Cyclophosphamide"), _int("Other Y")],
                        description="lymphodepletion with cyclophosphamide",
                    )
                ],
            )
            for _ in range(3)
        ]
        index = StageRoleIndex.from_protocols(bare_support)
        assert index.support_dominant({"cyclophosphamide"}, "NCT-other") is True
        first = bare_support[0]["identificationModule"]["nctId"]
        assert index.support_dominant({"cyclophosphamide"}, first) is False
        assert stage_attribution(_bare_trial(), "Cyclophosphamide", index) == (
            "WITHHELD_SUPPORT_DOMINANT"
        )

    def test_supermajority_boundary(self) -> None:
        three_two = [_support_trial() for _ in range(3)] + [
            _investigational_trial() for _ in range(2)
        ]
        assert (
            stage_attribution(
                _bare_trial(), "Cyclophosphamide", StageRoleIndex.from_protocols(three_two)
            )
            == STRUCTURED
        )
        four_two = [_support_trial() for _ in range(4)] + [
            _investigational_trial() for _ in range(2)
        ]
        assert (
            stage_attribution(
                _bare_trial(), "Cyclophosphamide", StageRoleIndex.from_protocols(four_two)
            )
            == "WITHHELD_SUPPORT_DOMINANT"
        )

    def test_unknown_trials_do_not_enter_the_denominator(self) -> None:
        corpus = [_support_trial() for _ in range(3)] + [_bare_trial() for _ in range(10)]
        index = StageRoleIndex.from_protocols(corpus)
        assert stage_attribution(_bare_trial(), "Cyclophosphamide", index) == (
            "WITHHELD_SUPPORT_DOMINANT"
        )

    def test_mixed_use_drug_keeps_trials_that_study_it(self) -> None:
        index = StageRoleIndex.from_protocols([_support_trial("Lenalidomide") for _ in range(5)])
        drug, other = _int("Lenalidomide", "Given PO"), _int("Rituximab", "Given IV")
        arms = [_arm("Lenalidomide maintenance", [drug, other])]
        protocol = _protocol([drug, other], arms=arms)
        assert stage_attribution(protocol, "Lenalidomide", index) == EXPLICIT


class TestCarriedOver:
    def test_conditional_therapy_partners(self) -> None:
        duo = _int("DuoCAR20.19.22-D95", "Patient derived autologous T cells.")
        flu = _int("Fludarabine (Conditional therapy)", "Lymphodepletion chemotherapy")
        protocol = _protocol([duo, flu])
        assert stage_attribution(protocol, "DuoCAR20.19.22-D95") == EXPLICIT
        assert stage_attribution(protocol, "Fludarabine (Conditional therapy)") == (
            "WITHHELD_SUPPORT_ROLE"
        )

    def test_imaging_partner(self) -> None:
        car = _int("huCART19-IL18-eDHFR cells", "Genetically modified autologous T cells.")
        tracer = _int(
            "[18F]Fluoropropyl-Trimethoprim",
            "Trafficking will be visualized by PET/CT imaging using an investigational imaging agent.",
        )
        protocol = _protocol([car, tracer])
        assert stage_attribution(protocol, "huCART19-IL18-eDHFR cells") == EXPLICIT
        assert stage_attribution(protocol, tracer["name"]) == "WITHHELD_NON_PRODUCT"

    def test_placebo_and_famotidine(self) -> None:
        drug = _int("BMS-986337", "Specified Dose on Specified Days")
        placebo = _int("BMS-986337 Placebo", "Specified Dose on Specified Days", kind="OTHER")
        famotidine = _int("Famotidine", "Specified Dose on Specified Days", kind="BIOLOGICAL")
        protocol = _protocol([drug, placebo, famotidine])
        assert stage_attribution(protocol, "BMS-986337") in (EXPLICIT, STRUCTURED)
        assert stage_attribution(protocol, "BMS-986337 Placebo") == "WITHHELD_CONTROL_ROLE"

    def test_co_administered_products_under_generic_labels(self) -> None:
        cd22 = _int("Autologous, humanized anti-CD22 CAR T cell therapy (CART22-65s)")
        cd19 = _int("Autologous, humanized anti-CD19 CAR T cell therapy (huCART19)")
        arms = [_arm("Dose Finding Arm", [cd22, cd19]), _arm("Expansion Arm", [cd22, cd19])]
        protocol = _protocol([cd22, cd19], arms=arms)
        assert stage_attribution(protocol, cd22["name"], StageRoleIndex()) == STRUCTURED
        assert stage_attribution(protocol, cd19["name"], StageRoleIndex()) == STRUCTURED

    def test_title_annotates_and_never_rescues(self) -> None:
        titled = _protocol([_int("KITE-363")], title="KITE-363 in Autoimmune Disease")
        assert stage_method(titled, "KITE-363", EXPLICIT) == (
            "ctgov_stage:STAGE_FROM_EXPLICIT_INVESTIGATIONAL+TITLE"
        )
        assert stage_method(_protocol([_int("KITE-363")]), "KITE-363", EXPLICIT) == (
            "ctgov_stage:STAGE_FROM_EXPLICIT_INVESTIGATIONAL"
        )
        protocol = _protocol(
            [_int("CAR-T X"), _int("Cyclophosphamide", "Lymphodepletion chemotherapy")],
            title="Cyclophosphamide and CAR-T X",
        )
        assert stage_attribution(protocol, "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"
