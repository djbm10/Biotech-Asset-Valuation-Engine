"""A trial's phase belongs to its investigational programs.

Policy: ``docs/se_policies/trial_stage_attribution_amendment_5.md``. Stage is kept unless the
intervention's own record or arm links give positive evidence that it is not the program.
"""

from __future__ import annotations

from bve.se.evidence.stage_attribution import stage_attribution, stage_method

ATTRIBUTED = "STAGE_FROM_STRUCTURED_INTERVENTION"


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
            "nctId": "NCT00000001",
            "briefTitle": title,
            "officialTitle": official,
        },
        "armsInterventionsModule": {
            "interventions": interventions,
            "armGroups": arms if arms is not None else [_arm("Treatment", interventions)],
        },
    }


class TestReasonCodes:
    def test_title_subject(self) -> None:
        protocol = _protocol([_int("Cyclophosphamide")], title="Anti-CD19-CAR-T Cells in NHL")
        assert stage_attribution(protocol, "Anti-CD19-CAR-T Cells in NHL") == (
            "STAGE_FROM_TRIAL_TITLE_SUBJECT"
        )

    def test_unresolved(self) -> None:
        protocol = _protocol([_int("Cyclophosphamide")])
        assert stage_attribution(protocol, "KTE-X19") == "WITHHELD_UNRESOLVED"

    def test_structured_intervention(self) -> None:
        protocol = _protocol([_int("KITE-363")])
        assert stage_attribution(protocol, "KITE-363") == ATTRIBUTED

    def test_control_role_by_arm(self) -> None:
        drug = _int("Rituximab")
        new = _int("AZD0486")
        arms = [_arm("Experimental", [new, drug]), _arm("SOC", [drug], kind="ACTIVE_COMPARATOR")]
        protocol = _protocol([new, drug], arms=arms)
        assert stage_attribution(protocol, "Rituximab") == "WITHHELD_CONTROL_ROLE"
        assert stage_attribution(protocol, "AZD0486") == ATTRIBUTED

    def test_non_product_by_type(self) -> None:
        protocol = _protocol([_int("CAR-T X"), _int("Leukapheresis", kind="PROCEDURE")])
        assert stage_attribution(protocol, "Leukapheresis") == "WITHHELD_NON_PRODUCT"

    def test_support_role_by_own_description(self) -> None:
        cy = _int("Cyclophosphamide", "Chemotherapy for lymphodepletion")
        protocol = _protocol([_int("ALLO-329"), cy])
        assert stage_attribution(protocol, "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"


class TestRegistryCases:
    def test_sole_product_with_lymphodepletion_in_arm_description(self) -> None:
        # NCT06294236: arm descriptions are not read.
        sc291 = _int("SC291", "SC291 is an allogeneic CAR T cell therapy", kind="BIOLOGICAL")
        arms = [_arm("LN Cohort", [sc291], description="SC291 with lymphodepleting therapy")]
        assert stage_attribution(_protocol([sc291], arms=arms), "SC291") == ATTRIBUTED

    def test_product_description_referring_to_lymphodepletion(self) -> None:
        # NCT07799116: the support term follows a temporal marker, so it is a reference point.
        car = _int(
            "TranspoCART19",
            "Autologous CD19-directed CAR-T cell therapy administered following lymphodepleting "
            "chemotherapy. After leukapheresis and manufacturing, participants receive it.",
        )
        assert stage_attribution(_protocol([car]), "TranspoCART19") == ATTRIBUTED

    def test_prior_to_infusion_sentence_in_product_description(self) -> None:
        car = _int(
            "Anti-CD19-CAR-T cells",
            "Prior to cellular infusion, patients receive lymphodepletion with fludarabine.",
        )
        protocol = _protocol([car, _int("Fludarabine", "Fludarabine 25 mg/m2/day.")])
        assert stage_attribution(protocol, "Anti-CD19-CAR-T cells") == ATTRIBUTED

    def test_conditional_therapy_partners_are_support(self) -> None:
        # NCT06879340.
        duo = _int("DuoCAR20.19.22-D95", "Patient derived autologous T cells.")
        flu = _int("Fludarabine (Conditional therapy)", "Lymphodepletion chemotherapy")
        protocol = _protocol([duo, flu])
        assert stage_attribution(protocol, "DuoCAR20.19.22-D95") == ATTRIBUTED
        assert stage_attribution(protocol, "Fludarabine (Conditional therapy)") == (
            "WITHHELD_SUPPORT_ROLE"
        )

    def test_imaging_partner_is_non_product(self) -> None:
        # NCT07343934.
        car = _int("huCART19-IL18-eDHFR cells", "Genetically modified autologous T cells.")
        tracer = _int(
            "[18F]Fluoropropyl-Trimethoprim",
            "Trafficking will be visualized by PET/CT imaging using an investigational "
            "radiolabeled imaging agent.",
        )
        protocol = _protocol([car, tracer])
        assert stage_attribution(protocol, "huCART19-IL18-eDHFR cells") == ATTRIBUTED
        assert stage_attribution(protocol, "[18F]Fluoropropyl-Trimethoprim") == (
            "WITHHELD_NON_PRODUCT"
        )

    def test_placebo_and_famotidine_partners(self) -> None:
        # NCT04550195.
        drug = _int("BMS-986337", "Specified Dose on Specified Days")
        placebo = _int("BMS-986337 Placebo", "Specified Dose on Specified Days", kind="OTHER")
        famotidine = _int("Famotidine", "Specified Dose on Specified Days", kind="BIOLOGICAL")
        protocol = _protocol([drug, placebo, famotidine])
        assert stage_attribution(protocol, "BMS-986337") == ATTRIBUTED
        assert stage_attribution(protocol, "BMS-986337 Placebo") == "WITHHELD_CONTROL_ROLE"

    def test_co_administered_products_under_generic_labels(self) -> None:
        # NCT05674175.
        cd22 = _int("Autologous, humanized anti-CD22 CAR T cell therapy (CART22-65s)")
        cd19 = _int("Autologous, humanized anti-CD19 CAR T cell therapy (huCART19)")
        arms = [_arm("Dose Finding Arm", [cd22, cd19]), _arm("Expansion Arm", [cd22, cd19])]
        protocol = _protocol([cd22, cd19], arms=arms)
        assert stage_attribution(protocol, cd22["name"]) == ATTRIBUTED
        assert stage_attribution(protocol, cd19["name"]) == ATTRIBUTED


class TestTitle:
    def test_title_annotates_a_grant(self) -> None:
        protocol = _protocol([_int("KITE-363")], title="KITE-363 in Autoimmune Disease")
        assert stage_method(protocol, "KITE-363", ATTRIBUTED) == (
            "ctgov_stage:STAGE_FROM_STRUCTURED_INTERVENTION+TITLE"
        )

    def test_untitled_grant_has_no_annotation(self) -> None:
        protocol = _protocol([_int("KITE-363")])
        assert stage_method(protocol, "KITE-363", ATTRIBUTED) == (
            "ctgov_stage:STAGE_FROM_STRUCTURED_INTERVENTION"
        )

    def test_title_never_rescues_an_excluded_intervention(self) -> None:
        cy = _int("Cyclophosphamide", "Lymphodepletion chemotherapy")
        protocol = _protocol([_int("CAR-T X"), cy], title="Cyclophosphamide and CAR-T X")
        assert stage_attribution(protocol, "Cyclophosphamide") == "WITHHELD_SUPPORT_ROLE"
