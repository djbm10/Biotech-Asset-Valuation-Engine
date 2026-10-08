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

## 5. Result — 2026-10-08, code `840340a`

Scored by rendering the adopted `*_protoid_v1` results with the rule and with an identity
display function. Output: `research/se_protocol_id/display_stage_d_v1.txt`.

| Criterion | Result |
|---|---|
| **D1** | **PASS.** Only the frozen asset's shown name changes, in the mint5 shortlist (#10) and in both memos. All 22 changed memo lines (11 per benchmark) are that asset. `raw_name` is preserved. In TAC01 the asset is not on the shortlist, so only memo lines change. |
| **D2** | **PASS.** The order by asset id is identical. The input result is not modified. |
| **D3** | **PASS.** The cleaned string is registered nowhere. The scorer's one hit is the pre-existing generic asset `asset:026193b4…`, which carries that name in the baseline too. Disclosure: in the memo, that generic asset and the cleaned row now show the same text. They are told apart by the asset-id column. The generic asset is not on either shortlist. |
| **D4** | **PASS.** `tests/se` 1655 passed, 3 xfailed; ruff clean. |

**Status: ADOPTED.**
