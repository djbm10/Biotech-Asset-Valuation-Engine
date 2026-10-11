# H15_EXTRA_TARGET_DIAGNOSIS v1 — recorded, not diagnosed further, not fixed

**Status:** OPEN, recorded 2026-10-11 during SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1. Per the
operator, this case is not used in the shortlist diagnosis and nothing is fixed here.

**Observation (from the sealed H15 run output only; no resolver query was made):**
- Query: "Find clinical-stage ANGPTL3 inhibitors for homozygous familial hypercholesterolemia."
- The compiled target expression is ANY(ANGPTL3, **LDLR**). The intended target is ANGPTL3 only.
- The LDLR target in `problem.yaml` carries the alias `familial hypercholesterolemia`. The
  disease phrase was therefore read as a target name through an ontology gene/disease synonym.
- The compiled indication requirement is the literals `["inhibitors", "homozygous"]`. The
  disease phrase was consumed as a target and never reached the indication requirement.

**Question for the later milestone:** should a disease-name synonym of a gene be allowed to
compile as a target when it occupies the query's indication slot? This is
target-recognition semantics, separate from the shortlist work. The milestone should be
preregistered on its own population and must not be tuned on H15 alone.
