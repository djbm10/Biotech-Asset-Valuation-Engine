# Analyst correction: historical exposure and dated preclinical evidence

**UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability.**
Implementing-agent source check, 2026-10-24. Independent human BD review remains pending.
This addendum supersedes any impression of complete trial coverage or current-stage verification
from the previous package. The previous dated artifacts remain unchanged for audit.

## Cizutamig: investigate the originator-code clinical history

The new bounded workflow started with **cizutamig only**. Registry intervention metadata supplied
**CND106**; the already acquired EpimAb disclosure explicitly pairs **EMB-06 (CND106)**. Searching
the derived historical code recovered **NCT04735575**. These relationships were generated from
source content, not a product-specific code table. The implementing agent inspected the actual
registry intervention fields and EpimAb passage: together they support the historical naming chain
in this case. This manual conclusion is separate from the workflow's provisional retrieval labels;
no identity was merged in BVE. Formulation, manufacturing and any program-version changes still
require diligence. Sources: [registry naming fields](https://clinicaltrials.gov/study/NCT07215663),
[EpimAb disclosure](https://www.epimab.com/en/news/3CmnUq).

The [historical trial](https://clinicaltrials.gov/study/NCT04735575) is a Phase 1/2 study in relapsed
or refractory multiple myeloma, sponsored by Shanghai EpimAb Biotherapeutics, with **40 ACTUAL**
enrolled and registry status **TERMINATED**. The record, last updated 2025-05-28, attributes stopping
to company resource optimization and a product-development change. This is a sponsor-reported reason,
not an independent explanation, evidence of toxicity, or proof the molecule failed. The registry
lists EMB-06 as the biological intervention. These are prior oncology exposures, not autoimmune PoC.

All nine records in the old limited query remain in the current root-query result; the historical
code contributes one additional distinct record. **Ten retrieved records still do not mean all
trials.** Three returned records have intervention names that do not exactly equal an issued term;
they remain UNATTRIBUTED_QUERY_HIT rather than being silently normalized into the asset's history.
Chinese, EU and Japanese registries remain unsearched. The code is strict about exact names and has
no global collision inventory. See [generated history](run_02/HISTORY.md) and
[query/pointer provenance](run_02/history.json).

**Next action:** obtain the originator study report/ASH presentation, reconcile the reason for
stopping with subsequent development and formulations, and review identity before using exposure
counts in a diligence memo. Search additional registries under the reviewed names. Do not combine
oncology and autoimmune cohorts or registry enrollment targets into one efficacy denominator.

Commercial correction to the AI review: UCB's completed acquisition means this is not an independent
Candid program. It does **not** establish that future collaboration is impossible. Availability
remains **UNKNOWN**. Chinese site locations or Asian participants cannot establish who holds or
supplies rights in those countries; current territory/contract diligence remains separate.

## HXN-1031: distinguish the relevant observation from current stage

The [2025 ACR abstract](https://acrabstracts.org/abstract/development-of-a-noval-111-cd19-and-bcma-dual-targeted-t-cell-engager-for-autoimmune-diseases/)
reports depletion of **B cells and plasma cells in cynomolgus monkeys**. That pharmacodynamic
observation is directly relevant to the proposed autoimmune mechanism and should have been prominent
in the earlier brief. The prior wording omitted it while emphasizing mouse tumor evidence.

The defensible label is **SUPPORTED: preclinical observations reported in the 2025 abstract**;
**UNKNOWN: current clinical-development/IND/CTA status**. The old zero-hit ClinicalTrials.gov search
was not a worldwide registry search and cannot establish that the asset remains exclusively
preclinical. Nonhuman-primate depletion is not human efficacy or autoimmune clinical PoC.
The archived abstract's hash was checked against the prior evidence ledger; no fresh ACR page
verification is claimed (the current browser request was blocked).

**Next action:** request depth/duration of depletion, relevant safety and recovery data, and current
IND/CTA/protocol identifiers from the program's responsible organization. Establish legal owner and
rights separately; Helixon author affiliation and Earendil listing do not resolve the chain of title.

## What this improves

A material missing historical trial is now recoverable through a reusable, source-linked retrieval
workflow. This is a **known-defect reproduction**, not a blind asset-discovery benchmark, independent
qualification result or human usefulness assessment. The supplied company source was already known.
The separate-session AI review found the defect; its 3/5 scores are AI judgments, not human responses.
No human review counters or historical review files were changed. Commercial landscape and competitor
features were deferred to keep this milestone focused on the demonstrated history gap.
