"""A drug listed inside a regimen does not own the regimen's result.

Policy: ``docs/se_policies/human_poc_regimen_list_attribution.md``. The three negative
sentences are the ones that credited conditioning and chemotherapy agents on TAC01.
"""

from __future__ import annotations

from bve.se.evidence.human_poc import efficacy_statements

R_CHOP = (
    "Approximately 40% of patients with high-risk diffuse large B-cell lymphoma (DLBCL) are not "
    "cured with first-line R-CHOP (rituximab, cyclophosphamide, doxorubicin, vincristine, and "
    "prednisone or prednisolone)."
)
FCR = (
    "Additionally, patients receiving VO showed the highest survival rates at 12 months (95% "
    "confidence interval [CI]) at 97.6% (94.5, 100.0), followed by fludarabine, "
    "cyclophosphamide, and rituximab (FCR) at 96.6% (94.0, 99.3)."
)
DVRD = (
    "N = 395) demonstrated improved overall minimal residual disease (MRD) negativity rates "
    "among patients achieving complete response and progression-free survival (PFS) with "
    "daratumumab plus bortezomib, lenalidomide, and dexamethasone (DVRd) versus VRd."
)


class TestARegimenListItemIsNotCredited:
    def test_a_parenthetical_regimen_expansion(self) -> None:
        for name in ("cyclophosphamide", "vincristine", "doxorubicin"):
            assert efficacy_statements(R_CHOP, asset_names=[name]) == []

    def test_a_final_item_of_alternatives(self) -> None:
        # Amendment 1: "and prednisone or prednisolone" is one list item of two alternatives.
        for name in ("prednisone", "prednisolone"):
            assert efficacy_statements(R_CHOP, asset_names=[name]) == []

    def test_a_serial_list_with_a_final_and(self) -> None:
        assert efficacy_statements(FCR, asset_names=["cyclophosphamide"]) == []
        assert efficacy_statements(FCR, asset_names=["fludarabine"]) == []

    def test_a_list_item_after_a_plus_joined_lead(self) -> None:
        assert efficacy_statements(DVRD, asset_names=["lenalidomide"]) == []

    def test_a_plain_three_item_list(self) -> None:
        text = (
            "Patients treated with ABC-123, XYZ-9, and dexamethasone achieved an overall "
            "response rate of 70%."
        )
        control = "Patients treated with XYZ-9 achieved an overall response rate of 70%."
        assert len(efficacy_statements(control, asset_names=["XYZ-9"])) == 1
        assert efficacy_statements(text, asset_names=["XYZ-9"]) == []


class TestAnIndividualResultIsKept:
    def test_a_single_agent_comma_clause(self) -> None:
        text = "In patients treated with ABC-123, the overall response rate was 83%."
        assert len(efficacy_statements(text, asset_names=["ABC-123"])) == 1

    def test_an_apposition_is_not_a_list(self) -> None:
        text = "The product, ABC-123, achieved complete remission in 10 of 12 patients."
        assert len(efficacy_statements(text, asset_names=["ABC-123"])) == 1

    def test_a_sentence_initial_name_with_an_appositive(self) -> None:
        text = "ABC-123, a CD19 CAR-T, achieved an overall response rate of 83% in patients."
        assert len(efficacy_statements(text, asset_names=["ABC-123"])) == 1

    def test_a_combination_product_name_keeps_its_result(self) -> None:
        text = "CD19/BCMA dual CAR-T achieved complete remission in 10 of 12 patients."
        assert len(efficacy_statements(text, asset_names=["CD19/BCMA dual CAR-T"])) == 1
