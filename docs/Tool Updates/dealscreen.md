# DealScreen: screening a BD team's own landscape

Plain-language updates on DealScreen, the workflow that takes the asset landscape a BD team
already has and turns it into a defensible shortlist and first valuations.

## 2026-10-28: tested on real public data; two valuation problems explained

**What changed**

DealScreen was run on 40 real myasthenia gravis programs built only from public sources:
ClinicalTrials.gov, FDA labels and the ChEMBL drug database. Every cell records where it came
from. Two valuation problems from the first version were also tracked down.

**Why it matters**

A synthetic demo only shows that the software runs. Real data shows what it gets right and
where it gets stuck.

**How it works, plainly**

- **What happened on real data.**
  - Nothing was wrongly included or wrongly excluded, compared with a reference written before
    the run. That reference came from the same AI that built the tool, so this is an internal
    check, not independent proof.
  - Four of the nine programs that fit were found automatically. The other five, including
    the market leader efgartigimod (Vyvgart), were put in "needs review", not rejected. The
    reasons were wording, such as "Protein" instead of "antibody", or "Generalized Myasthenia
    Gravis" instead of "Myasthenia Gravis", or a target that no structured source states.
  - No source said who holds U.S. rights for any program, so the tool says "unknown" rather
    than guessing.
- **The two valuation problems.**
  - One example drug valued higher in its "bear" case than its base case. That is correct
    arithmetic for a drug that loses money even if it succeeds: a lower chance of success
    means less money spent on trials. The tool now says so in plain words, and refuses to
    show any out-of-order result it cannot explain.
  - The canonical RLAY example crashed, and its design settings had been silently ignored,
    which raised its value from $44M to $65M. It now stops with a clear error. The fix to the
    example's settings needs sign-off from the valuation owners, so it is prepared but not applied.
- **No more implied approvals.** An AI assistant can now list candidates but can never mark
  anything approved or confirm evidence.

**Proof it works**

- 72 DealScreen tests, including one that pins the real-data result.
- Report: `research/dealscreen_real_v1/REPORT.md`. Audit:
  `research/dealscreen_hardening_v1/FINANCIAL_AUDIT.md`.

## 2026-10-27: first working version (synthetic demonstration)

**What changed**

BVE can now take a landscape spreadsheet, the kind a BD team exports from its data provider.
It checks every program against a specific buyer's requirements, keeps a record of what the
analyst decided and why, values up to three chosen finalists with BVE's existing valuation
engine, and produces an Excel workbook and a one-page memo.

**Why it matters**

Until now, BVE's search tools found programs on their own from public sources, and their
precision on unseen targets was low. Most BD teams already pay for a landscape. The
bottleneck is not finding programs; it is deciding which ones fit *this* buyer, showing why,
and keeping scientific fit apart from whether the rights can actually be had.

**How it works, plainly**

- **Import.** Each provider's column names are mapped once, in a small settings file. Every
  original row is kept exactly as written, and every row that cannot be used is listed with
  the reason.
- **Screening.** Screening uses BVE's existing eligibility engine: each requirement is
  PASS, FAIL or UNKNOWN (missing or conflicting data), and each answer cites the row and
  column it came from. Missing data is never treated as a pass or a fail.
- **Rights.** U.S. licensing rights are a separate column. "No license recorded" never
  becomes "available".
- **Shared codes.** Two different companies' drugs with the same code are never merged
  automatically. That was the MB-102 failure in the IL3RA pilot.
- **Research assistant.** It can look things up (a target, a phase, a rights statement) and
  must quote its source. Nothing it finds counts until an analyst confirms it.
- **Approvals.** Approvals are explicit, named, dated and tamper-evident. A program that
  failed a hard requirement cannot be approved.
- **Valuation.** It runs through BVE's own command-line tool and reads the saved result,
  so the numbers match the engine exactly. A finalist without owned market and cost
  assumptions is marked NOT READY rather than given invented ones.

**Proof it works**

- An end-to-end run on a 200-row synthetic landscape. Every row is accounted for.
- 184 of 192 programs land where the synthetic answer key expects. The 8 differences are
  deliberately cautious: programs left "needs review" rather than excluded.
- No false exclusions, no wrong merges, and no rights shown as available without a statement.
- 59 automated tests, including the MB-102 case, tamper detection, and a check that the
  valuation numbers in the workbook equal BVE's saved output.

All of this is synthetic and UNVALIDATED. It shows the workflow works, not that it is
accurate on real data. Details: `docs/dealscreen/README.md`.
