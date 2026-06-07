# Live Scanner Path Explainer

**Date:** 2026-06-04
**Scope:** Watchlist ingestion, signal extraction, valuation updates, ranking, and M&A scanner interaction
**Main files:** `src/bve/pipeline/watchlist_runner.py`, `src/bve/intelligence/ranking.py`, `src/bve/intelligence/ma_probability.py`, `src/bve/intelligence/weekly_ma_screen.py`

## Short Version

The live scanner is the tool's operating dashboard. It watches configured assets,
pulls new documents from configured sources, extracts structured signals, decides
whether the signal is safe to use, maps eligible signals into model changes,
reruns valuation when allowed, and then ranks assets from the latest stored
valuation diffs and signals.

It currently supports live-style refresh and reranking, but it is not yet a fully
autonomous news interpreter. New information changes the score only if it makes
it through this chain:

```text
source document
  -> fetched by connector
  -> deduped and stored
  -> extracted into StructuredSignal
  -> passes confidence gate
  -> passes valuation trigger gate
  -> mapped into assumption-change proposals
  -> auto-approved values applied
  -> valuation diff stored
  -> ranking engine reads latest diff + signal + market cap
  -> ranked output updates
```

If a document is low confidence, ambiguous, not mapped, or review-required, it
may be stored for audit but not immediately change the live score.

---

# 1. What The Live Scanner Watches

The scanner runs from a watchlist config. Each watchlist asset can include:

- company ID,
- asset ID,
- drug name,
- indication,
- ticker,
- ClinicalTrials.gov NCT ID,
- valuation config path,
- connector list,
- market cap override,
- ranking overrides.

The active connector set is configured per run. The runner has built-in support
for source connectors such as:

| Source type | What it can contribute |
|---|---|
| ClinicalTrials.gov | trial status, enrollment/status changes, NCT-linked updates |
| FDA | regulatory events, approvals, holds, designations, safety/regulatory actions |
| SEC EDGAR | 8-Ks, 10-Qs, 10-Ks, financing, business updates, trial disclosures |
| Press releases | company-published trial, regulatory, partnership, and corporate updates |
| Market prices | market cap snapshots, price reaction tracking, volume anomaly context |

The scanner does not automatically know every biotech company or every article on
the internet. It watches the configured universe and configured connectors.

---

# 2. How A News Item Enters The System

The watchlist runner fetches documents per asset and connector.

For each fetched document, it:

1. normalizes the document into a `RawDocument`,
2. assigns entity hints such as asset, company, ticker, drug, indication, and NCT ID,
3. stores the raw document in the knowledge store,
4. deduplicates already-seen documents, duplicate hashes, duplicate events, and recent similar titles,
5. sends eligible documents to the extractor.

Deduplication matters because company press releases and filings can repeat the
same event in several places. The scanner tries not to count the same real-world
event multiple times.

---

# 3. How The Tool Interprets The News

The extractor tries to convert a raw document into an `ExtractionResult` and a
`StructuredSignal`.

`StructuredSignal` is the important object. It turns text into typed facts such
as:

| Signal field | Example |
|---|---|
| `event_type` | `trial_readout`, `fda_decision`, `safety_signal`, `partnership`, `financing` |
| `trial_phase` | Phase 1, Phase 2, Phase 3, NDA/BLA |
| `primary_endpoint_met` | true / false / unknown |
| `primary_endpoint` | PFS, OS, ORR, HbA1c, eGFR slope, etc. |
| `hazard_ratio`, `p_value`, `response_rate` | extracted efficacy facts |
| `safety_grade` | highest reported safety severity |
| `fda_action_type` | approval, CRL, hold, designation |
| `designation_type` | BTD, FTD, ODD, RMAT |
| `deal_value_millions`, `deal_type` | partnership or licensing economics |
| `extraction_confidence` | model confidence in the extracted signal |

Current extractor backends can be fake/test, Anthropic, or OpenAI depending on
config. The runner also has a daily LLM cost guard and per-asset document cap.

---

# 4. Confidence Gates

The scanner does not let every extracted signal touch the model.

There are two extraction confidence thresholds:

| Gate | Default behavior |
|---|---|
| Below discard threshold | Store extraction for audit, but discard from live processing. |
| Below review threshold | Store and flag for review, but do not send to valuation. |
| Above review threshold | Store structured signal, create event, and queue for valuation checks. |

This is why the scanner may ingest a news item but not immediately rescore the
asset. The system is deliberately conservative when extraction confidence is low.

---

# 5. Valuation Trigger Gate

After a signal is accepted, it still must pass the valuation trigger gate.

Default valuation-trigger event types are:

```text
trial_readout
fda_decision
safety_signal
```

The signal must also meet the configured minimum confidence score.

That means a partnership, financing, management change, or ordinary publication
may be stored and useful for M&A or memo context, but it will not necessarily
rerun the single-asset valuation unless the configuration says it should.

---

# 6. Mapping News Into Model Changes

When a signal passes the valuation gate, the `MappingEngine` maps it into
assumption-change proposals.

Conceptually:

```text
StructuredSignal
  -> MappingEngine
  -> AssumptionChangeProposal[]
  -> ReviewQueue route
  -> effective auto-approved values
  -> ValuationSession.apply_proposals()
  -> StoredValuationDiff
```

Examples:

| News signal | Possible model effect |
|---|---|
| Positive Phase 2 readout | prior-phase evidence improves; POS and rNPV can rise |
| Failed primary endpoint | prior-phase evidence worsens; POS and rNPV can fall |
| Safety signal | safety profile worsens; POS and rNPV can fall |
| FDA approval | stage/status improves; approval probability and commercial timing can change |
| CRL or clinical hold | regulatory risk rises; timing, cost, POS, and rNPV can worsen |

Important nuance: not every proposal auto-applies. Review-required proposals are
deferred and logged for manual review. The live score changes only from effective
values that the queue allows through.

---

# 7. How Reranking Works

The ranking engine does not refetch news or call an LLM. It reads the database.

Specifically, it reads:

- latest valuation diffs,
- structured signals linked to those diffs,
- market cap snapshots or latest stored market prices,
- catalyst events,
- model POS and implied market POS when available.

The current asset ranking score is:

```text
score =
    valuation_component * 0.50
  + confidence_component * 0.25
  + recency_component * 0.15
  + event_type_component * 0.10
```

Where:

| Component | Meaning |
|---|---|
| `valuation_component` | mispricing between model rNPV and market cap, or valuation-delta proxy |
| `confidence_component` | extraction confidence, optionally calibration-scaled |
| `recency_component` | newer events score higher; half-life default is 14 days |
| `event_type_component` | high-impact event types such as approvals, safety signals, trial readouts, and holds get higher priority |

Upcoming catalysts within 60 days can boost the final rank score.

So a news item changes rank only if it creates a stored valuation diff or relevant
stored signal that the ranking engine can read.

---

# 8. How News Changes The Score: Examples

## Positive Phase 2 Readout

```text
press release says Phase 2 met primary endpoint
  -> extractor identifies trial_readout
  -> signal confidence passes gate
  -> MappingEngine proposes stronger clinical assumptions
  -> valuation reruns
  -> rNPV increases
  -> valuation diff stored
  -> ranking sees higher model value, high event priority, high recency
  -> asset moves up the ranked watchlist
```

## FDA Clinical Hold

```text
FDA hold disclosed in 8-K
  -> extractor identifies fda_decision or safety/regulatory signal
  -> mapping proposes worse regulatory/safety assumptions
  -> valuation reruns
  -> rNPV decreases
  -> ranking may still show the event as high-priority, but valuation component worsens
  -> asset may move down or be flagged for urgent review
```

## Partnership Deal

```text
company announces licensing partnership
  -> extractor identifies partnership
  -> signal stored
  -> may not trigger valuation by default
  -> may still matter for M&A/BD context:
       seller openness, existing partner, rights encumbrance, validation signal
  -> deeper BD layers need structured M&A mapping to convert this into score changes
```

## Financing Stress

```text
company files financing / going-concern disclosure
  -> extractor identifies financing or SEC filing
  -> current valuation path may not auto-rerun
  -> M&A logic can use it as transaction pressure or distress context
  -> stronger future mapping should update Layer 0F / Layer 1 transaction setup / Layer 2 momentum
```

---

# 9. How This Relates To The M&A Scanner

There are two scoring concepts that often get confused.

## Live asset ranking

This is the fast operational ranking from `ranking.py`. It mainly asks:

```text
Which tracked asset has the most interesting recent valuation-changing signal?
```

It is driven by valuation diffs, signal confidence, recency, event type, market
cap, and catalysts.

## M&A scanner / BD ranking

This asks:

```text
Which targets are attractive and realistic M&A opportunities?
```

It uses M&A-specific concepts such as:

- target eligibility,
- asset attractiveness,
- strategic scarcity,
- financing pressure,
- buyer fit,
- affordability,
- rights and encumbrances,
- integration complexity,
- antitrust,
- seller willingness,
- calibrated transaction probability.

The live scanner can feed the M&A scanner when new documents change those M&A
inputs. But today, not every news type has a complete automatic mapping into the
institutional M&A layers.

---

# 10. What Is Implemented Today

Implemented:

- configured watchlist ingestion,
- connector fetching,
- raw document storage,
- deduplication,
- LLM/fake extraction backend support,
- confidence gating,
- structured signal storage,
- event creation,
- mapping into assumption-change proposals,
- review queue routing,
- valuation diff persistence,
- market price refresh,
- price reaction tracking,
- ranking from stored valuation diffs and signals,
- weekly M&A screen and M&A probability modules.

Partly implemented / needs strengthening:

- broad free-text biotech news interpretation,
- automatic M&A-layer updates from all relevant news types,
- source conflict resolution when filings and press releases disagree,
- score-change attribution that explains exactly why a rank moved,
- auto-vs-review policy by event type and field,
- point-in-time replay validation for news-to-score movement.

---

# 11. Practical Mental Model

Use this distinction:

```text
Live scanner path = "What changed recently, and how should the watchlist rerank?"

Institutional BD path = "If this is interesting, is the deal thesis real, who can
buy it, and what structure makes sense?"
```

The live scanner is the alerting and reranking layer. The BD path is the
underwriting and action layer.

The long-term goal is for the live scanner to feed the BD path automatically:

```text
new event
  -> update valuation / POS / M&A inputs
  -> rerank watchlist
  -> rerun BD route
  -> show explanation and confidence
  -> queue human review where judgment is required
```

