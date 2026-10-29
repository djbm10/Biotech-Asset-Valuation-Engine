# Workflow C2 log (DealScreen after fixes) — AI-SIMULATED, INTERNAL DEVELOPMENT

Analyst: AI assistant (reviewer id `ai-assistant-C2`, kind AI_PREPARED). No human steps were taken:
finalist approval, finding confirmation, identity-flag resolution are NOT COMPLETED BY HUMAN.
Tool calls: ~31 (Bash + 3 WebSearch + 1 ToolSearch). Workspace: `~/.cache/compare_C2/` (TMPDIR=~/.cache/dealscreen_suite).
Forbidden paths: none accessed; no accidental exposure.

## Commands (B=.venv/bin, I=research/dealscreen_comparison_v1/inputs)
```
# buyer copy with documented transaction block (frozen input untouched): buyer_with_transaction.yaml
B/bve-dealscreen import --workspace ws --landscape I/landscape_cldn18.csv --profile I/profile_cldn18.yaml --buyer buyer_with_transaction.yaml --identity-authority
B/bve-dealscreen screen --workspace ws                     # AS INSTALLED: 0 eligible / 41 unresolved / 21 excluded
B/bve-dealscreen research --workspace ws --provider offline:I/evidence_library.json --unresolved   # 27 proposals, no target ones
cp -r ws ws_tmap
B/bve-dealscreen screen --workspace ws_tmap --target-map target_map_cldn18.yaml   # 14 / 22 / 26
B/bve-dealscreen research --workspace ws_tmap --target-map target_map_cldn18.yaml --provider offline:... --unresolved  # +2
B/bve-dealscreen propose ... (7 attempts: 5 recorded, 4 refused; see below)
B/bve-dealscreen decide --action APPROVE_FINALIST --new-state APPROVED --reviewer-kind AI_PREPARED   # REFUSED (correct)
B/bve-dealscreen decide --action SELECT_FOR_VALUATION ...                                           # REFUSED (correct)
B/bve-dealscreen decide --action APPROVE_FINALIST --new-state CANDIDATE_NOT_APPROVED --reviewer-kind AI_PREPARED  x10
B/bve-dealscreen value-config --workspace ws_tmap --asset CL-16|CL-24|CL-27 --assumptions valuation_assumptions_C2.yaml [--deal acquisition|license] --out vc/...
B/bve-dealscreen-value --config vc/X.yaml --output-json out/X.json --n-sims 2000 --seed 42   (x9)
B/bve-dealscreen export --workspace ws_tmap --out dealscreen_C2_targetmap.xlsx ; memo --out bd_memo_C2.md
B/bve-dealscreen export --workspace ws --out dealscreen_C2_as_installed.xlsx
```

## Declared transaction block (and why)
`marketed: exclude` ("we do not want an already-marketed product"); `encumbered_rights: deprioritize`
(licensed/optioned = not available unless returned); `deprioritized_holders`: AstraZeneca, Astellas, Merck, MSD, Takeda,
Bristol-Myers Squibb / Bristol Myers Squibb, AbbVie, Amgen, Eli Lilly, Roche, Pfizer, Novartis, Sanofi, GSK,
Johnson & Johnson, BioNTech, Jazz Pharmaceuticals ("U.S. rights held by a large pharmaceutical company is not attractive
unless returned"). My judgment of "large pharma"; Merck KGaA is caught by "Merck".

## Workaround (one, significant)
As installed, the S&E ontology did not resolve vendor target text "Claudin 18.2" to CLDN18, so **every program's target
gate was UNKNOWN: 0 eligible**. I used the documented `--target-map` option with an AI-prepared synonym map
(`target_map_cldn18.yaml`: Claudin 18.2→CLDN18 plus HER2, CD3, 4-1BB, CD47, PD-L1, PD-1, TIGIT, CTLA-4, MUC1). This is an
analyst configuration that a human should review; the as-installed workbook is also delivered. Note `export` does not accept
`--target-map` (it reads the last screen), which is fine but inconsistent.

## What the tool did well
- Row accounting, raw rows kept, identity SHARED_CODE flags caught AZD0901/CMG901/sonesitatug, XNW27011/ASP546C, zolbetuximab/IMAB362 (not merged).
- Excluded CAR-T/CAR-NK, naked mAbs, non-CLDN18.2 bispecifics (FG-B901, RC148, rilvegostomig, zanidatamab...) correctly once targets resolved.
- Never asserted availability; zolbetuximab EXCLUDED_BY_BUYER_PREFERENCE (marketed); AZ/Astellas programs DEPRIORITIZED.
- Refused AI approval and AI valuation selection; refused rights proposals whose quote did not state the status.
- value-config + bve-dealscreen-value made valuation fully reproducible from saved configs.

## What the tool did badly / misleading
- Target resolution failure (above) is the dominant defect: as installed the screen is useless on this landscape.
- Indication gate: 18 IN-type programs left UNRESOLVED because registry indications (e.g. "solid tumors", "gastric cancer") lack positive compatibility (RC118, givastomig, AZD5863, VBC108, AMG 910...).
- Vendor modality errors propagate: IBI343 ("Imaging agent") UNRESOLVED, LCB02A ("Monoclonal antibody", actually ADC platform) EXCLUDED; ISAC BDC-4182 EXCLUDED as mAb. Proposals to correct modality sit unconfirmed.
- TAC01-CLDN18.2 (cell therapy) and imaging agents CL-61/62 UNRESOLVED instead of OUT (blank modality/phase).
- Transaction tier OPEN for SHR-A1904 (Merck KGaA option) and LM-302 is ranked #1 OPEN: the offline research found the rights sentences but they stay proposals, so the tier ignores them until a human confirms. A reader of the memo's "#1 LM-302 OPEN" could over-read it.
- Rights-statement recogniser refused "handed back rights" (until value text changed to "rights returned" — value wording, not the quote, changed the outcome), "shares worldwide rights", and a truncated Takeda license sentence.
- Preference rank puts Phase 3 bispecific QLS31905 above ADCs; capability (ADC) is only the 5th tie-breaker.

## Could not determine
- U.S. rights holders for JS107, BL-M05D1, QLS31905, VBC108, TQB2103, DA-3501, AK132, SG1906 (no deal found; holder assumed originator); whether any owner is seeking a partner (no evidence of availability for ANY program).
- ATG-022 true phase (vendor Ph3 vs reported Ph2 expansion); nature of MSD links (ATG-022, spevatamig) — likely clinical collaborations.
- Whether ANO31905 = QLS31905; whether LCB02A has human data yet; Bio-008 identity.
- SKB315 return of rights: from search-result summary (Fierce/Citeline), verbatim quote not captured.
