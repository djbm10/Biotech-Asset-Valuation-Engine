# Validation record

## Evidence and reporting

- Prospective PLAN.md hash verified; old discovery v1 FROZEN.sha256 verified without rescoring.
- All selected archived evidence spans/JSON paths verified by the handoff CLI.
- Two initial local renders were byte-identical. After adding the independently fetched rights
  disclosures, the final brief was regenerated and the focused determinism test passed.
- New follow-up tests: 9 passed. They check citation requirements, independent maturity/commercial
  dimensions, unknown rights, evidence corruption/bounds and deterministic rendering.
- New research Python files and test pass Ruff. Full `ruff check src/` still reports 7,568
  existing findings; no production source changed.
- Focused reporting/triage/ontology regression after the timing fix: 83 passed in 2.51 s.
- Final full scientific suite: **2,000 passed, 3 xfailed**, one existing warning, in
  **2,017.75 s (33m 37s)**. The previously failing timing check passed. See REGRESSION.md
  for the measured confound and limits on attributing the uninstrumented historical failures.

## Scientific scope and final-output review

Implementer desk review of the final brief: primary facts checked against archived UCB releases,
ACR abstracts, registry protocols, the publisher-linked Earendil program data, and SEC-filed issuer/
EpimAb licensing disclosures. Registry statuses
are dated, not assumed operationally current. The preclinical model, acquired-program context,
estimated enrollment, serious adverse events, unsupported efficacy, historical territory exclusions and unknown current amendments remain explicit.

The two-case evidence gaps improved; this is not an accuracy estimate or a validated autonomous
qualification system. No discovery credit, gate decision, human-PoC confirmation, alias merge or
validation-grade promotion was made. No full-scale replay, paid execution or external messages.
Independent BD final-output review and analyst-time measurement remain **OUTSTANDING**.

## Diagnostic transparency

The initial full-suite diagnostic was interrupted after its hook raised an AssertionError in
pytest setup (item.addfinalizer was called before the appropriate setup context). No GC measurement
from that run is used as evidence. The corrected hook wraps pytest_runtest_call, restores the
original helper in finally, and passed both isolated shared-alias tests before the ordered-prefix
run. Failed/interrupted diagnostic logs are retained locally; the regular suite does not load it.
