# Hand-Labeled Extraction Fixtures

These fixtures contain real-world biotech documents with manually verified
expected extraction outputs.

## Schema

Each fixture is a JSON object with:

- `fixture_id` — unique identifier
- `description` — brief description of the document
- `source_citation` — original source reference
- `labeled_by` — analyst identifier
- `labeled_at` — labeling date (ISO)
- `notes` — context and caveats
- `raw_document` — full `RawDocument` JSON
- `expected` — manually verified expected signal fields
- `tolerance` — per-field numeric tolerances for approximate matching

## Files

| Fixture | Event Type | Date | Asset |
|---------|-----------|------|-------|
| `dupilumab_ad_approval_2017.json` | fda_approval | 2017-03-28 | dupilumab (REGN) |
| `sotorasib_phase2_readout_2021.json` | publication | 2021-06-01 | sotorasib (AMGN) |

## Adding New Fixtures

1. Select a real-world document with a clear, unambiguous event.
2. Copy the document text verbatim (do not paraphrase).
3. Manually determine the expected field values — do not use LLM output as ground truth.
4. Set `labeled_by` to your analyst ID and `labeled_at` to today's date.
5. Add to the fixture table above.
6. Run `pytest tests/intelligence/extraction/test_eval_harness.py` to verify.
