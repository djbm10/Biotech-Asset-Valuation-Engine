# Workflow A log (AI-SIMULATED / INTERNAL DEVELOPMENT)

- Tool calls: ~19 total (Bash 9, Read 1, Write 1, ToolSearch 1, WebSearch 9 [incl. retries], no WebFetch).
- Read: PROTOCOL.md, SOP_SPREADSHEET.md, inputs/* (landscape, buyer, profile, hypothetical market inputs; evidence_library.json only its structure — it mirrors public_evidence.json), sources/public_evidence.json (all items). Did not open ctgov or openFDA snapshots in detail (relied on landscape cells + curated quotes). Forbidden folders (reference/, other runs/, src/, tests/, docs/) not opened. The workspace system context listed repo memory notes mentioning DealScreen work generally; nothing CLDN18-specific from reference was seen.
- Web searches: LM-302 rights; JS107; ATG-022; SKB315/Merck return; SHR-A1904 option; BL-M05D1; TORL-2-307; QLS31905; ANO31905/Anova; spevatamig/Phanes.
- Built `workbook.xlsx` with openpyxl via `build_workbook.py` (copy kept here): Tracker (62 rows + SOP columns, autofilter), Rights (29 IN rows), Shortlist (10), Val_CL-07/CL-16/CL-27 with Excel formulas. No Excel/LibreOffice available, so formulas were not recalculated; numbers in valuation.md come from a Python mirror and hand-checked worked examples.

## Manual workarounds
- Landscape modality errors corrected by judgement (IBI343 = ADC, LCB02A = ADC, BDC-4182 = ISAC).
- Identity groups assigned by hand from alias columns and NCIt aliases.
- Several web quotes come from search-result summaries, not fetched pages (CL-16, CL-27, CL-29, CL-31 evidence) — critic should verify these quotes verbatim.

## Hard / undetermined
- Availability: no source states any program is actively offered, so nothing is EVIDENCED_AVAILABLE. Kelun's "exploring ... international markets" is the closest.
- Unknown: Merck KGaA option exercise on SHR-A1904; JS107 and BL-M05D1 ex-China rights; whether ANO31905 = QLS31905; Bio-008 target; AZD5863 licence terms (Harbour BioMed) not sourced.
- Indication fit for solid-tumour-basket programs (RC118, LCB02A, Q-1802, TQB2103, SG1906, VBC108, AK132) assumed acceptable (CLDN18.2 is mainly gastric/pancreatic) — marked "?".
- Human sign-off: NOT COMPLETED BY HUMAN.
