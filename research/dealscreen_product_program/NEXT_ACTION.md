# Next action (restart checkpoint)

**State at checkpoint (2026-10-28):**
- Branch `dealscreen-mvp`; Cycles 1-2 are committed (see `ITERATION_LOG.md`).
- Uncommitted user files: `AGENTS.md`, `research/universe/biotech_tickers.yaml`, `.claude/`, `.serena/`. Never stage them.

## On restart

1. Read `PRODUCT_GOAL.md`, `SCORECARD.md` and this file.
2. Confirm the branch and that `git status` shows only the user files above.
3. Re-run, with temp files on the home disk because `/tmp` is a small tmpfs:
   `TMPDIR=$HOME/.cache/dealscreen_suite python -m pytest tests/dealscreen -q -p no:cacheprovider`
   Expect 101 passed. `test_real_landscape.py` pins 4/14/22.

## Highest-value next cycle: Cycle 3, rights-holder vs availability (backlog 4)

**Why.**
- Every one of the 40 real programs shows U.S. rights UNKNOWN. That includes three U.S.-marketed products whose labeler is a public fact.
- Gate D needs owner / licensor, territorial rights, encumbrances, availability and unknown availability kept apart. Today there is one rights field.

**Plan:**
- Add holder facts derived only from explicit evidence:
  - the FDA labeler → "U.S. rights holder (labeler), availability UNKNOWN";
  - a registry sponsor is **not** a holder;
  - territorial licensee statements come from cited sources (e.g. the Immunovant 10-Q licensed-territory sentence) via assertions.
- Never infer availability.
- Write criteria first, as for Cycles 1-2.
- Measure on the real landscape: how many programs move from UNKNOWN to "holder known, availability UNKNOWN", with 0 AVAILABLE.

## Then, by backlog rank

- 5: separate U.S.-marketed, ex-U.S.-marketed and Phase 4 study stages. The profile maps any Phase 4 trial to stage order 6.
- 6: refresh diff between two exports, carrying decisions forward.
- 7: agent extraction of approval statements.

## Needs a person (cannot be engineered)

- **Gate H:** one BD / BD Finance professional to run the workflow on the real landscape. Record their actions, corrections, time and feedback.
- **Gate B:** an independent curator for a held-out landscape and reference, with thresholds preregistered before the run.
