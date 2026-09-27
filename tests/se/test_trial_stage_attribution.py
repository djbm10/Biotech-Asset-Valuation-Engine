"""A trial's phase belongs to what the trial investigates.

Policy: ``docs/se_policies/trial_stage_attribution.md`` with Amendments 1 and 2.
"""

from __future__ import annotations

from bve.se.evidence.stage_attribution import stage_attribution

CAR_T = {
    "name": "Anti-CD19-CAR-T cells",
    "type": "GENETIC",
    "description": (
        "Each subject will be infused with a single dose of anti-CD19-CAR-T cells. Prior to "
        "cellular infusion, patients receive lymphodepletion with fludarabine."
    ),
}
CY = {
    "name": "Cyclophosphamide",
    "type": "DRUG",
    "description": "Cyclophosphamide will be given at 250 mg/m2/day for 3 days prior to CAR-T infusion.",
}
FLU = {"name": "Fludarabine", "type": "DRUG", "description": "Fludarabine 25 mg/m2/day."}


def _arm(label, members, kind="EXPERIMENTAL"):
    return {
        "label": label,
        "type": kind,
        "interventionNames": [f"Drug: {m['name']}" for m in members],
    }


def _protocol(interventions, *, arms=None, title="A Study in B-cell Lymphoma", official=None):
    return {
        "identificationModule": {
            "nctId": "NCT00000001",
            "briefTitle": title,
            "officialTitle": official,
        },
        "armsInterventionsModule": {
            "interventions": interventions,
            "armGroups": arms if arms is not None else [_arm("Treatment", interventions)],
        },
    }


class TestAttributed:
    def test_sole_intervention(self) -> None:
        assert (
            stage_attribution(_protocol([CAR_T]), CAR_T["name"]) == "STAGE_FROM_SOLE_INTERVENTION"
        )

    def test_a_car_t_is_the_sole_product_among_conditioning_agents(self) -> None:
        # Cyclophosphamide is the agent of its own "prior to CAR-T infusion" clause; fludarabine is
        # the agent of "lymphodepletion with fludarabine" in the CAR-T's description.
        protocol = _protocol([CAR_T, CY, FLU])
        assert stage_attribution(protocol, CAR_T["name"]) == "STAGE_FROM_SOLE_PRODUCT"

    def test_a_title_derived_hit_is_the_trial_subject(self) -> None:
        protocol = _protocol([CY, FLU], title="Anti-CD19-CAR-T Cells in B Cell Malignancies")
        title = protocol["identificationModule"]["briefTitle"]
        assert stage_attribution(protocol, title) == "STAGE_FROM_TRIAL_TITLE_SUBJECT"

    def test_basket_products_are_each_named_by_their_arm(self) -> None:
        kym = {
            "name": "KYMRIAH",
            "type": "DRUG",
            "description": "CD19-directed T cell immunotherapy",
        }
        yes = {
            "name": "YESCARTA",
            "type": "DRUG",
            "description": "CD19-directed T cell immunotherapy",
        }
        flu = {"name": "Fludarabine 30mg/m2 3 doses", "type": "DRUG", "description": "30 mg/m2 IV"}
        arms = [
            _arm("ARM A: Kymriah refractory ALL", [kym, flu]),
            _arm("ARM B: Yescarta refractory DLBCL", [yes, flu]),
        ]
        protocol = _protocol([kym, yes, flu], arms=arms)
        assert stage_attribution(protocol, "KYMRIAH") == "STAGE_FROM_ARM_LABEL"
        assert stage_attribution(protocol, "YESCARTA") == "STAGE_FROM_ARM_LABEL"
        assert stage_attribution(protocol, flu["name"]) == "WITHHELD_AMBIGUOUS_PARTNER"

    def test_an_observed_short_name_matches_the_arm_label(self) -> None:
        cart22 = {"name": "CART22-65s cells", "type": "BIOLOGICAL", "description": "anti-CD22"}
        hu19 = {"name": "huCART19 Cells", "type": "BIOLOGICAL", "description": "anti-CD19"}
        arms = [
            _arm("CART22-65s monotherapy", [cart22]),
            _arm("CART22-65s in combination with huCART19", [cart22, hu19]),
        ]
        protocol = _protocol([cart22, hu19], arms=arms)
        assert stage_attribution(protocol, "huCART19 Cells") == "STAGE_FROM_ARM_LABEL"

    def test_an_other_name_matches_the_intervention(self) -> None:
        product = {**CAR_T, "name": "Axicabtagene Ciloleucel", "otherNames": ["KTE-C19"]}
        assert stage_attribution(_protocol([product]), "KTE-C19") == "STAGE_FROM_SOLE_INTERVENTION"


def test_a_formulation_word_is_not_required_by_an_identity_match() -> None:
    # Amendment 3 strips the word for label matching only; identity still needs the full name.
    hu19 = {"name": "huCART19 Cells", "type": "BIOLOGICAL", "description": "anti-CD19"}
    assert stage_attribution(_protocol([hu19, FLU]), "huCART19") == "WITHHELD_UNRESOLVED"


class TestSupportIsAClauseRelation:
    def test_the_product_after_before_is_the_reference_point(self) -> None:
        ucart = {
            "name": "CD19-UCART",
            "type": "BIOLOGICAL",
            "description": (
                "A conditioning therapy with cyclophosphamide and fludarabine will be conducted "
                "before CD19-UCART injection. VP16 can be added to the conditioning therapy."
            ),
        }
        assert stage_attribution(_protocol([ucart]), "CD19-UCART") == "STAGE_FROM_SOLE_INTERVENTION"

    def test_the_product_after_followed_by_is_the_reference_point(self) -> None:
        ytb = {
            "name": "Rapcabtagene autoleucel (YTB323)",
            "type": "BIOLOGICAL",
            "description": (
                "Participants undergo leukapheresis for cell collection, receive lymphodepleting "
                "chemotherapy, followed by a single intravenous infusion of rapcabtagene "
                "autoleucel (YTB323)."
            ),
        }
        assert stage_attribution(_protocol([ytb]), ytb["name"]) == "STAGE_FROM_SOLE_INTERVENTION"

    def test_the_product_after_during_is_the_reference_point(self) -> None:
        jw = {
            "name": "JWCAR029",
            "type": "BIOLOGICAL",
            "description": (
                "During JWCAR029 production, subjects will receive a conditioning chemotherapy "
                "regimen of cyclophosphamide and fludarabine."
            ),
        }
        assert stage_attribution(_protocol([jw]), "JWCAR029") == "STAGE_FROM_SOLE_INTERVENTION"

    def test_the_product_before_after_is_the_reference_point(self) -> None:
        # Amendment 4: the marker lies between the product and the support term.
        bre = {
            "name": "Breyanzi Injectable Product",
            "type": "DRUG",
            "description": "Infuse BREYANZI 2 to 7 days after completion of lymphodepleting chemotherapy.",
        }
        flu = {"name": "Fludarabine", "type": "DRUG", "description": "30 mg/m2 IV"}
        arms = [_arm("Arm E: Breyanzi relapsed LBCL", [bre, flu])]
        protocol = _protocol([bre, flu], arms=arms)
        assert stage_attribution(protocol, bre["name"]) == "STAGE_FROM_ARM_LABEL"


class TestWithheld:
    def test_a_conditioning_agent_that_names_its_own_timing(self) -> None:
        assert (
            stage_attribution(_protocol([CAR_T, CY, FLU]), "Cyclophosphamide")
            == "WITHHELD_SUPPORT_ROLE"
        )

    def test_an_agent_named_in_another_interventions_support_clause(self) -> None:
        assert (
            stage_attribution(_protocol([CAR_T, CY, FLU]), "Fludarabine") == "WITHHELD_SUPPORT_ROLE"
        )

    def test_a_support_term_in_the_intervention_name(self) -> None:
        bridging = {**FLU, "name": "Bridging radiotherapy"}
        protocol = _protocol([CAR_T, bridging])
        assert stage_attribution(protocol, "Bridging radiotherapy") == "WITHHELD_SUPPORT_ROLE"

    def test_a_comparator_arm_drug(self) -> None:
        chemo = {"name": "R-GDP", "type": "DRUG", "description": "Given IV"}
        arms = [_arm("CAR-T", [CAR_T]), _arm("SOC", [chemo], "ACTIVE_COMPARATOR")]
        protocol = _protocol([CAR_T, chemo], arms=arms, title="Anti-CD19-CAR-T Cells versus R-GDP")
        assert stage_attribution(protocol, "R-GDP") == "WITHHELD_NOT_EXPERIMENTAL"

    def test_a_titled_backbone_shared_with_the_control_arm(self) -> None:
        bispecific = {"name": "AZD0486", "type": "DRUG", "description": "IgG4 bispecific"}
        backbone = {"name": "R-mini-CHOP", "type": "DRUG", "description": "Rituximab 375 mg/m2"}
        arms = [
            _arm("Arm A: R-mini-CHOP with AZD0486", [bispecific, backbone]),
            _arm("Arm B: R-mini-CHOP", [backbone], "ACTIVE_COMPARATOR"),
        ]
        protocol = _protocol(
            [bispecific, backbone],
            arms=arms,
            official="R-mini-CHOP x2 Followed by AZD0486 Versus R-mini-CHOP x6",
        )
        assert stage_attribution(protocol, "R-mini-CHOP") == "WITHHELD_NOT_EXPERIMENTAL"
        assert stage_attribution(protocol, "AZD0486") == "STAGE_FROM_SOLE_PRODUCT"

    def test_a_titled_partner_is_not_studied_on_the_title_alone(self) -> None:
        partner = {"name": "Lenalidomide", "type": "DRUG", "description": "Given PO"}
        product = {"name": "MOR00208", "type": "BIOLOGICAL", "description": "Given IV"}
        protocol = _protocol(
            [product, partner],
            arms=[_arm("Treatment", [product, partner])],
            title="MOR00208 in Combination With Lenalidomide",
        )
        assert stage_attribution(protocol, "Lenalidomide") == "WITHHELD_AMBIGUOUS_PARTNER"

    def test_a_name_on_no_intervention(self) -> None:
        assert stage_attribution(_protocol([CAR_T, CY]), "vincristine") == "WITHHELD_UNRESOLVED"


class TestTitleIsCorroboration:
    def test_title_annotates_an_attributed_grant(self) -> None:
        from bve.se.evidence.stage_attribution import stage_method

        protocol = _protocol([CAR_T], title="Anti-CD19-CAR-T cells for Lymphoma")
        reason = stage_attribution(protocol, CAR_T["name"])
        assert (
            stage_method(protocol, CAR_T["name"], reason)
            == "ctgov_stage:STAGE_FROM_SOLE_INTERVENTION+TITLE"
        )

    def test_no_title_no_annotation(self) -> None:
        from bve.se.evidence.stage_attribution import stage_method

        protocol = _protocol([CAR_T])
        reason = stage_attribution(protocol, CAR_T["name"])
        assert (
            stage_method(protocol, CAR_T["name"], reason)
            == "ctgov_stage:STAGE_FROM_SOLE_INTERVENTION"
        )
