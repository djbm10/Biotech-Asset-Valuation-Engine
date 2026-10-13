# Gate-input validation note

An additional all-stored-facts probe was invalid: it supplied all retained modality facts directly to evaluate_requirement. For asset:df0b23613e170e339595 this produced FAIL against saved UNKNOWN. The unchanged pipeline (pipeline.py around 532–540 and 1029–1030) gates only admitted/entailed facts, while result.json retains other facts as evidence. This does not demonstrate a representation delta; none of the legacy files changed. The invalid probe is preserved as invalid_all_facts_probe.py and is not an acceptance result.

The valid additional check re-evaluates each saved modality gate with its recorded observed_fact_ids as the frozen gate input. It checks statuses and fact IDs against those saved outcomes. This is gate-input reproduction, not a full pipeline replay or a claim to recompute entailment. No implementation/scope rule or frozen expectation was changed in response. Legacy-file hashes and full regression tests independently test neutrality.
