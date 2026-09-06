# M10C — Confirmed PDCD1 error audit & precision controls

Descriptive. No pipeline, identity or extraction code was changed.

## 1. Full 35/5 accounting over the 40 V2-confirmed PDCD1 assets

Each asset is attributed to the FIRST stage boundary it failed, so a downstream symptom is
never reported as the cause. Per-asset rows in `confirmed_asset_audit.jsonl`.

| first_failure_boundary | n |
|---|---|
| NONE (identified) | 35 |
| EXTRACTION | 3 |
| IDENTITY_RESOLUTION | 2 |

### The 5 misses

| gold entry | src | boundary | evidence |
|---|---|---|---|
| Budigalimab | V1 | EXTRACTION | NCT04223804 `NO_ASSET_NAME_EXTRACTED` + `MODALITY_NOT_CONFIRMED`; name present in `other_names` |
| Budigalimab (ABBV-181) | V1 | EXTRACTION | same single trial; duplicate M8 presentation |
| Subcutaneous pembrolizumab/berahyaluronidase alfa (MK-3475A) | V2 | EXTRACTION | NCT05017012 `NO_ASSET_NAME_EXTRACTED` + `MODALITY_NOT_CONFIRMED`; name present in `other_names` |
| Dostarlimab-gxly (GSK4057190 / TSR-042, JEMPERLI) | V1 | IDENTITY_RESOLUTION | trial survived; run emitted `dostarlimab` and `tsr042dostarlimab`, neither binding the hyphenated alias set |
| SMT112, AK112 | V2 | IDENTITY_RESOLUTION | NCT07743632 survived; run emitted `ak112`, `ivonescimab`, `ivonescimab smt112or ak112injection` |

The 5 misses collapse to **two defect classes and two trials**:

- **Extraction boundary (3 entries, 2 trials).** Both trials carry the asset name only in the
  CT.gov `other_names` field and both also failed modality confirmation. The names are present
  in the registry record; the extractor did not lift them.
- **Alias binding (2 entries).** In both cases the molecule WAS discovered and correctly named
  under another surface form. The benchmark string is a hyphenated INN suffix
  (`Dostarlimab-gxly`) or a multi-code list (`SMT112, AK112`) that no single emitted mention
  equals. Neither is a discovery failure.

No miss was an acquisition or policy-filter failure. Retrieval reached all 40.

## 2. Precision on confirmed negatives

Confirmed NON_PDCD1 assets: **133** (V1 106 + V2 27).
Surfaced by the PDCD1-scoped run: **42 (31.6%)**.

Most of the 42 are chemotherapy backbones and comparators that legitimately appear inside
PD-1 combination trials — carboplatin, cisplatin, paclitaxel, gemcitabine, pemetrexed,
capecitabine, bevacizumab, lenvatinib. Surfacing them is not by itself wrong; the discovery
stage is asset identification within retrieved trials.

The sharper subset is 6 pathway-adjacent traps: **Durvalumab, Atezolizumab, Avelumab,
Adebrelimab, Pumitamig (BNT327/BMS-986545) x2** — all PD-L1, all `NON_PDCD1` under the frozen
rule.

### The actual precision defect

Probing the run's own per-candidate target assertions (`target_attribution_probe.json`):

- candidates: **1136**
- candidates carrying `target_ids`: **1136**
- distinct target sets observed: **exactly one — `['PDCD1']`**

**Every discovered candidate is stamped with the query target unconditionally.** The run
asserts `PDCD1` for sitagliptin, carboplatin, olaparib, cyclophosphamide and durvalumab
alike. There is no per-asset target attribution step, so the system cannot currently
distinguish a PD-1 drug from a chemotherapy backbone in the same trial.

19 confirmed NON_PDCD1 entries are asserted `PDCD1` under an exact-name match; the true figure
is the full 42 surfaced negatives, since the stamp is unconditional.

This is a genuine, previously unmeasured precision hole, and it is a design gap rather than a
narrow bug. Recall of 87.5% should not be quoted without it.

## 3. Metric summary

| metric | value |
|---|---|
| strict M8 recall | 80/224 = 35.7% |
| V1 confirmed PDCD1 asset recall | 25/28 = 89.3% |
| V2 confirmed PDCD1 asset recall | 35/40 = 87.5% |
| reachable V2 confirmed PDCD1 asset recall | 35/40 = 87.5% |
| residual uncertainty interval | [71.4%, 87.5%] |
| confirmed negatives surfaced | 42/133 = 31.6% |
| per-asset target attribution | absent — all 1136 candidates stamped `PDCD1` |
