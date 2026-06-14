# Future Fix — Autonomous Ticker + Lead-Asset Discovery

## Goal

Remove the manual seed bottleneck. Today a human types a ticker and authors an
identity seed (ticker, company, lead asset, indication, TA, stage, modality, NCT);
the pipeline auto-builds everything downstream. The discovery layer makes the seed
itself automatic.

**Operating model (not blind autonomy — precision-first):**
- **High confidence** → tool auto-adds the seed; pipeline builds a coarse profile/config.
- **Medium confidence** → tool *proposes* a seed; lands in the review queue.
- **Low / exception** → analyst review only (the exception list below).

Anti-goal: never let a wrong auto-added lead pollute the screen. Auto-add favors
**precision over recall**; everything auto-derived stays `evidence_level=coarse`
(economics heuristic) until reviewed — the existing honesty machinery still applies.

## Architecture — six stages (front-end to the existing pipeline)

```
[0] Enumerate universe      exchange/ETF/SEC-SIC -> candidate (ticker, CIK, name)
[1] Liveness / exclude      drop acquired/delisted/shell/SPAC -> exclusion ledger
[2] Detect assets           CT.gov sponsor trials + SEC/FDA -> candidate programs
[3] Rank lead asset         score programs -> lead + indication + stage + modality
[4] Propose seed            emit UniverseRegistryEntry + per-field confidence
[5] Route by tier           auto-add / propose (review queue) / exception
        |
        +-> existing: ProfileBuilder -> profile_store -> profile_to_config
                      -> watchlist_auto_generated -> M&A screen -> review_queue
```

Everything from Stage 5 onward already exists. Discovery only produces **seeds**.

## Source playbook (structured first; extraction later)

| Source | Yields | Precision | Status |
|---|---|---|---|
| **ETF holdings** (XBI/IBB/ARKG) | liquid, "real biotech" universe (~140 names) | high | NEW fetcher |
| **SEC `company_tickers.json` + SIC** (2834/2836/8731) | full listed pharma/biotech ticker↔CIK | high (broad) | NEW (SEC client exists) |
| **CT.gov `search_studies(sponsor=)`** | per-sponsor trials → drug, phase, indication, enrollment, status, dates | **high, structured** | EXISTS |
| **FDA** (Drugs@FDA, orphan/breakthrough/fast-track) | approvals + designations → stage/lead signal | high | EXISTS (`fda_client`) |
| **SEC 10-K Item 1 / pipeline narrative** | "lead/most advanced program", encumbrance | medium (needs NLP) | LLM phase |
| **Company pipeline pages** | structured-ish pipeline table | medium (scrape+extract) | LLM phase |
| **Press releases / 8-K** | catalysts, topline readouts, M&A events | medium | LLM phase |

**Principle:** CT.gov sponsor records are the workhorse — they alone yield drug +
phase + indication + recency for most names, *structured*, with an existing client.
LLM extraction of unstructured text (10-K, pipeline pages, PRs) is a later
confirmation/disambiguation layer, never the primary signal.

## The crux — lead-asset ranking

For each live company, CT.gov gives a set of candidate programs (cluster trials by
intervention/drug). Pick **the** lead by scoring each program:

- **Max phase reached** (phase_3 > phase_2 > phase_1) — dominant term.
- **Registrational intent** — pivotal-size enrollment, breakthrough/fast-track (FDA).
- **Sponsor is lead** (not merely a collaborator on someone else's trial).
- **Active & recent** — recruiting/active-not-recruiting, recent primary-completion.
- **Catalyst proximity** — near-term primary-completion / PDUFA.
- **Corroboration** — named "lead/most advanced" in 10-K (LLM phase).

`lead_confidence = f(margin(score#1 − score#2), source_agreement, single-asset clarity)`.
A clear single Phase-3 program with agreeing sources → high. Two close late-stage
programs, or CT.gov/PR phase disagreement → medium/exception.

## Confidence model + tiering

Overall discovery confidence combines component agreements:
`universe_membership` (XBI ∩ SIC ∩ trading) · `liveness` (active filer + trading +
active trials) · `lead_margin` · `phase_source_agreement` · `single_asset_clarity`.

Thresholds map to tiers (auto / propose / exception). **Calibrate the thresholds
against the 50 hand-authored seeds** (we know the right lead/indication/stage for
those) — a built-in labeled set. Backtest: run discovery on the 50, measure how
often it recovers the correct seed → precision/recall per tier. Do not enable
auto-add until auto-tier precision on this set is high (e.g. ≥0.9).

## Hard problems → mitigations (the exception list)

| Exception | Detection | Handling |
|---|---|---|
| Unclear lead asset | low `lead_margin` | → review (`ambiguous_lead_asset`, exists) |
| Multiple co-lead assets | ≥2 programs within margin ε | → review (`multiple_lead_candidates`, new) |
| Conflicting phase/indication | CT.gov vs FDA/PR disagree | record both → `conflicting_sources` (exists) |
| Discontinued/acquired/delisted/shell | 8-K 2.01, Form 25, going-concern, SEC shell-flag, no trading | **exclusions engine** → exclusion ledger w/ reason+date |
| Uncertain rights / partner encumbrance | 10-K "Collaboration/License", CT.gov collaborators | default no-encumbrance, flag → review (new reason) |
| Aliasing / dedup | code-name vs generic vs brand; ticker/company renames | alias map (`company_aliases.yaml`) + CT.gov synonyms + `normalization/normalizer.py` |

## Closed-loop learning (the compounding idea)

Every analyst disposition already logs to `profile_review_decisions` (approve/reject/
defer on proposed seeds + field corrections). These are **labels**. Start the lead
ranker as a transparent heuristic; over time learn weights from accumulated
decisions (which proposed lead the analyst confirmed vs. corrected). The review
loop becomes the training signal — the more it's used, the fewer items it routes
to humans.

## Phased plan (incremental, reuse-first)

- **A. Universe + liveness.** XBI holdings + SEC SIC enumeration; trading + active-filer
  filter; wire the existing `exclusions` engine into an **exclusion ledger**. Output:
  live biotech ticker set. Validate against `universe_data` (124) + the 50 seeds.
- **B. Asset detection + lead ranking (CT.gov only).** Sponsor search → cluster →
  rank → provisional seed + confidence. **Backtest vs the 50 seeds** (precision/recall
  of lead/indication/stage/modality recovery). This alone likely derives most seeds.
- **C. Tiering + routing.** Thresholds → auto-add (write `seeds_auto.yaml`, consumed by
  `bve-profile build --missing`) / propose (review queue) / exception. Reuse
  `review_queue` + `review_writeback` (`resolve --approve` promotes a proposed seed).
- **D. Enrichment.** FDA designations + SEC structured facts improve ranking + liveness.
- **E. LLM extraction.** 10-K Item 1 + pipeline pages + PRs for lead confirmation,
  modality, and **encumbrance**, with citations, feeding the conflict detector.
- **F. Continuous operation.** Scheduled weekly discovery; **diff** vs current registry
  (new listings, newly-acquired→exclude, phase advances→re-tier); deltas → review queue.
  Re-verify auto-added seeds periodically (ties into the freshness follow-up).

## Reuse map

**Exists:** `ops/universe_builder.py`, `intelligence/exclusions/*` (acquired/delisted/
shell rules), `ingestion/clinicaltrials_gov.search_studies(sponsor=)`, `ingestion/
fda_client`, `ingestion/sec_edgar`, `normalization/normalizer.py`, `research/universe/
company_aliases.yaml`, the seed model `UniverseRegistryEntry`, and the entire
downstream pipeline (ProfileBuilder → … → review_queue/writeback).

**New:** ETF/SIC universe enumerator; asset clusterer (trials→programs); lead-asset
ranker + confidence; proposed-seed store + `seeds_auto.yaml`; discovery CLI
(`bve-discover run|backtest|propose`); new review reason codes
(`proposed_seed`, `multiple_lead_candidates`, `uncertain_encumbrance`).

## Validation gates & risks

- **Gate:** auto-add disabled until backtest precision on the 50 known seeds clears a
  bar; until then everything routes to *propose* (review). Recall can ramp later.
- **Negative universe:** the exclusion ledger is first-class + persistent so acquired/
  dead names are not re-proposed each run.
- **Compliance:** SEC fair-access (declared User-Agent, rate limits); ETF/pipeline-page
  scraping subject to ToS — prefer official holdings files / APIs.
- **Coarse-until-reviewed** stays invariant: discovery changes *who's covered*, never
  the honesty of *how* they're valued.
```
