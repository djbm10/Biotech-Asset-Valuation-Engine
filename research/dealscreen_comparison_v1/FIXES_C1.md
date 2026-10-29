# Cycle C1 fixes: ranked from the frozen baseline critique (criteria before code)

Source: `CRITIC_BASELINE.md` (77775ef) and the frozen C run. Verdict before fixes: no demonstrated
DealScreen advantage over general Claude. Every fix must be generic (no CLDN18-, gastric- or
company-specific rule) and must hold on the FcRn and C5 landscapes.

| Rank | Id | Observed failure | Generic root cause | Fix |
|---|---|---|---|---|
| 1 | X1 | As installed, 0 of 30 in-scope programs eligible: "Claudin 18.2" / "CLDN18.2" unreadable | Target names written as a protein isoform ("<name> <n>.<m>", "<SYMBOL><n>.<m>") are not gene symbols | Read an isoform name as its gene when the gene name/symbol resolves; disclose "isoform not distinguished by the gene authority" on the asset |
| 2 | X2 | Offline research crashed on partial dates ("2016-10") in the supplied library | Date parser accepts full ISO dates only | Accept YYYY-MM and YYYY as no exact date, with a limitation note |
| 3 | X3 | 28 rows indication UNKNOWN, incl. Phase 3 gastric ADCs | Registry conditions use coordination ("A or B adenocarcinoma"), biomarker subsets ("CLDN18.2-positive X") and extent qualifiers ("locally advanced unresectable X") | Indication reading v2: expand "A or B <head>"; read "<marker>-positive X" and extent-qualified X as X; multiple qualifiers; same disclosure as v1. "Gastric cancer" stays UNKNOWN (ambiguous, and broader than the buyer's adenocarcinoma) |
| 4 | X4 | Returned rights (LM-302, SKB315) and options (SHR-A1904) cannot be recorded; LM-302's return lost from the memo | Rights vocabulary has no RETURNED / OPTION states | Add RIGHTS_RETURNED_TO_ORIGINATOR and OPTION_HELD_BY_THIRD_PARTY (neither is availability), readable in assertions/proposals, shown in memo and workbook |
| 5 | X5 | The tool's rank puts three programs whose U.S. rights large pharma holds at #2–#4, and the same molecule twice | No buyer-declared transaction preferences; scientific rank used as the opportunity order | Buyer-declared `transaction` preferences (exclude or deprioritise marketed; deprioritised rights holders/sponsors; encumbered rights); a separate **transaction view** (tier + reasons) next to, never inside, the scientific disposition; same-molecule records marked |

**Deferred (recorded):** vendor modality errors (LCB02A, IBI343: needs human-confirmed facts, by
design); EO-3021/SYSA1801 identity (authority gap); an agent question for indication; valuation
narrative disclosure of the engine's tax rate and scenario shocks (P-series proposal addendum);
evidence citations with URLs in the memo.

## Acceptance criteria

- **X1.** "Claudin 18.2", "CLDN18.2", "Claudin18.2", "claudin 18 isoform 2" read as CLDN18 with the
  reading listed on the asset (`target_readings`) and in the workbook. Not applied when the full text
  already resolves; never to "PD-1"-style names (no dot-number isoform). FcRn and C5 landscapes:
  dispositions unchanged.
- **X2.** A library document dated "2016-10" or "2016" yields findings with `document_date` None and
  a limitation "partial date (YYYY-MM): exact date not known". Invalid text still yields None, never a crash.
- **X3.** "Gastric or Gastroesophageal Junction Adenocarcinoma" reads as both concepts;
  "CLDN18.2-positive Adenocarcinoma of the Gastroesophageal Junction" and "Locally Advanced Unresectable
  Gastric Adenocarcinoma or Cancer" read as their parents; "Gastric Cancer" and "Solid Tumor" do not.
  Held-out: the 75k S&E condition strings, every new reading listed and reviewed for correctness;
  FcRn/C5 dispositions unchanged.
- **X4.** Rights quotes stating a return of rights or an option read as those statuses; neither counts
  as AVAILABLE; memo and workbook show them; the AI proposal path accepts them.
- **X5.** Buyer YAML may declare `transaction:` preferences; without them, behaviour is unchanged.
  The transaction view never changes a scientific gate or disposition. A deprioritised holder matches
  only against cited holder evidence or the registry sponsor, and the reason names which. No
  availability is ever inferred.

## X6 (found while measuring X1-X5; criteria before code)

**Observed:** ASP2138, QLS31905, AZD5863 and AMG 910 ("Claudin 18.2; CD3") stay UNKNOWN on target:
one unreadable part (CD3, a complex rather than a gene) voids the whole target set.
**Generic cause:** every T-cell engager names CD3; any multi-target construct with one unreadable
part is affected.
**Criteria:** when some parts of a target text are unreadable, a target fact is emitted only if the
readable parts include a buyer-requested target (a positive witness, enough for an ANY requirement),
with the unreadable parts listed as a disclosed limitation. Otherwise nothing is emitted, as today, so a
partial set can never produce a FAIL. An ALL-operator requirement is never satisfied by a partial set.
FcRn/C5 dispositions unchanged.
- **X6 amendment (during build).** ALL-operator requirements may also use the positive witness (a partial set that already contains every requested target is a valid witness); only EXACT_COMBINATION is excluded.

## Review (independent AI code review, before commit) and measurement

The review found 2 decision-level defects in the first versions, both fixed with regression tests:
X6 could turn UNKNOWN into a false FAIL for an ALL requirement and skipped claim reconciliation; X1
read "CLDN18.1" as CLDN18 for a buyer asking for 18.2 (a wrong PASS on a different isoform) and read
dose-like strings ("IL-1.2"). Also fixed: coordination slicing into the head ("Small Cell or Non-Small
Cell Lung Cancer"), qualifier coordination, biomarker-prefix shape, rights verbs without a rights
object ("patients returned"), "treatment option", and substring holder matching. Disputed: none.

**Measured on the frozen CLDN18.2 landscape, tool as installed (no synonym map, no date fix):**
reference-IN ELIGIBLE 0/30 → 14/30; reference-OUT or UNRESOLVED made ELIGIBLE: 0; research on the
supplied library: crash → 32 proposals. Remaining wrong exclusion: LCB02A (vendor modality cell says
"Monoclonal antibody"; needs a human-confirmed fact). FcRn/C5 pinned results unchanged; fast-path
equivalence byte-identical. DealScreen tests 303.

## X7 (found from the C2 re-run; criteria before code)

**Observed:** the C2 analyst saw 0 eligible "as installed" where engineering measured 14. Root cause
(verified in its workspace: `target_cache_meta.json` ontology_version null; even "CLDN18" cached as
null): the S&E ontology snapshot path defaults to the RELATIVE path `data/se/ontology/current`, so
running DealScreen from any directory other than the repository root silently loads no ontology and
every target, and every identity lookup, reads as unknown. The baseline C run also ran outside the
repository root, so its "0 eligible" had two causes (this, and isoform names, which fail even with
the ontology loaded).
**Severity:** silent, total loss of target screening with no warning; generic to every landscape.
**Criteria:**
- DealScreen resolves the default snapshot against the installed repository when the relative path
  does not exist in the current directory (S&E code unchanged; DealScreen sets the documented
  override only when it is unset and the anchored path exists).
- If no ontology is available and no `--target-map` was given, `import` and `screen` print a
  WARNING naming the consequence; the import manifest records it.
- Measured: the same commands from `~/.cache/...` and from the repo root give the same funnel.
- **X7 built.** Implemented at the CLI: user paths made absolute, then the process runs from the
  repository root when `data/se` is there and not in the current directory; a WARNING when no ontology
  is available and no `--target-map` was given. Amendment: the manifest does not record the warning
  (console only). Measured: the CLDN18.2 import from `~/.cache/x7` gives 14 / 25 / 23 with the
  ontology loaded and 7 identity flags, identical to the repository-root run.
- **P8 / P10 (DealScreen's own prototype CLI, not the protected engine).** `bve-dealscreen-value`
  now prints the engine's effective tax rate with the perspective line and warns when bear/base/bull
  are out of order. The engine's own reporting (P8/P9 in the Lane 1 proposal) is unchanged.
