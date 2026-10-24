# Analyst handoff: building the answer key for the first blinded BVE experiment

You are building a hidden answer key. The BVE engine will run without seeing it, and its output will then be scored against it.
The result is only as trustworthy as your key and your custody of it. Nothing in this repository has validated the engine.

## 1. Choose the question (before anything else)

- Choose a therapeutic area, target or modality where you could build a near-complete list of drugs yourself. A good size is 10–40 in-scope assets.
- **Do not reuse** any area, asset or document that BVE's developers have already examined. That excludes the autoimmune T-cell-engager review (cizutamig / CND106 / EMB-06, HXN-1031), and every target in the repo's past benchmark reports (PDCD1, SLC6A2, HRH1, HTR2A, CHRM1, and the TAC01 and AACR runs). Ask the operator for the current list. Don't tell them which area you are considering.
- Fix an **as-of date**. Assets and facts are judged as of that date.

## 2. Write and preregister the request (shared with the operator)

1. Copy `templates/spec.template.json` to `spec.json`. Fill in the area, targets, modalities, stages, as-of date and a plain-language query. **Do not name any asset.**
2. Copy `templates/criteria.template.json` to `criteria.json`. Set the pass/fail thresholds now. Once the engine has run, they can't be changed.
3. Run `bve-se-pilot prereg --spec spec.json --criteria criteria.json --out prereg.json`.
4. Commit all three files under `research/se_blinded_pilot_v1/<spec_id>/` and push them.
5. Email the commit SHA and the two hashes in `prereg.json` to yourself and to one third party. That email is your independent timestamp.
6. Only then tell the operator to run the engine.

## 3. Build the answer key (private, never in the repo)

Start from `templates/reference.template.json` and save it as `reference.json` on a machine or drive the operator can't access.

For each **in-scope asset** (every drug that meets the spec as of the date), record:
- `names`: every name you can find, including the INN, every development code (old and new), trade names and licensee codes. Missing aliases cause false "misses".
- `target_ids`: HGNC symbols.
- `modality`.
- `trial_ids`: **every** NCT ID, including terminated and withdrawn trials and trials run under old codes. This is the trial-history denominator.
- `facts`: checkable fields such as `owner`, `stage`, `rights_territory` and `licensor`, each with one value as of the date.

Add **negative controls** (`in_scope: false`): 3–10 plausible drugs that do *not* qualify, for example a wrong target, a discontinued program or an out-of-scope stage. These detect over-broad output.

Fill in `provenance` honestly:
- `prepared_by`;
- `organization`;
- `prepared_on`;
- `method`: the databases searched, search terms and dates;
- `independent_of_engine: true` only if you never used BVE output to build the list;
- `synthetic: false`.

Use your own sources: ClinicalTrials.gov, WHO ICTRP / ChiCTR / EU CTR, company pipelines, press releases, SEC filings, Citeline/Cortellis if licensed. **Do not** use BVE reports, BVE run outputs or anything in this repository.

Keep a separate working note of why each asset is in or out. You will need it in step 5.

## 4. Custody rules

- Never commit `reference.json`, or put it anywhere inside the repository folder. The scorer refuses it there.
- Don't discuss assets, aliases or trial counts with the operator until scoring is finished.
- Before you hand over the key, get `receipt.json` from the operator and check it:
  - `prereg_commit` matches your emailed SHA;
  - `prereg_on_remote` is `true`;
  - `run_started_at` is after your preregistration and before the handover.
- Write down the date and time you hand over or use the key. Any engine change after that date doesn't count for this experiment.

## 5. Score and adjudicate

Run `bve-se-pilot score` yourself, or watch it being run. Then review `report.json`:
- **`unadjudicated_candidates`**: for each one, decide whether it is an engine false positive or a real asset you missed. Record your decision. Don't edit `reference.json` after scoring; record corrections separately.
- **`unreferenced_trials`**: is each one a correct addition or a wrong attribution?
- **Citations**: spot-check that the cited sources actually support the claims (sample at least 20 if there are many).
- **`misleading_claims`**: confirm each one.

## What the scorer can't tell you

- Whether your key is complete. Recall is measured against your list.
- Whether a citation supports its claim.
- Whether the engine was tuned after someone saw the key. Only your custody record covers that.
