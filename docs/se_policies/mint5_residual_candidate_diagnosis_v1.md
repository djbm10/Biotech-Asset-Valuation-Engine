# MINT5_RESIDUAL_CANDIDATE_DIAGNOSIS v1 — suspicious mint5 top-20 rows (diagnosis only)

**Status:** FROZEN 2026-10-06. No behaviour was changed.
**Baseline:** `~/se_runs/mint5_ncitid_v1`, ranking v2.
**Evidence used:** sealed CT.gov records (interventions, `otherNames`, descriptions, lead
sponsor, collaborators, org study ids), the identity graph, and the NCIt/ChEMBL links. None of
the frozen rows has an NCIt or ChEMBL record.

**Categories:**
- **A.** Duplicate of another canonical product.
- **B.** A trial-arm, field or intervention-list label, not a product.
- **C.** A legitimate distinct product.
- **D.** Unresolved.

## 1. Frozen rows

| Row | Name | Trials | Sponsor |
|---|---|---|---|
| #3 | umbilical cord blood CD19-BCMA CAR-T cells infusion | NCT06947473 | Beijing GoBroad Hospital |
| #6 | allogeneic umbilical cord blood-derived CAR-T targeting CD19 and BCMA | NCT07274059 (`UDCAR-SLE`) | Chengdu Ucello Biotechnology |
| #9 | Assigned Interventions CD19/BCMA CAR T-cells | NCT05030779, NCT05085418/31/44 (`CD19/BCMA-001…004`) | Zhejiang University, collaborator Yake Biotechnology |

## 2. Findings

**#3 and #6 are not the same product. Verdict: #3 D, #6 D leaning A (against a non-top-20 asset).**
- They have different sponsors (a hospital in Beijing and a company in Chengdu), and no
  identifier, `otherNames` or collaborator links them. "Cord-blood CD19/BCMA CAR-T" is a
  construct description, not an identity.
- #6 has a probable sibling outside the top 20: *allogeneic cord blood-derived, dual-targeting
  CD19/BCMA CAR-T cells* (NCT07139509). That trial is run by Xi'an No.3 Hospital with
  collaborator Ucello Therapeutics, and its dosage form is "UCAR-T cell injection". The link
  is sponsor/collaborator context plus construct description only, with no shared code. Under
  the standing principle (no merge on sponsor overlap or name similarity) this is **not
  mergeable**. It stays D.
- #3's product source is not stated in its record, so it is D.

**#9 is a real product with a contaminated name. Verdict: C (name artifact), plus an
unmergeable partial duplicate.**
- **Label.** The registry's own intervention name is literally "Assigned Interventions
  CD19/BCMA CAR T-cells". The sponsor pasted the CT.gov field header into the name field. Our
  parser did not create it. The description gives the product's real name: "Other Name:
  CD19/BCMA CAR T-cells injection". So this is a **real therapeutic product**, the Zhejiang
  University/Yake programme, behind a polluted label. It is not B: the row is not an arm, a
  field or a list. Only its name contains a field label.
- **Duplicate.** The same programme's fifth study, NCT05263817 (`CD19/BCMA-005`, same sponsor
  and collaborator, `otherNames` "CD19/BCMA CAR T-cells injection"), sits in a different
  asset: generic *CD19/BCMA CAR T-cells*. That asset also pools an unrelated Ucello trial
  (NCT07266337, `DCAR-SLE`). Merging #9 into it would import the Ucello trial, which would be
  a false merge. The defect is that the generic descriptor pools two sponsors' products. That
  is the same failure shape as `CART19`, for a dual-target construct.
- **Scope.** The pattern occurs once in each benchmark, in the same asset. There is no other
  field-label name in TAC01 or mint5.

## 3. Root causes, kept separate

1. **Field-label contamination in a source-supplied name** (#9). A naming/qualification
   question. Its population is 1 asset. A preregistered fix would strip a closed set of
   CT.gov field headers ("Assigned Interventions") from a name and keep the original as an
   alias. That changes the display and the identity key. It suppresses nothing, because the
   product is real.
2. **Generic construct descriptors pooling several sponsors' products** (the *CD19/BCMA CAR
   T-cells* asset). An identity question: the generic-designator problem beyond `CAR19`-shaped
   names. A fix would have to **split** pooled descriptors, not merge into them. It needs its
   own diagnosis, and it is the larger defect.
3. **Same-construct, different-sponsor rows** (#3 and #6). No defect is demonstrated. They
   stay separate.

**No row qualifies for removal (B), and none has merge evidence meeting the adopted standard.**
No merge or suppression fix is justified by this diagnosis as-is. Fix 1 is cosmetic-plus-key.
Fix 2 is the substantive one.

## 4. Top 20 after diagnosis

The top 20 is unchanged. By verdict: 17 rows are not in scope, #3 and #6 are D, and #9 is C
with a name artifact. No false duplicates are confirmed.
