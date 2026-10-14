# v4 R3 policy — 2026-10-13 (frozen before the v4 measurement; `8ca2a76` unchanged)

Policy for admitted legacy facts whose adjudicated support is an **unsupported** structure (COPULA, CLASS_OF, NAME_SELF_DESCRIBING, STRUCTURED_OTHERNAMES, CROSS_SENTENCE_COREFERENCE), or that have no adopted PRODUCT_LEVEL support:

1. Missing PRODUCT_LEVEL certification from an incomplete extractor is **not evidence the fact is false**.
2. An unsupported fact is **not verified** whole-product modality.
3. Keeping legacy behaviour is **not certification**.
4. The consumer routes every admitted fact without adopted PRODUCT_LEVEL support (and without conflict) to **UNKNOWN_REVIEW**: non-decisional, legacy value preserved for audit, not deleted.
5. **Readiness clause:** a migration is not DESIGN_READY if it moves any adjudicated-TRUE admitted fact from a decisional state to UNKNOWN_REVIEW, because it would discard verified correct information without distinguishing it from false facts. The alternative, retaining unsupported legacy facts, retains the adjudicated-FALSE facts and fails R1. No third option is defined, since that would require distinguishing evidence the representation lacks.

R3 is therefore met only if the number of adjudicated-TRUE admitted facts routed to UNKNOWN_REVIEW is **0**.

**Prediction (from the frozen adjudication alone, before measurement):** 6 of 8 TRUE admitted facts have unsupported support types, so R3 is expected to fail and v4 to STOP. The measurement tests whether the extractor behaves as the adjudication implies. In particular, it checks whether the two APPOSITIVE facts are actually certified under v3 routing and whether any FALSE fact is accidentally certified.
