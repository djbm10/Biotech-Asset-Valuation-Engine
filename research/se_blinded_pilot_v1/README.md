# Blinded S&E pilot benchmark (v1)

**Status: UNVALIDATED. No independent reference dataset has been supplied.**
The only references scored so far are synthetic test fixtures in
`tests/se/test_blinded_pilot.py`. They test the scorer. They say nothing about how well the engine performs.
A synthetic fixture never gets a pass/fail verdict.

Code: `src/bve/se/evaluation/blinded_pilot.py`. Command: `bve-se-pilot`.
External analyst instructions: [`ANALYST_HANDOFF.md`](ANALYST_HANDOFF.md).

## Who does what

| Step | Who | Output |
|---|---|---|
| 1. Write the request | Analyst | `spec.json` (from `templates/`). It must not name any expected asset. |
| 2. Declare pass/fail rules | Analyst | `criteria.json` (from `templates/`) |
| 3. Preregister | Analyst | `bve-se-pilot prereg --spec spec.json --criteria criteria.json --out prereg.json`. Commit and **push** all three files to the repo (`research/se_blinded_pilot_v1/<spec_id>/`), and email the commit SHA plus both hashes to a third party. |
| 4. Build the answer key | Analyst, privately | `reference.json`, **kept outside the repo**. Can be done before or after step 5, but must never be shown to the engine operator before step 8. |
| 5. Run discovery | Engine operator | Translates `spec.json` into an engine problem YAML by hand, then `bve-se-run --problem … --live` → `result.json` |
| 5a. Check the translation | Engine operator | The problem must carry every spec constraint the engine can express. Areas and indications go in as lists, never as a bare string (pilot `gucy2c_oncology_v1` compiled `"ONCOLOGY"` into eight one-letter areas). Mechanism exclusions go in as `required_biology` requirements, for example `target_action_type NOT_IN [AGONIST]`. Record anything the engine cannot express in the run notes, so nobody assumes it was applied. |
| 6. Export | Engine operator | `bve-se-pilot export --result result.json --spec-id … --engine-commit … --out candidates.json` |
| 7. Seal | Engine operator | `bve-se-pilot seal --spec … --criteria … --candidates … --prereg … --out receipt.json` |
| 8. Score | Analyst or evaluator | `bve-se-pilot score --receipt … --spec … --criteria … --candidates … --reference … --out report.json` |
| 9. Adjudicate | Analyst | Human verdicts on the `not_auto_scored` items |

## Preregistration: what is checked

Seal refuses in each of these cases:
- the spec or criteria file differs from the hashes in `prereg.json`;
- `prereg.json` isn't committed in git with exactly that content;
- the earliest commit holding it isn't older than the engine run's `started_at` (taken from the engine's own run manifest).

The receipt records the prereg commit and whether that commit was on a remote branch.

If the prereg commit was never pushed, score downgrades the run to `UNVALIDATED`. A local commit time is self-reported. The pushed commit and the analyst's emailed copy of the hashes are what an outsider can check.

The prereg file holds only hashes of the spec and criteria. It contains no reference data, so it is safe to publish.

## What keeps the labels blind

- `prereg`, `export` and `seal` take no reference argument (tested).
- No other module in `src/bve` imports the scorer or the reference types (tested).
- `score` refuses a reference file stored inside the engine repo. The only override is `--allow-reference-in-repo`, for synthetic tests.
- `score` refuses if the spec, criteria or candidates changed after sealing (tested).
- The rest is **procedural**. The code can't stop someone who has read the reference from changing engine code. See the handoff's custody rules.

## Scored automatically

- **Recall**: in-scope reference assets recovered ÷ all in-scope reference assets. An asset counts as recovered only through a candidate that matches that asset and nothing else.
- **Precision**: recovered assets ÷ candidates. A drug split into several candidates earns one credit, and a merged candidate earns none.
  - *Strict*: every candidate is in the denominator.
  - *Adjudicated*: candidates matching nothing in the reference are left out and listed for a human.
  - Hits on negative controls are listed separately.
- **Identity errors**:
  - *merge*: one candidate matches two reference assets;
  - *split*: one reference asset matches two or more candidates.
- **Name matching**: exact match after lowercasing and stripping punctuation, on any name or code. No substring matching.
- **Target and modality accuracy**, scored once per recovered reference asset:
  - correct only if every candidate for that asset that states a value states the right one;
  - UNKNOWN is reported both excluded and counted as wrong (`*_incl_unknown`);
  - when the reference has no value, the field is *unadjudicable*, not wrong.
- **Trial-history coverage**:
  - `trial_coverage_overall`: reference trials found ÷ reference trials of **all** in-scope assets, including missed ones. Thresholds use this.
  - `trial_coverage_recovered`: the same ratio, recovered assets only.
  - Trials the engine attached that the reference doesn't list are counted as *unreferenced*.
- **Evidence**: share of claims with a citation. Claims are *supported*, **misleading** (contradicts a reference fact) or *unverifiable* (no reference value).
- **Verdict**: given only when the status is `SCORED_AGAINST_SUPPLIED_REFERENCE`, and otherwise `null`. A metric that can't be computed fails any threshold above zero.

## Not scored automatically (needs a human)

- Whether each cited source actually supports its claim.
- Unmatched candidates: is each one a miss in the reference or an engine false positive?
- Unreferenced trials: is each one a correct addition or a wrong attribution?
- Claims on fields the reference doesn't cover.

## Report status values

- `SYNTHETIC_SELF_TEST`: test fixture. Never gets a verdict.
- `UNVALIDATED`: the reference doesn't declare an independent preparer, or the preregistration was never pushed. Never gets a verdict.
- `SCORED_AGAINST_SUPPLIED_REFERENCE`: the reference declares an independent preparer and the preregistration was pushed. The tool can't verify the preparer's independence, so the result is only as good as the reference.
