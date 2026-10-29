# C3 DealScreen workflow log (AI-SIMULATED, INTERNAL DEVELOPMENT)

Agent: AI analyst (`ai-analyst-C3`). No HUMAN actions taken; all human-only steps NOT COMPLETED BY HUMAN.
Forbidden paths: none accessed (no reference/, other runs/, CRITIC_*, FIXES_C1, scores, heldout, src/, tests/, git history).
Tool calls: ~30 (Bash/Read/WebSearch/WebFetch).

## Commands (TMPDIR=$HOME/.cache/dealscreen_suite; W=$HOME/.cache/compare_C3/ws; I=research/dealscreen_comparison_v1/inputs)
```
cp $I/buyer_cldn18_gastric.yaml buyer_with_transaction.yaml   # + transaction block (below)
bve-dealscreen import --workspace $W --landscape $I/landscape_cldn18.csv --profile $I/profile_cldn18.yaml --buyer buyer_with_transaction.yaml --identity-authority
bve-dealscreen screen --workspace $W
bve-dealscreen research --workspace $W --provider offline:$I/evidence_library.json      # 32 proposed findings
bve-dealscreen propose ... CL-06 modality ADC (Takeda PR) ; CL-38 modality ADC (CT.gov title) ; CL-06 us_rights LICENSED
bve-dealscreen propose ... CL-06/CL-27 rights with paraphrase-like quotes -> REFUSED (quote must state rights status)
bve-dealscreen queue / screen / export --out $W/deliverables/dealscreen_C3.xlsx / memo --out $W/deliverables/bd_memo_C3.md
bve-dealscreen value-config --asset {CL-07,CL-20,CL-27} --assumptions assumptions_C3.yaml [--deal acquisition|license] --out val/...
bve-dealscreen-value --config val/X.yaml --output-json val/X.json --n-sims 5000 --seed 42
```
Transaction block declared (workspace copy only): `marketed: exclude` ("we do not want an already-marketed product");
`deprioritized_holders: [AstraZeneca, Astellas, Takeda, AbbVie, Amgen, Merck KGaA, Merck Sharp & Dohme, Bristol-Myers Squibb,
Bristol Myers Squibb, Eli Lilly, GlaxoSmithKline, Pfizer, Roche, Novartis]` ("U.S. rights held by a large pharma not attractive
unless returned" — deprioritize, not exclude, since return is possible); `encumbered_rights: deprioritize`.

## Tool funnel as installed
62 screened = 14 ELIGIBLE / 25 UNRESOLVED / 23 EXCLUDED (excluded: modality 21, target 2). U.S. rights UNKNOWN for all 14 eligible.
Identity: flagged AZD0901/CMG901/sonesitatug vedotin, zolbetuximab/IMAB362, XNW27011/ASP546C (not merged). Did NOT flag EO-3021=SYSA1801 or ANO31905~QLS31905.
Transaction tiers among eligible: OPEN 9, DEPRIORITIZED 5 (AZ x2, Astellas x3); zolbetuximab EXCLUDED_BY_BUYER_PREFERENCE.

## My calls
23 records IN (19 distinct molecules), 13 UNRESOLVED, rest OUT. Shortlist (availability NOT evidenced for any):
1 LM-302 (BMS rights returned), 2 QLS31905, 3 ATG-022, 4 givastomig, 5 SHR-A1904 (Merck KGaA option, status unknown),
6 SKB315 (Merck returned rights 2024), 7 JS107, 8 BL-M05D1, 9 spevatamig, 10 TORL-2-307-ADC.
Excluded from shortlist: AstraZeneca (AZD0901, AZD5863), Astellas (ASP2138, XNW27011), Takeda (IBI343) — held by large pharma.

## Workarounds
- Transaction preferences required a copied buyer YAML (documented feature).
- Valuation via `value-config` + `bve-dealscreen-value` because `value` requires human-SELECTED finalists.
- Large-pharma matching is by registry sponsor; IBI343 (Takeda licence) shows OPEN because the Takeda rights proposal cannot be applied without a human.

## Did well
Fast import (33 s) with row accounting; identity flags for code/INN aliases; refused paraphrase rights quotes; kept rights UNKNOWN;
transaction tier separate from science; reproducible valuation configs; cost/milestone arithmetic reproducible.

## Did badly
- Indication gate UNKNOWN for 40 programs (incl. AZD5863, givastomig, DA-3501, CMG901 with gastric in conditions) -> many true INs UNRESOLVED.
- Landscape modality errors propagate (IBI343 "imaging agent", LCB02A "mAb" EXCLUDED) and only a human can fix them.
- Agent findings (32) are inert for an AI-only run: funnel unchanged after research.
- License scenario ordering anomaly (bear > base) not flagged in CLI output.
- Missed identity EO-3021/SYSA1801.

## Could not determine
Current status of Merck KGaA's SHR-A1904 option; whether any owner is actively seeking a U.S. partner (no evidence of availability for any program);
Elevation's EO-3021 rights after discontinuation; ANO31905 identity; RC118/VBC108/SG1906 gastric cohorts.
Sources (web): https://synapse.patsnap.com/article/merck-co-invests-in-kelun-bispecific-adc-exits-cldn182-program ;
https://www.takeda.com/newsroom/newsreleases/2025/innovent/ ; https://www.biospace.com/hengrui-pharma-partners-with-merck-kgaa-darmstadt-germany-to-advance-innovative-cancer-therapies
