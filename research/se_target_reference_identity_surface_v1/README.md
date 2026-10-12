# TARGET_REFERENCE_IDENTITY_SURFACE v1 — ADOPTED

Preregistration `3ac5faa`; candidate `07d104b`. All T1–T12 passed in the one formal evaluation. No candidate changes followed formal scoring.

The parser retains the certified target entity separately from the biological symbol. Authority lookup uses the reference; source requests use biological text. A reference must agree with the installed resolver version and declared canonical target. Invalid references fail closed. Legacy objects omit absent metadata and retain their prior serialization. No new aliases were admitted.

## Frozen results

- 12 positive synthetic queries compile; two refusal controls remain refused.
- 18 exact source-request oracles across six connectors pass in both reference and qualified-ID modes (36 comparisons).
- Nine asset/target assertions and nine actual ANY target-gate comparisons match their frozen identity semantics. The gate audit feeds each of the three qualified target IDs as a normalized `targets` fact against each certified requested entity: same entity PASS, different entity FAIL. Its first invocation omitted the required expression operator and stopped during harness construction; adding the already intended ANY operator changed no production code, oracle or expectation.
- 103 complete current scientific controls preserved after independently validating references and projecting only the preregistered metadata/version changes.
- 1,791 historical source checks match original implementation archives; original research artifacts and historical scorers remain unchanged. Historical certification is not represented as current-HEAD historical isolation.
- 4,704 frozen parses: zero scientific-field, span or provenance differences. All 16 raw resolver and complete intent controls unchanged.
- FXI retains TARGET:F11, compiles five plans, and emits no ontology namespace in search literals. Bare F11 remains ambiguous. This is diagnostic evidence, not generalization validation.
- All 14 synthetic queries produce identical intent/problem/plan/request outputs under hash seeds 0, 1 and 42.
- Full `tests/se`: 1,828 passed, three existing xfails, zero failures/errors. Ruff clean.

## Reproduction

Run with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`:

- `python scripts/score_target_reference_v1.py`
- `python scripts/check_target_reference_determinism.py`
- `python -m pytest -p no:cacheprovider tests/se -q`
- `ruff check --no-cache src/bve/se tests/se scripts/evaluate_target_reference_v1.py scripts/score_target_reference_v1.py scripts/check_target_reference_determinism.py`

Tests `test_target_reference_compatibility.py` separately certify the original historical source archives and current 103-case compatibility. Original historical scoring scripts are unchanged and remain applicable at their original revisions.

No live searches/replays or holdout probes occurred. H21–H25 and H6–H10 remain unrun. IL-4Rα and factor XI remain missing aliases. The engine is not yet validated. The separate capitalization nondeterminism, C056 reader defect, failed receipt oracle, and stopped human-PoC recovery are unchanged.

Next: resume TARGET_QUERY_ALIAS_COVERAGE v1 by diagnosing and preregistering authority-backed Greek spelling equivalence and NCIt protein synonym admission separately where their evidence semantics differ. Do not treat structural identifier eligibility alone as synonym admission, and do not infer equivalence by removing biological qualifiers.
