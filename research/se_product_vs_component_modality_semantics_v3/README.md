# PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v3 — design STOP

Design `b12ee79` executed unchanged; population/labels/readiness frozen at `7dd05ae` before measurement. Verdict, computed by `audit.py::criteria`: **STOP_NOT_IMPLEMENTATION_READY, first failing requirement R3**. No implementation is authorized and there are no production changes.

Reproduce: `PYTHONPATH=src python research/se_product_vs_component_modality_semantics_v3/audit.py --output <new dir>`. Frozen hashes are verified; two builds are byte-identical. Self-test: a valid fixture is IMPLEMENTATION_READY; an unsupported product promotion fails R1, an unregistered population change fails R2, a withdrawn true fact fails R3, and a selected conflict fails R4.

## Results

| Requirement | Result |
|---|---|
| R1 control safety | PASS. All 14 v2 controls are correct, including the three former modifier failures (now non-product); all 25 head-attachment controls conform; the two NON_PRODUCT uncovered controls are not promoted |
| R2 accounting | PASS. 293/293 facts (TAC01 169, mint5 124), 13 admitted, 0 missing-provenance claims; routes: 59 CT.gov structured, 234 public document |
| **R3 no true admitted fact lost** | **FAIL.** 8 of 8 label-TRUE admitted facts (blinatumomab ×3, teclistamab, ATG-201, CLN-978, CC312 TCEs; BNT162b2 vaccine) would be withdrawn |
| R4 conflicts not selected | PASS. 1 conflict (a MONOCLONAL_ANTIBODY product claim against a TCE fact) → UNKNOWN |

Categories, all 293 facts: **0 A_PRODUCT**, 0 component-only, 0 relational, 282 D_AMBIGUOUS, 11 E_NO_SCOPED_EVIDENCE. All 910 same-value scoped assertions are AMBIGUOUS. The proposed consumer would withdraw all 293 to UNKNOWN. Among the 13 admitted: 5 label-FALSE facts withdrawn (correct; e.g. the CAR-T labelled VACCINE from a "Biological/Vaccine:" registry category, and immunosuppressant-withholding arms labelled VACCINE) and 8 label-TRUE facts withdrawn (wrong).

## Why: coverage, not safety

The corrected representation is safe but recognises almost nothing in real inputs. Real modality evidence is phrased as appositives ("Blinatumomab (Blincyto), an anti-CD19/anti-CD3 bi-specific T cell engager"), "in the class of", conference titles, and non-hyphenated premodifiers ("a recombinant, human IgG1-like TCE", "a BCMAxCD3 bispecific T-cell engager"). All eight uncovered-structure controls were AMBIGUOUS or had no modality text. CT.gov `name`/`type`/`otherNames` fields have no scoped representation.

So the boundary is the representation's **recall** on non-copular and premodified product descriptions. The legacy facts then split into true and false ones that scope evidence cannot yet tell apart.

## Not authorized / next

No consumer, no fact deletion, no grammar extension in this milestone. A further step would be a separately preregistered representation milestone covering appositive and premodified product descriptions (and possibly structured CT.gov fields), with its own frozen controls, before any v4 semantic design. Datopotamab's false PEPTIDE exclusion remains. ESG401 not started; H21–H25 untouched; H6–H10 unrun.
