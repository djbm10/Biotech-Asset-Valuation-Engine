# Harvey Falsification Tool

Plain-language record of the run that made Harvey's killer-question falsification idea operational.

## 2026-07-02 - End-to-End Status

### What Changed

The tool can now name a program's killer question, update confidence in that question from evidence, show the full conviction trail in outputs, and lower confidence when evidence contradicts the biological thesis.

This is not a POS or valuation change yet. It is the diligence/conviction layer Harvey wanted: explicit, falsifiable, auditable.

### Built Sequence

1. **Killer-question spine.**
   The science layer now produces a ranked `KillerQuestionSet`: top make-or-break questions, VOI ranking, confidence, abstention, company-focus mismatch, and `NOVEL_OR_UNMODELED_RISK` escape hatch.

2. **Conviction kernel (`6582ec4`).**
   Added log-odds posterior updating plus `EvidenceUpdate` and `ConvictionRecord`. Evidence can confirm or refute. Silence stays inert.

3. **Trail surfacing (`1b1cf38`).**
   Conviction trails appear in JSON and BD memo: prior, evidence updates, posterior, rationale.

4. **Dose-response producer (`ed1a225`).**
   Replaced the old hardcoded dose-response `+0.10` with a real `EvidenceUpdate` flowing through the kernel.

5. **Expected-signature scaffold (`550a53c`, docs `d96124b`).**
   Added curated expected-signature library and loader. Draft signatures surfaced as candidates but could not score.

6. **Expected-signature producer (`e2361af`, docs `321aceb`).**
   Approved signatures can now move confidence:
   - observed matches expected biology -> confidence up
   - observed contradicts expected biology -> confidence down
   - required marker missing -> untested, no confidence move
   - draft signatures -> cannot fire

7. **S&E / BD shortlist cluster.**
   Buyer-problem shortlist mode now ranks assets for a buyer problem, shows decisive killer question per asset, and preserves excluded gate reasons. This makes the killer question actionable in BD diligence.

### Why It Matters

- The tool is no longer just averaging many weak factors.
- It names the few questions that actually decide the asset.
- It can be talked out of a thesis by evidence.
- A human can audit every confidence movement.
- Biology assumptions that are easy to hallucinate, like expected biomarker signatures, are gated by human approval before they can move confidence.

### What It Still Does Not Do

Conviction still does **not** change POS, valuation, BD score, or route.

That next step needs the staged plan in `docs/conviction_generalization_plan.md`:

- per-archetype producers
- canonical per-question trails
- calibration by archetype x source x context
- shadow mode before any score effect
- bounded/asymmetric POS influence
- overlap and correlation guards
- valuation only through calibrated POS
- BD route influence only after hard gates remain protected

### Proof It Works

Automated tests covered:

- kernel updates in log-odds
- refuting evidence lowers confidence
- silence and missing markers do not punish
- near-miss with trend raises while near-miss without trend lowers
- dose-response trail reaches memo/JSON
- expected-signature approved-only gate
- match raises confidence
- contradiction lowers confidence
- missing marker sets untested
- draft signatures never fire
- POS/science modifier/scoring boundaries remain untouched

### Current Next Steps

- Add more approved expected signatures through domain review.
- Feed `observed_biomarker_changes` from asset YAML/config into normal runs.
- Backtest conviction records before allowing any POS/valuation/BD influence.
- Implement conviction generalization only in staged shadow mode.
