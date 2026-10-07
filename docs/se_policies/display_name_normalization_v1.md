# DISPLAY_NAME_NORMALIZATION v1 — strip a pasted registry field header from the shown name (preregistration)

**Status:** PREREGISTERED 2026-10-07. No implementation exists.
**Operator decision:** 2026-10-06, option (a): display-only.
**Parent:** `mint5_residual_candidate_diagnosis_v1.md` §2, row #9.

## 1. Problem

Some sponsors paste a CT.gov field header into the intervention name, for example
"Assigned Interventions CD19/BCMA CAR T-cells". Stripping it from the **identity** key would
make the asset equal to the generic *CD19/BCMA CAR T-cells* asset, which pools another
sponsor's product. That would be a false merge. Stripping it only from the **shown** name has
no identity effect.

## 2. Rule (frozen)

**Grammar.** If a canonical name matches the closed header grammar below, followed by at
least one more non-space character, the **display name** is the name with the header removed:

```
^(?:Assigned Interventions?|Interventions?|Intervention Names?|Intervention/Treatment|Arm Intervention/Treatment)\s*[:\-–]?\s+
```

Matching is case-insensitive.

**Where it applies.**
- It applies to the shortlist entry `name` and to memo asset names.
- The shortlist entry gains `raw_name`, which always holds the unmodified canonical name.

**What it never touches:**
- `canonical_name`, aliases or identity keys;
- registry ingestion, merges or trial attribution;
- the ranking key (its name tie-break keeps using the raw canonical name);
- any fact, gate or qualification.

## 3. Frozen population

The grammar matches exactly 1 asset in each benchmark (`*_ncitid_v1`): "Assigned Interventions
CD19/BCMA CAR T-cells" → "CD19/BCMA CAR T-cells".

## 4. Acceptance

The baseline is the adopted protocol-id runs, re-rendered.

- **D1.** Only the frozen asset's shown name changes, and its `raw_name` is the original.
- **D2.** Candidates, aliases, identity keys, merges, trial reattributions, facts, gates and the
  ranked order (by asset id) are identical with and without the rule. This is render-only.
- **D3.** No asset is registered under the cleaned string.
- **D4.** `tests/se` and ruff pass.

The rule is render-time, so D1–D3 are scored by rendering the same `result.json` before and
after the code change. No replay is needed.
