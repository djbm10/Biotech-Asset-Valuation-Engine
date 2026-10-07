# GENERIC_DESCRIPTOR_SPLIT_DIAGNOSIS v1 — do generic construct names pool distinct products? (diagnosis only)

**Status:** FROZEN 2026-10-06. No behaviour was changed.
**Baselines:** `~/se_runs/{tac01,mint5}_ncitid_v1`, ranking v2.

## 1. Frozen population

The enumerator is `research/se_generic_descriptor/enumerate_v1.py`. It was frozen before any
classification. The population is `population_v1.json` (sha256
`4cbef1b236f54291b662f9912ce4e4f7f2e882088e71e90a3312d97e1d17d7bd`).

An asset is a generic descriptor when **every token of every one of its own names** is either:
- a modality or format word (CAR, T, cells, injection, autologous, allogeneic, dual, cord
  blood, …), or
- an antigen designator (`CDnn`, BCMA, a bare number, or `CAR[T]nn`).

At least one CAR/TCR/NK token is required. No code, INN or trade name may survive.
- TAC01: 137 assets, 42 with 2+ trials.
- mint5: 142 assets, 43 with 2+ trials.

## 2. Classification method

The classifier is `research/se_generic_descriptor/classify_v1.py`; its output is
`classification_v1.txt`. For each trial it reads:
- the asset's own intervention entry (name, `otherNames`, description);
- the product codes in that entry;
- the lead sponsor, as context only.

| Verdict | Meaning | TAC01 | mint5 |
|---|---|---|---|
| A1 | single trial | 90 | 87 |
| A | every trial carries one shared product code | 0 | 0 |
| **B** | 2+ trials carry **different** product codes | **5** | **5** |
| C | multiple sponsors; no code unites or separates them | 40 | 40 |
| C1 | one sponsor; codes don't decide | 6 | 6 |

**The B cases are the same five in both benchmarks:**
- **`CART19`** (33 trials, 14 sponsors). Pools Penn CART-19, Miltenyi MB-CART19.1 / MB-CART2019.1, PACE CART19 and others.
- **`CAR19`** (8 trials). Pools UCL CAR19, UNC iC9-CAR19 (AP1903) and OSU CAR19.20.
- **`anti-CD19 CAR NK cells`**. Pools Changhai KN5501 and PersonGen NK-92 with 7 uncoded trials.
- **`CAR-T Therapy`**. Pools Union Hospital CT1192 and CT1195E with uncoded trials.
- **`CAR-20`**. MCW CAR-20 and the bispecific CAR20.19.

**C is not "same product".** Most C assets are 2–9 hospital trials from different sponsors
with no code on either side. Example: *CD19/BCMA CAR T-cells*, with Zhejiang/Yake
`CD19/BCMA-005` and Ucello `DCAR-SLE`. These are almost certainly pooled too, but no
structured identifier exists to separate them. Sponsor alone is not admissible identity
evidence.

## 3. Materiality

**Pooling is real but not material to either shortlist.**
- **Unranked.** 105 of 137 TAC01 and 102 of 142 mint5 generic assets have no qualification
  reason, so they are held out of the shortlist. That includes **every B asset except `CAR-20`
  (TAC01 #159)**. `CART19`, `CAR19`, `anti-CD19 CAR NK cells` and `CAR-T Therapy` are not
  ranked at all.
- **Ranked.** The generic assets in the top 50 are single-trial (A1), so they cannot pool,
  except for:
  - *Allogenic CD19-CAR-γδT cell*, TAC01 #47: C1, one sponsor;
  - *universal allogeneic anti-CD19/BCMA CAR T-cells*, mint5 #23: C, two hospitals, no codes.
- No B asset is in either top 50. No ranked row is shown to carry another product's trials.

**Separability.** Only the coded trials of B assets could be split off by a general rule
(trial-level product code → its own asset). The uncoded remainder stays a generic pool. A
split would mint new coded assets, such as MB-CART19.1, KN5501 and CT1192. They would enter
qualification and ranking as new candidates. That is a population **addition**, not cleanup,
and it should be preregistered as such if wanted.

## 4. ICG318 / BCMA-CD19 cCAR

**Not caused by this mechanism.**
- Neither asset is a generic descriptor, because `cCAR` is iCell's construct term. Both
  assets hold only iCell trials, so nothing is pooled.
- The split is a code-vs-descriptor identity gap.
- **Structured link found.** The cCAR trial NCT06787989 carries sponsor protocol id
  **`ICG318-ITP-01`** (`orgStudyIdInfo`), while its intervention is named "BCMA-CD19 cCAR T
  cells". The ICG318 trials name the intervention "ICG318, BCMA-CD19-IL-15/IL-15 sushi
  Compound CAR T".
- **Caution.** The cCAR asset also holds NCT04162353 (2019, multiple myeloma), which has no
  ICG318 reference. The IL-15/sushi armoured construct may be a later product. A merge on the
  protocol id would attach that older trial to ICG318.
- This is a separate milestone: protocol-id product-code evidence, with a trial-level rather
  than asset-level merge question.

## 5. Decision

- **GENERIC_DESCRIPTOR_SPLIT v1 is NOT preregistered.** B cases exist, but none is material
  to either shortlist, and the material C cases are not safely separable.
- Shortlist correctness is protected today by qualification holding generic pools out.
  **Any future change that admits generic assets must address pooling first.**
- **Next, by the operator's order:** ICG318, as its own milestone, on the protocol-id
  evidence above, with the NCT04162353 attribution question explicit. Then field-label
  cleanup.
