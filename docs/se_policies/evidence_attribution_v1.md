# Asset-specific evidence attribution (v1)

Status: **DECLARED**, 2026-10-25, before any code change. Development work: the examples
below come from the already-disclosed GUCY2C development corpus. **Not validation.**
Follows `gi_area_evidence_v1.md`. Its post-hoc B4/B7 failures and Amendment 1 stay in the
record unchanged.

## Problem

A free-text document's context is turned into a fact about every drug name in it:

| Fact | Where | Behaviour today |
|---|---|---|
| `therapeutic_area` (gate-decisive) | `evidence/pubmed.py` (G2), `evidence/generic.py` | every area anywhere in the abstract/document attaches to every name in it |
| candidate `modality_id`, `modality_id` fact | PubMed and indexed/URL adapters → `resolution/registry.py:289`, `generic.py` | the document's single modality term attaches to every name |
| construct target set | `construct_targets.py` | already attributed (cue in the same clause): **unchanged** |
| `human_poc_present` | `human_poc.py` | already attributed (sentence names the asset and no other): **unchanged** |
| CT.gov area, stage, status | `clinicaltrials.py` | a structured intervention → condition record: **unchanged** |

Development examples (no rule below names a product):
- **dextran** is a colitis inducer, and its abstract has no area term; it carries modality `T_CELL_ENGAGER`.
- **aniline** is an ADC catabolite. It gets ONCOLOGY from "plasma and tumor samples" and ADC modality.
- **ether** is part of a sensitizer's chemical name. It gets ONCOLOGY from "tumor-targeting" and RNA modality.
- **polyethylene glycol** is a constipation therapy, but every GI sentence coordinates it with another drug.
- **TAK-264**: "Evaluation of TAK-264, an Antibody-Drug Conjugate in Pancreatic Cancer Cell Lines…".

## Three evidence types

1. **Document context**: the document discusses an indication or modality.
2. **Mention**: the document names the asset.
3. **Asset attribution**: a structured record or an attributable passage establishes that
   *this* asset is studied for the indication, or *is* of the modality.

Only type 3 produces a gate-decisive fact. Types 1–2 are kept as contextual facts with
their citations, `document_therapeutic_area` and `document_modality_context`, which no gate
reads.

## Rules (free-text documents only: PubMed and public documents)

Sentences are split at `.`, `!` and `?` followed by whitespace. Names are matched as whole
words, case-insensitively, on the hit's own asset name only.

- **R1 Area attribution.** A sentence attributes area A to asset X when all of these hold:
  - X occurs, and an A lexicon term occurs **after** it within 12 tokens;
  - between them is an indication cue: `in`, `for`, `against`, `treat`, `treats`, `treating`,
    `treatment`, or `patients`;
  - X is **not coordinated** with another product: the token directly before or after X is
    not `and`, `or`, `plus`, `with`, `versus`, `vs`, `combined`, `combination`, `+`, or `/`.

  One attributing sentence produces one `therapeutic_area` fact, citing that sentence.
- **R2 Modality attribution.** A sentence attributes modality M to X only by apposition or a
  head noun:
  - `X, a|an|the <≤4 tokens> <M phrase>`;
  - or `<M phrase> X`, with the phrase ending at most 1 token before X.

  Without that the hit's `modality_terms` is empty, and the document's modality goes to
  `document_modality_context`.
- **R3 No inference from absence.** No attribution produces no asset area or modality fact.
  The area gate then reads UNKNOWN (review), never FAIL. A contextual fact never produces
  PASS, FAIL or EXCLUDED.
- **R4 Unchanged:**
  - structured registry facts;
  - authority modality and target edges;
  - construct targets;
  - human-PoC attribution, including C9's document-area condition, which can only *withhold* a promotion;
  - gate semantics, qualification and identity.

## Eligibility display (TAK-264)

TAK-264 is ELIGIBLE because every declared gate passes:
- identity;
- construct target GUCY2C (two authorities);
- authority action BINDING AGENT;
- area;
- minimum stage.

Before this change, the area PASS came from document-level PubMed ONCOLOGY facts. Under R1
it survives only through an attributable sentence; the title above qualifies. Under the
declared criteria this is **historical scientific eligibility**. The problem has no
activity gate, and the run holds no ownership or licensing facts.

- **D1.** The `Disposition: ELIGIBLE` line gains the note "meets the declared search
  criteria; not evidence of current development, ownership or licensing availability".
- **D2.** `Status:` becomes `Trial registry status:`, with the note "status of each cited
  trial record (historical programmes are not excluded)".
- **D3.** `Phase:` shows the **highest** stage across the cited stage claims, with "highest
  of N cited trial records". Today it shows the first record's stage.

## Synthetic cases (tests, written before the implementation)

| Case | Expected |
|---|---|
| Oncology abstract naming a reagent ("plasma and tumor samples contained X aniline") | no asset area for the reagent; `document_therapeutic_area` ONCOLOGY kept |
| Multi-drug paper, one drug evaluated for cancer ("Y improved stool frequency; X in patients with colorectal cancer") | X → ONCOLOGY; Y gets no ONCOLOGY |
| Coordinated drugs ("X or Y for chronic constipation") | neither attributed (UNKNOWN) |
| Drug with genuine evidence in two areas (two sentences) | both areas attributed; an oncology request PASSes |
| Trial record with explicit intervention → condition | unchanged CT.gov area fact |
| Ambiguous abstract (area term only before the name, or no cue) | UNKNOWN |
| Historical programme, all trials terminated, gates pass | ELIGIBLE kept; status and D1 note shown |
| Vaccine / CAR-T trial intervention | CT.gov area fact unchanged |
| Apposition ("X, an antibody-drug conjugate") | modality ADC; a document-only modality is context |

## Acceptance criteria (frozen before implementation)

Development replay on the same sealed bytes, with pre-C10 code `94fefff` + G1/G2 + this
change, against `gi_v1_preC10`.

| | Criterion |
|---|---|
| E1 | All 12 recovered reference assets stay analyst-visible; recall 12/17 visible and all |
| E2 | 0 negative-control hits; the 3 agonists stay EXCLUDED by the agonist rule |
| E3 | dextran, aniline and ether have no asset-specific area fact and no modality |
| E4 | Every free-text `therapeutic_area` claim cites a sentence that names the asset and satisfies R1 (machine-checked) |
| E5 | No candidate becomes FAIL/EXCLUDED on a fact it did not have before; identity unchanged (279 candidates, 2 merges, 1 split); targets unchanged |
| E6 | ELIGIBLE count ≤ 1; any ELIGIBLE asset has an R1-attributed or structured area fact |
| E7 | CT.gov area facts of all 12 recovered assets unchanged (vaccines and cell therapies not suppressed) |
| E8 | Wall clock ≤ +20%, RSS ≤ 4.5 GB |

**Expected cost, declared now.** Candidates excluded in v2 on document-level GI evidence
whose GI sentences coordinate several drugs will return to REVIEW as UNKNOWN. The
visible count may rise. That is the correct price of R3, and it is reported, not tuned.
