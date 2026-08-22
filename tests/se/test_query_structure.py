"""M9E1b: the CT.gov query must preserve the planner's boolean structure.

The first exhaustive PDCD1 sweep retrieved 15,101 trials of which 11,144 came from a
batch reading "therapeutic vaccine vaccine". Splitting a query by word count and unioning
the responses turns (targets) AND (modalities) into a union of arbitrary fragments.
"""
from __future__ import annotations


from bve.se.universe import ClinicalTrialsGovProvider
from bve.se.universe.provider import TrialQuery


class _RecordingSearch:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return []


_PDCD1_PROBLEM_YAML = """\
schema_version: se_buyer_problem_v2
problem_id: baseline_pdcd1_landscape
version: "1.0.0"
buyer:
  buyer_id: baseline_buyer
  name: PDCD1 Baseline Buyer
  as_of_date: 2026-08-20
strategic_gap:
  therapeutic_areas: [oncology]
  indications: []
  target_expression:
    operator: ANY
    targets:
      # Canonical PDCD1, not the bare nickname "PD-1": that string is genuinely
      # ambiguous in the general ontology (it is also a legacy alias of RPL17),
      # and the resolver is right to abstain on it. Product behaviour on the
      # nickname is measured separately as a smoke test, not scored here.
      - canonical_id: PDCD1
        label: PDCD1
        aliases: [PD-1, PD1, CD279, Programmed cell death protein 1]
  # The M8 PDCD1 benchmark places no modality restriction on its 224 canonical
  # candidates, so the baseline declares the full supported modality ontology
  # (modality_v2) rather than a subset. The schema requires at least one entry.
  modalities:
    - ANTIBODY_DRUG_CONJUGATE
    - BISPECIFIC_ANTIBODY
    - CAR_T
    - CELL_THERAPY
    - FUSION_PROTEIN
    - GENE_EDITING
    - GENE_THERAPY
    - MOLECULAR_GLUE_OR_DEGRADER
    - MONOCLONAL_ANTIBODY
    - MULTISPECIFIC_ANTIBODY
    - ONCOLYTIC_VIRUS
    - PEPTIDE
    - RADIOLIGAND
    - RNA_THERAPEUTIC
    - SMALL_MOLECULE
    - T_CELL_ENGAGER
    - VACCINE
  required_biology: []
  capability_constraints:
    manufacturing: []
    delivery: []
    clinical_operations: []
    commercial: []
    integration: []
  evidence_floor:
    minimum_stage: PHASE_1
    human_poc_required: true
    evaluable_patients_minimum: null
    follow_up_minimum_days: null
    required_evidence_types: [HUMAN_CLINICAL_RESULT]
  clinical_effect_bar: {}
  acceptable_deal_routes: [LICENSE, COLLABORATION, OPTION, ACQUISITION]
  geographic_rights_requirements: []
  missing_evidence_policy: REVIEW
output:
  landscape_mode: SEPARATE
  group_by: COHORT
ranking_cohort_required: true
"""


class TestQueryStructureSurvivesTransport:
    def test_groups_become_one_and_of_ors_in_a_single_request(self):
        search = _RecordingSearch()
        provider = ClinicalTrialsGovProvider(search_fn=search)
        provider.fetch(
            TrialQuery(term_groups=[["PDCD1", "CD279"], ["vaccine", "cancer vaccine"]])
        )
        # One request: fragmenting is what destroyed the AND.
        assert len(search.calls) == 1
        expr = search.calls[0]["intervention"]
        assert expr == '("PDCD1" OR "CD279") AND ("vaccine" OR "cancer vaccine")'

    def test_a_flat_term_list_is_one_or_group_not_an_and(self):
        # An alias list means "any spelling of this thing". Joining aliases with spaces
        # asks CT.gov for trials containing all of them at once, which returned zero.
        search = _RecordingSearch()
        ClinicalTrialsGovProvider(search_fn=search).fetch(
            TrialQuery(terms=["PDCD1", "PD-1"])
        )
        assert search.calls[0]["intervention"] == '("PDCD1" OR "PD-1")'

    def test_quotes_in_a_term_cannot_break_out_of_the_expression(self):
        search = _RecordingSearch()
        ClinicalTrialsGovProvider(search_fn=search).fetch(
            TrialQuery(terms=['PD"1 OR cancer'])
        )
        expr = search.calls[0]["intervention"]
        # The OR must survive only as literal text inside the quotes, never as an
        # operator: exactly one quoted literal, and no unquoted region to hide one in.
        assert expr == '("PD 1 OR cancer")'
        assert expr.count('"') == 2

    def test_an_empty_group_is_dropped_rather_than_emitting_empty_parens(self):
        search = _RecordingSearch()
        ClinicalTrialsGovProvider(search_fn=search).fetch(
            TrialQuery(term_groups=[["PDCD1"], []])
        )
        assert search.calls[0]["intervention"] == '("PDCD1")'

    def test_no_terms_at_all_still_issues_exactly_one_request(self):
        search = _RecordingSearch()
        ClinicalTrialsGovProvider(search_fn=search).fetch(
            TrialQuery(conditions=["melanoma"])
        )
        assert len(search.calls) == 1
        assert "intervention" not in search.calls[0]


class TestPlanCarriesNoRedundantQueries:
    """One query per target facet, not one per spelling of it.

    The PDCD1 plan compiled 255 queries that resolved to 17 distinct searches repeated
    15 times: the compiler emitted a query per alias, and the retrieval layer expanded
    each one back to the same full alias set. 240/255 contributed no new trials.
    """

    def _problem(self):
        import yaml

        from bve.se.schemas.contracts import BuyerProblemV2

        return BuyerProblemV2.model_validate(yaml.safe_load(_PDCD1_PROBLEM_YAML))

    def test_aliases_do_not_multiply_the_plan(self):
        from bve.se.discovery.query import compile_problem_queries

        queries = compile_problem_queries(self._problem())
        modalities = {m for q in queries for m in q.modality_ids}
        assert len(queries) == len(modalities), (
            f"{len(queries)} queries for {len(modalities)} modalities -- "
            "aliases are multiplying the plan again"
        )

    def test_every_alias_is_still_searched(self):
        # Compacting the plan must not narrow it: the aliases move into the OR group
        # rather than disappearing.
        from bve.se.discovery.adapters import QueryVocabulary
        from bve.se.discovery.query import compile_problem_queries

        queries = compile_problem_queries(self._problem())
        searched = {
            term
            for q in queries
            for facet in QueryVocabulary.for_query(q).query_facets()
            for term in facet
        }
        for alias in ("PDCD1", "CD279", "programmed cell death 1"):
            assert alias in searched

    def test_compaction_searches_the_same_expressions_as_the_alias_plan(self):
        """The frozen half of the equivalence check.

        Live, the two plans returned identical 2,908-NCT sets. That holds because they
        issue the *same* CT.gov expressions -- the compact plan just stops issuing each
        one 27 times. Asserting on the expressions keeps the guarantee testable without
        a network round trip.
        """
        from bve.se.discovery.adapters import QueryVocabulary
        from bve.se.discovery.query import compile_problem_queries
        from bve.se.ontology.targets import target_aliases
        from bve.se.universe.ctgov import build_intervention_expression

        problem = self._problem()
        compact = compile_problem_queries(problem)
        aliases = target_aliases(
            problem.strategic_gap.target_expression.targets[0].canonical_id
        )
        expanded = [q for q in compact for _ in aliases]

        def expressions(queries):
            return {
                build_intervention_expression(
                    [list(f) for f in QueryVocabulary.for_query(q).query_facets()]
                )
                for q in queries
            }

        assert expressions(compact) == expressions(expanded)
        assert len(compact) == len(expressions(compact)), "plan repeats a search"
