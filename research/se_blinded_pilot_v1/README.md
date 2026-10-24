# Blinded S&E pilot benchmark (v1)

**Status: UNVALIDATED. No independent reference dataset has been supplied.**
The only references scored so far are synthetic test fixtures in
`tests/se/test_blinded_pilot.py`. They test the scorer. They say nothing about how well the engine performs.

Code: `src/bve/se/evaluation/blinded_pilot.py`. Command: `bve-se-pilot`.

## Who does what

| Step | Who | Input | Output |
|---|---|---|---|
| 1. Write the request | Analyst | `templates/spec.template.json` | `spec.json`: therapeutic area, targets, modalities, stages, as-of date and a plain-language query. It must not name any expected asset. |
| 2. Declare pass/fail rules | Analyst (before seeing any engine output) | `templates/criteria.template.json` | `criteria.json`: thresholds for precision, recall, trial coverage, identity errors and misleading claims |
| 3. Build the hidden answer key | Analyst (separately) | `templates/reference.template.json` | `reference.json`, **stored outside this repo**: every in-scope asset with all known names and codes, targets, modality, NCT IDs and checkable facts (owner, stage, rights), plus negative controls (plausible assets that do *not* qualify) and provenance |
| 4. Run discovery | Engine operator | `spec.json` translated into an engine problem YAML + source policy | `bve-se-run --problem … --live` → `result.json` |
| 5. Export | Engine operator | `result.json` | `bve-se-pilot export --result result.json --spec-id … --engine-commit … --out candidates.json` |
| 6. Seal | Engine operator | spec, criteria, candidates | `bve-se-pilot seal … --out receipt.json`. Hashes all three. This step accepts no reference input. |
| 7. Score | Evaluator | receipt + the three sealed files + `reference.json` | `bve-se-pilot score … --out report.json` |
| 8. Adjudicate | Analyst | the `not_auto_scored` items in `report.json` | human verdicts on those items |

Step 4 needs a person: the analyst's spec has to be translated into an engine problem YAML by hand. No automatic translator exists yet. Whoever does that translation must not have seen `reference.json`.

## What keeps the labels blind

- `export` and `seal` take no reference argument (tested).
- No other module in `src/bve` imports the scorer or the reference types (tested).
- `score` refuses a reference file stored inside the engine repo. The only override is `--allow-reference-in-repo`, for synthetic tests.
- `score` refuses if the spec, criteria or candidates changed after sealing (tested). Criteria therefore can't be tuned after the answers are visible.
- This blindness is **procedural**. The code cannot stop someone who has read the reference from editing engine code or problem YAMLs before step 4. The analyst should record when the reference was handed over, and the engine commit in `candidates.json` must predate that handover.

## Scored automatically

- **Asset precision.** Two versions. *Strict* counts every unmatched candidate as wrong. *Adjudicated* leaves unmatched candidates out and lists them separately. Hits on negative controls are listed separately.
- **Asset recall** over in-scope reference assets.
- **Name matching.** A candidate matches a reference asset when any of its names or codes normalises to one of that asset's names or codes (exact match after lowercasing and stripping punctuation; no substring matching).
- **Identity errors.** *Merge*: one candidate matches two reference assets. *Split*: one reference asset is matched by two or more candidates.
- **Target accuracy.** Exact match on the set of targets; candidates with no target are counted as UNKNOWN, separately. **Modality accuracy** is scored the same way.
- **Trial-history coverage.** Reference NCT IDs found, pooled per reference asset. Trials the engine attached that the reference doesn't list are counted as "unreferenced".
- **Evidence.** Share of claims with at least one citation. Claims that match a reference fact count as *supported*; claims that contradict one count as **misleading** (scientific or commercial); claims on fields the reference doesn't cover count as *unverifiable*.
- A pass/fail verdict against the predeclared thresholds. It is withheld (`null`) when the reference status is UNVALIDATED.

## Not scored automatically (needs a human)

- Whether each cited source actually supports its claim. The scorer only checks that a citation is present.
- Unmatched candidates: is each one a miss in the reference or an engine false positive?
- Unreferenced trials: is each one a correct addition or a wrong attribution?
- Claims on fields the reference doesn't cover.

## Report status values

- `SYNTHETIC_SELF_TEST`: the reference is a test fixture.
- `UNVALIDATED`: the reference doesn't declare an independent human preparer.
- `SCORED_AGAINST_SUPPLIED_REFERENCE`: the reference declares an independent preparer. The tool doesn't verify that claim, so the result is only as good as the reference.
