# Amendment 6.1: two readings of Amendment 6, fixed before measurement

Status: **FROZEN**, 2026-09-27, written during implementation, before any replay. It changes no
threshold, criterion or reason code of Amendment 6. It records how two sentences are read, where
a literal reading contradicts Amendment 6's own worked cases or Amendment 4.

1. **"Named inside the phrase"** includes any drug name the identity extractor observes in the
   phrase (`extract_observed_asset_names`, lexicon only, no shape scan), not only registered
   interventions of the trial.
   - This is required by Amendment 6's CD19-TriCAR-T/SILK worked case. Fludarabine and
     cyclophosphamide are named in the CAR-T's own description but are not registered
     interventions. The worked case says they, not the CAR-T, are the referents.
   - A phrase naming such a drug therefore blocks self-reference. Forward referents are still
     only registered interventions, since only they can receive a role.
2. **Before-product self-reference** requires the clause to contain text before the "prior to" or
   "before" marker. That text is the description's subject, so the marker does not open the
   clause.
   - This restores Amendment 4's condition that the agent occurs *before* the marker.
   - "Cyclophosphamide will be given … prior to CAR-T infusion" is support.
   - "Prior to cellular infusion, patients receive lymphodepletion with fludarabine" is not
     support for the CAR-T whose description it is. It still makes fludarabine a forward
     referent where fludarabine is a registered intervention.
   - A clause that also contains a support term is decided by the support-phrase rules alone.
