# Drug → Target Authority

Plain-language updates on how the tool decides what a drug actually acts on.

## 2026-09-07 — The tool stopped assuming a drug hits the target we searched for

**What changed**

Until now, if we searched clinical trials for PD-1 (gene name `PDCD1`) and a drug turned
up in one of those trials, the tool recorded that drug as a PD-1 drug. That is how the
search worked, not what the drug does. Chemotherapy given alongside a PD-1 antibody was
being filed as a PD-1 asset.

That inheritance is now gone. A drug gets a target only from published evidence about
that drug itself, and every answer is recorded with the source it came from.

**Why it matters**

Target attribution feeds competitor counts, crowding, and comparables. A wrong
attribution quietly inflates how contested a market looks. It also confuses two different
things that should stay separate: what a search *found* (legitimate discovery evidence)
and what a drug *is* (a claim we should be able to defend to a partner).

**How it works, plainly**

We built a versioned reference library of drugs, targets, and the documented mechanism
links between them, assembled from two public authorities: ChEMBL release 37 and Open
Targets release 26.06. For each drug the tool asks one question per target of interest
and records one of four answers:

- **Confirmed** — a source documents this drug acting on this target.
- **Confirmed, different target** — sources document this drug, and it acts on something
  else. (This is what correctly separates PD-L1 drugs such as durvalumab and
  atezolizumab from PD-1 drugs, even though both sit in the same pathway.)
- **Conflicting** — the two authorities disagree. We keep the disagreement visible rather
  than picking a winner.
- **Unresolved** — no source says anything. Silence is recorded as silence, never as a
  denial.

Two deliberate restrictions:

- **Only direct, single-protein evidence decides anything.** Some database rows say a
  drug acts on a protein *family* and then list every member gene. Reading that as "binds
  each of these" is a guess. Those rows are kept and shown to an analyst reviewing an
  unresolved drug, but they can never confirm or rule out a target.
- **Names are matched exactly, by identifier or registered synonym.** No fuzzy matching.
  A name that could mean two different molecules resolves to neither.

The whole library is content-hashed and versioned (`chembl_ChEMBL_37 · open_targets_26.06
· resolver_v2`), so any answer can be traced back to the exact source release it came
from, and the library can be rebuilt from scratch and checked byte-for-byte.

**Proof it works**

Measured against the frozen 173-drug PD-1 benchmark, running through the production code
path:

- **0 out of 133** non-PD-1 drugs were falsely asserted as PD-1. This was the failure
  mode being fixed, and it is now zero.
- **0** true PD-1 drugs were wrongly assigned to a different target.
- All four PD-L1 look-alike traps were correctly separated as different-target.
- Carboplatin, appearing in PD-1 trials, is now unresolved rather than a PD-1 asset.

Of the 40 confirmed PD-1 drugs, 29 are confirmed by documented mechanism and 11 remain
unresolved: early development programs and multi-target antibodies that the public
mechanism databases have not yet catalogued. Those are reported as unknown rather than
guessed, and they define what the next data tier has to solve.

Notably, adding the Open Targets source changed none of these benchmark numbers — the
rules were not loosened to make the score look better. It was included because it carries
direct mechanism evidence for **623 drugs** ChEMBL does not cover at all, which matters
for every future target we point the tool at.
