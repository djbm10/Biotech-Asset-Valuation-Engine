# Milestone 6 - Build A vs Build B Frozen Row Identity Mapping Comparison

Build A rows: `300`
Build B rows: `300`
Row outcome agreement: `300/300` (100.0%).
Disagreements: `0`, enumerated in `reconciliation_ledger.jsonl`.

Both builds read the same frozen M1-M5 inputs. Build B reverses input ordering and writes its own complete ledger set; Build A remains the published row mapping.
