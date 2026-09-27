"""A trial's phase belongs to what the trial investigates.

Policy: ``docs/se_policies/trial_stage_attribution.md``.
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
    "armGroupLabels": ["CAR-T"],
}
CY = {
    "name": "Cyclophosphamide",
    "type": "DRUG",
    "description": "Cyclophosphamide will be given at 250 mg/m2/day for 3 days prior to CAR-T infusion.",
    "armGroupLabels": ["CAR-T"],
}
FLU = {
    "name": "Fludarabine",
    "type": "DRUG",
    "description": "Fludarabine 25 mg/m2/day.",
    "armGroupLabels": ["CAR-T"],
}


def _protocol(interventions, *, title="Anti-CD19-CAR-T Cells in B Cell Malignancies", arms=None):
    return {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": title},
        "armsInterventionsModule": {
            "interventions": interventions,
            "armGroups": arms
            if arms is not None
            else [
                {
                    "label": "CAR-T",
                    "type": "EXPERIMENTAL",
                    "interventionNames": [
                        f"{i['type'].title()}: {i['name']}" for i in interventions
                    ],
                }
            ],
        },
    }


class TestAttributed:
    def test_the_titled_investigational_product(self) -> None:
        protocol = _protocol([CAR_T, CY, FLU])
        assert (
            stage_attribution(protocol, "Anti-CD19-CAR-T cells") == "STAGE_FROM_TITLED_INTERVENTION"
        )

    def test_a_car_t_description_mentioning_lymphodepletion_is_not_support(self) -> None:
        protocol = _protocol([CAR_T], title="A Study in Lymphoma")
        assert (
            stage_attribution(protocol, "Anti-CD19-CAR-T cells") == "STAGE_FROM_SOLE_INTERVENTION"
        )

    def test_a_title_derived_hit_is_the_trial_subject(self) -> None:
        protocol = _protocol([CY, FLU])
        title = protocol["identificationModule"]["briefTitle"]
        assert stage_attribution(protocol, title) == "STAGE_FROM_TRIAL_TITLE_SUBJECT"

    def test_an_other_name_matches_the_intervention(self) -> None:
        product = {**CAR_T, "name": "Axicabtagene Ciloleucel", "otherNames": ["KTE-C19"]}
        protocol = _protocol([product, FLU], title="Study of Axicabtagene Ciloleucel")
        assert stage_attribution(protocol, "KTE-C19") == "STAGE_FROM_TITLED_INTERVENTION"


class TestWithheld:
    def test_a_conditioning_agent_that_names_its_own_timing(self) -> None:
        assert (
            stage_attribution(_protocol([CAR_T, CY, FLU]), "Cyclophosphamide")
            == "WITHHELD_SUPPORT_ROLE"
        )

    def test_a_support_term_in_the_intervention_name(self) -> None:
        bridging = {**FLU, "name": "Bridging radiotherapy"}
        protocol = _protocol([CAR_T, bridging])
        assert stage_attribution(protocol, "Bridging radiotherapy") == "WITHHELD_SUPPORT_ROLE"

    def test_an_untitled_partner_in_the_same_arm(self) -> None:
        assert (
            stage_attribution(_protocol([CAR_T, CY, FLU]), "Fludarabine")
            == "WITHHELD_AMBIGUOUS_PARTNER"
        )

    def test_a_comparator_arm_drug(self) -> None:
        chemo = {**FLU, "name": "R-GDP", "armGroupLabels": ["SOC"]}
        arms = [
            {
                "label": "CAR-T",
                "type": "EXPERIMENTAL",
                "interventionNames": ["Genetic: Anti-CD19-CAR-T cells"],
            },
            {"label": "SOC", "type": "ACTIVE_COMPARATOR", "interventionNames": ["Drug: R-GDP"]},
        ]
        protocol = _protocol([CAR_T, chemo], title="Anti-CD19-CAR-T Cells versus R-GDP", arms=arms)
        assert stage_attribution(protocol, "R-GDP") == "WITHHELD_NOT_EXPERIMENTAL"

    def test_a_name_on_no_intervention(self) -> None:
        assert stage_attribution(_protocol([CAR_T, CY]), "vincristine") == "WITHHELD_UNRESOLVED"

    def test_after_a_support_term_is_not_a_support_role(self) -> None:
        product = {
            **CAR_T,
            "name": "QH103 Cell Injection",
            "description": "QH103 Cell Injection is given following lymphodepletion with chemotherapy.",
        }
        protocol = _protocol([product], title="Universal CAR-gd T Cells")
        assert stage_attribution(protocol, "QH103 Cell Injection") == "STAGE_FROM_SOLE_INTERVENTION"
