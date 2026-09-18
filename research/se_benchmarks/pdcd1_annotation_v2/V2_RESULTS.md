# V2 adjudication results

Protocol `ANNOTATION_PROTOCOL_V2.md` (sha256 `a1743ace…`) was frozen and published before
any subject entry was researched. V1 rules, V1 outputs and M8 v2 are unchanged.

## Reported figures

| figure | identified | denominator | recall |
|---|---|---|---|
| strict M8 recall (permanent n=224) | 80 | 224 | 35.7% |
| V1 confirmed PDCD1 asset recall | 25 | 28 | 89.3% |
| V2 confirmed PDCD1 asset recall | 35 | 40 | 87.5% |
| reachable V2 confirmed PDCD1 asset recall | 35 | 40 | 87.5% |

Residual uncertainty interval: **[71.4%, 87.5%]**, from [48.7%, 89.3%] before V2.
Still `UNCERTAIN_V2`: 9 of the 48.

The reachable figure equals the unrestricted figure: the as-of cutoff costs zero confirmed
PDCD1 assets, as it did in V1.

## A/B agreement and reconciliation

| basis | n |
|---|---|
| AGREE (identical verdict) | 40 |
| SINGLE_ADJUDICATOR_EVIDENCE | 8 |
| CONFLICT_UNRESOLVED | 0 |

No entry produced a PDCD1_MATCH vs NON_PDCD1 conflict. All 8 splits were one adjudicator
finding an admissible source where the other found none.

Five of those 8 were then downgraded to `UNCERTAIN_V2` by the admissibility audit, which
applies only clauses already frozen in the protocol:

| entry | was | clause |
|---|---|---|
| ABP 206 (Amgen nivolumab biosimilar) | PDCD1_MATCH | V2.5+V2.2 — reference relationship rested on a CT.gov record stating no target |
| BCD-263 (Biocad nivolumab biosimilar) | PDCD1_MATCH | same |
| BCD-263 (Biocad nivolumab/OPDIVO biosimilar) | PDCD1_MATCH | same |
| Tumor-associated antigen cancer vaccine (EVM14) | NON_PDCD1 | V2.2 — cited a press-wire domain, inadmissible at any rank |
| DHP107 (oral paclitaxel, Liporaxel) | NON_PDCD1 | V2.3 — excerpt named the active moiety but stated no target |

## Source rank breakdown (resolved entries)

| rank | source class | n |
|---|---|---|
| 1 | regulator (FDA label / approval) | 2 |
| 2 | official company pipeline/product page | 16 |
| 3 | company filings | 0 |
| 4 | primary publication | 19 |
| 5 | ClinicalTrials.gov stating a mechanism | 2 |

**Resolved solely by CT.gov rank 5 — 2 entries**, both `NON_PDCD1`, so neither enters the
PDCD1 numerator or denominator and neither can inflate the headline recall:
ABO2109 (personalized mRNA cancer vaccine); Autologous TIL therapy (GC101).

## Track A vs Track B

| track | PDCD1_MATCH | NON_PDCD1 | UNCERTAIN_V2 | total |
|---|---|---|---|---|
| A | 12 | 24 | 2 | 38 |
| B | 0 | 3 | 7 | 10 |

Track A resolved 36/38. Track B resolved 3/10 — the modality-specific rules held, and
declining to auto-classify Track B as out-of-scope cost 7 unresolved entries rather than
hiding them. All 3 biosimilar candidates remain `UNCERTAIN_V2` because no admissible source
established the reference-product relationship; they are the clearest remaining target for a
future protocol, since a regulatory filing would settle all three.

## Note on the 12 new PDCD1 assets

The V2 additions are dominated by ivonescimab (4 alias presentations), IBI363/TAK-928
(2 presentations), JS207, GB268, ezabenlimab, Opdualag and subcutaneous pembrolizumab.
Several are PD-1-containing bispecifics that a mechanism-of-action database records under a
partner target or not at all -- which is exactly why V1 left them uncertain.

Pumitamig (BNT327/BMS-986545) resolved `NON_PDCD1`: both adjudicators independently found
the sponsor describing it as PD-L1xVEGF-A. Under the frozen rule PD-L1 is not PDCD1.
