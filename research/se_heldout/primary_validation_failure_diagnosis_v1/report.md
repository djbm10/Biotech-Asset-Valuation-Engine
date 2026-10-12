# PRIMARY_VALIDATION_FAILURE_DIAGNOSIS v1

**Status: DIAGNOSIS ONLY — frozen against H16–H20 primary-validation artifacts.**

Frozen engine: `5feee853c8a15d8c92ef632f82a07c32e1d0e038`. Labels committed before scoring at
`eed63eb7dd5c3ea4387a2b9789c6d886229bbaf5`; primary result committed at `ab0f02b`.
The primary result remains **FAIL, 0/5**. No label, query, rubric, threshold, score, or original
run artifact is changed by this diagnosis. Original interrupted H17/H18 directories remain
excluded. H6–H10 remain UNRUN. No live search, corpus replay, query rephrasing, parser using an
alternate query spelling, implementation, or engine-code change was performed.

All observations use saved result bytes, original source snapshots, the pinned ontology, and
the frozen code. Offline probes invoke narrow existing functions on original query text or
original evidence; they do not run the search engine. The 66-entry first-failure register
covers all 60 emitted top20 rows, both refusals, the three missing H19 reference products,
and H16's reference outside the top20. Relevant control rows are marked NONE rather than
assigned an invented failure. Where an upstream component correctly abstains, the register
distinguishes missing evidence from a false scientific assertion.

Evidence packet: `research/se_heldout/primary_validation_failure_diagnosis_v1/`.

## 1. Highest priority: false human-PoC (H18, H19)

**The frozen labels are not overturned. Both false claims reproduce on the exact saved
source text. Neither failure is an identity merge attaching another product's fact. The
named product is present; the extractor misreads what the sentence's number establishes.**

| Query/product | Claim and source | What was reported | What the extractor accepts | First scientific failure boundary |
|---|---|---|---|---|
| H18 Tirzepatide | `claim:9954996062248331a551`; PubMed 41852165, “Mitochondrial Adaptations in Skeletal Muscle Following Incretin-Based Therapies: In Vitro.” | Respiration in human myotubes, including changes for semaglutide/cagrilintide and tirzepatide | endpoint `response`; human cue `human`; first percent token `219330%` in raw JSON text | Prose efficacy admissibility: human-derived cells and an assay response are treated as human-patient efficacy; the number is not bound to this product's clinical endpoint |
| H19 Sacituzumab Tirumotecan | `claim:6c5b35e2a5871015f940`; PubMed 41790608, cost-effectiveness analysis | A partitioned survival model simulating patients over ten years; annual discount rate 5% | endpoint `survival`; human cue `patient`; number `5%` | Prose efficacy admissibility: model/design/economic quantities are treated as numerical observed clinical efficacy |

Both claims use `reported_efficacy_sentence`, extractor `human_poc_v4`, and become
`human_poc_present=True` with MACHINE_VERIFIED claims. No structured clinical-result route
produced these particular citations.

The precise acceptance chain in `evidence/human_poc.py:385–430` is:

1. The sentence names the asset and is shorter than 400 characters (H18 294; H19 351).
2. A broad efficacy substring matches: `response` in “responses”, or `survival` in the model name.
3. The sentence has a human cue: `human` includes human myotubes; `patient` includes simulated patients.
4. A percentage exists somewhere in the sentence. No requirement binds it to a patient benefit,
   the named product, or the matched endpoint.
5. Existing nonhuman and unreported veto vocabularies do not match `human myotubes`,
   `partitioned survival model`, `simulate`, or `discount rate` in these sentences.
6. `human_poc_evidence()` then turns the admitted statement into a direct-observation claim
   and a True fact. Source-capability admission of publication abstracts does not classify
   the study as clinical versus preclinical or economic modeling.

H18 additionally exposes a representation defect. `snapshot_cache.load_text()` reads the
raw serialized JSON file, not its parsed abstract. The original abstract contains a ↓ arrow;
its JSON spelling `\u2193` is adjacent to `30%`, so `_VALUE` returns `219330%`. Probing the
parsed original abstract instead returns `30%` **and still accepts the false human-PoC**.
Therefore decoding alone would not resolve the scientific failure. Moreover that first
percentage describes semaglutide/cagrilintide respiration, whereas the claim is on
tirzepatide. The sentence-wide name/value test provides no product–endpoint–number binding.

H19's 5% is explicitly the discount rate, not a treatment effect. Its model can be informed
by a real clinical trial without this cited sentence constituting numerical human efficacy.
The diagnosis concerns the actual asserted evidence, not whether the product has efficacy
reported elsewhere.

Supported controls are preserved: H16 Relatlimab has a cited numerical patient-response
passage; H18 survodutide has numerical patient liver-fat-response proportions. The frozen
row-level definition remains unchanged.

**Recommended first implementation milestone: human-efficacy evidence admissibility and
numerical attribution.** It must distinguish treated people from human-derived material,
observed clinical outcomes from models/design/economic quantities, and a product's measured
benefit from unrelated numbers in the same sentence. This is a diagnosis recommendation,
not a preregistered design or an implementation. Scope/number decoding is a related defect
to address explicitly, rather than silently treating a decoding fix as a scientific fix.

## 2. Target recognition: H17 and H20, independent of indication

| Query | Exact frozen target phrase | Existing parser behavior | Pinned authority evidence | First failure |
|---|---|---|---|---|
| H17 | `IL-4Rα` | `anti-` is successfully blanked by `_strip_target_affixes`; remaining token is offered to the resolver; normalized key `il 4rα` is UNRESOLVED | IL4R exists; aliases include `IL-4R-alpha`, `IL-4RA`, `IL4RA`, and full “subunit alpha” names, but not a matching Greek-alpha key | Target alias/orthographic lookup coverage, not an affix-parser regression |
| H20 | `factor XI` | The two-word phrase is permitted by the parser's target n-gram limit and offered to the resolver; normalized key `factor xi` is UNRESOLVED | F11 exists; names include “Coagulation factor XI”, FXI and F11; shortened “factor XI” is absent | Target alias coverage, not inability to parse a two-word phrase |

`normalize_lookup_key()` casefolds, unifies hyphens/underscores/slashes, and collapses
whitespace. It does not transliterate Greek letters, concatenate a Greek alpha to an
English-alpha alias, or derive abbreviated multiword target names. The adopted affix fix
only handles the outer grammar. It cannot supply missing authority vocabulary.

Both original queries yield zero TARGET spans. `SearchIntent` reports “no biological target
recognized in the query” and the compiler refuses. Atopic dermatitis and thrombosis also
remain residual text, but that happens independently and is not the refusal boundary.
No alternate query, alternate full spelling, synonym live run, or indication experiment was
used. Refusal is the observed primary-validation result and remains query-level FAIL.

## 3. H19 candidate quality: separate boundaries

### 3a. Three NON_ASSET rows

| Position/name | Frozen evidence | First failure boundary | Later effect |
|---|---|---|---|
| 17 `[68Ga]Ga-TTP` | NCT06715020 explicitly describes a TROP2-targeted PET radiotracer for imaging/diagnostic validation, not therapeutic benefit | Asset qualification: structured DRUG typing plus an experimental-arm relationship is mistaken for a therapeutic-product role | `STRUCTURED_THERAPEUTIC`, `identity_valid` PASS; target fact can correctly identify TROP2 without establishing therapeutic status |
| 18 Rescue Medications | NCT07216703/NCT06132958: generic premedication category, with antihistamines, acetaminophen, steroid equivalents and supportive medications in its description | Asset qualification: experimental-arm DRUG declaration overrides absence of a distinct product identity | `STRUCTURED_THERAPEUTIC`, `identity_valid` PASS; target UNKNOWN; review inclusion |
| 19 Rescue Medication | NCT06841354: another generic premedication category, not one named molecular product | Same qualification boundary | `STRUCTURED_THERAPEUTIC`, `identity_valid` PASS; target UNKNOWN; review inclusion |

`registry.ingest()` records DRUG/BIOLOGICAL typing and experimental-arm therapeutic
observations. `qualification_reason()` accepts that combination through its
STRUCTURED_THERAPEUTIC route after existing vetoes. These rows pass that route. The registry
field's type and an arm's experimental status are insufficient evidence of distinct
therapeutic-product identity. The tracer's true TROP2 affinity does not repair its
nontherapeutic role. Generic medication buckets are neither fabricated molecules nor simply
two duplicate real drugs; their frozen NON_ASSET labels remain appropriate.

### 3b. Two duplicates

- Position 16 TRODELVY resolves to `DRUG:SACITUZUMAB GOVITECAN` through TRADE_NAME, but
  `resolve_identifier()` deliberately excludes trade names. It therefore cannot merge
  with position 2 through `consolidate_by_authority()`. This is the same identity-policy
  boundary as H18, not a new TROP2-specific problem.
- Positions 14/15 are the frozen same-product construct pair: the MD Anderson
  cord-blood-derived TROP2 CAR/IL15 TGFBR2KO NK construct, written with different word
  order and an iC9 mention in one name. Position 15 is DUPLICATE. It has no drug identifier
  resolution, no emitted synonym edge joining the two names, and no applied identity merge
  bridging them. First boundary: absence of a trusted construct-identity bridge; ranking
  receives two separate assets. This diagnosis does not authorize approximate text merging
  or infer that any two products sharing a target/construct class should merge.

### 3c. Three missing reference products: not one recall root cause

| Reference | Captured evidence/candidate state | First boundary | Why absent from Recall@all |
|---|---|---|---|
| Datopotamab deruxtecan | Found with canonical name and DS-1062/Dato-DXd aliases; qualifies; target gate PASS; candidate authority modality ADC with MATCH | **Structured modality extraction** | A `PEPTIDE` modality fact drives `modality.required` FAIL and EXCLUDED, so the product is outside the scored shortlist |
| ESG401 | Its name occurs in captured NCT06145308 `armGroups[].description` as one alternative therapy, but the intervention name is generic `TROP2 ADC`; no named ESG401 candidate or identity mention is emitted | **Candidate enumeration / structured-name boundary** | No named product representation reaches target attribution, qualification, identity, or ranking |
| BL-M02D1 | No matching candidate/mention, and no matching string in any of the 779 captured query-source snapshots | **Discovery/corpus coverage, exact upstream cause unresolved** | Product is absent before downstream processing; ranking cannot retrieve a product not represented in the captured evidence |

Datopotamab's incorrect modality is directly reproduced on the exact saved intervention
name+description+otherNames. `_candidate_interventions()` uses `QueryVocabulary.modality_in()`
to label text. It chooses the longest matching modality substring. `peptide` (7 characters)
matches the **tetrapeptide linker**, defeating `adc` (3 characters); even `trap` matches
inside “tetrapeptide” and illustrates the substring specificity problem. Extraction emits
`claim:2022030306a59db4acec` / `fact:71c28d48f9461eb004d3`, value PEPTIDE, confidence 0.95.
The gate evaluates that fact. `_with_authority_modality()` separately annotates the
candidate as ADC but deliberately does not write a modality_id fact. The two representations
therefore disagree and the incorrect structured fact wins the hard exclusion.

This is not an indication failure: datopotamab's indication decision is UNKNOWN under the
adopted conservative rule; its **only FAIL decision is modality.required**. It is also not
an identity alias-matching miss: the exact frozen reference names are present on the
excluded candidate. No changed threshold or expanded reference spelling is needed to see it.

ESG401 occurs in an arm description, not in the intervention name/otherNames that drive
observed primary-product enumeration. That gives a precise captured-evidence boundary;
it does not prove that blindly expanding every drug name in a regimen description is safe.

For BL-M02D1, all 779 captured query-source snapshots were examined. The result has 783
source-document records; four are synthetic ontology provenance records without snapshot
paths. An absence in the captured query corpus does not
prove global source absence or determine whether a connector, query, pagination, title filter,
or provider availability was decisive before capture. Six source families were unconfigured.
That limits diagnosis and was already disclosed; it does **not** invalidate the scored run.
No live search was used to fill that gap.

### 3d. Off-target real products in the top20

Positions 3–8 and 20 are real products with frozen WRONG_TARGET labels. Their query-target
gate is UNKNOWN, not a false PASS. The earliest unmet boundary is product-target evidence;
the review shortlist admits uncertainty. Positions 3–8 have authority modality MATCH, which
sorts ahead of target evidence under the existing lexicographic display policy. None of
these observations changes the public labels or establishes a scientific target assertion
that the engine did not actually make. Qualification of a real product and matching ADC
modality are insufficient to establish TROP2 relevance.

## 4. H18 duplicates: five instances of one identity-policy boundary

| Position | Emitted name | Public/pinned-resolver identity | Earlier row |
|---|---|---|---|
| 9 | Saxenda | Liraglutide | 7 |
| 11 | Victoza | Liraglutide | 7 |
| 12 | Ozempic | Semaglutide | 10 |
| 14 | Wegovy | Semaglutide | 10 |
| 20 | Rybelsus | Semaglutide | 10 |

Every name RESOLVES to the expected canonical drug, with matched alias type TRADE_NAME.
Every corresponding `resolve_identifier()` / `DrugModalityAuthority.identifies_drug()`
returns None. `_IDENTIFIER_ALIAS_TYPES` is explicitly restricted to APPROVED_NAME and
DEVELOPMENT_CODE. Consequently the authority merger never groups these brand-only records
with the active-product record. They survive as distinct assets and occupy separate ranks.

This is not lack of a public synonym in the ontology, a ranking tie bug, or discovery
failure. It is a deliberate safety boundary in identity consolidation, motivated by ambiguous
ordinary-word trade names and distinct biosimilars in the older policy. The diagnosis does
not authorize relaxing it wholesale. Source-backed brand equivalence and potentially
ambiguous aliases require a separately frozen design before any identity change.

H18's other independent failure is the Tirzepatide false human-PoC above. Its P@20 0.750,
Recall@all 1.000 and NON_ASSET 0 pass their thresholds; DUPLICATE 5 and false human-PoC 1 fail.

## 5. H16: exact threshold failure, not an indication or recall failure

The sole failing frozen criterion is **P@20 >= 0.70**: 10 RELEVANT / 20 judged = 0.500.
Recall@all is 6/6; Recall@20 is 5/6 and has no pass threshold; NON_ASSET, DUPLICATE and
false human-PoC are all zero. Target recognition is correct. INCOMPLETE source configuration
is not an additional scoring failure.

The ten remaining rows are real WRONG_TARGET products. Their target gates are UNKNOWN;
they are presented as review rows, not falsely target-confirmed products. They all have
authority modality MATCH. The sixth reference, encelimab/TSR-033, is present at **all-shortlist
position 541**, has target UNKNOWN and authority modality UNKNOWN, and is also in review.

An exact `_rank_key()` probe of the saved candidate/gate/fact state confirms that all ten
off-target top20 rows have modality sorting value 0 and TSR-033 has value 1. Existing display
order evaluates modality match before target evidence. A correct reference with missing
authority modality therefore loses to unrelated but authoritative antibody products.
The candidate's extracted CELL_THERAPY context label is separately weak and is not an
authoritative classification of TSR-033.

This explains why high overall recall coexists with insufficient top20 precision. H16
does not by itself demand a new biological/indication/identity semantic rule. Its frozen
failure concerns review-cohort presentation precision and incomplete product-evidence
coverage; deciding to change those requires a separately preregistered milestone, not
relabeling, excluding UNKNOWN rows after scoring, or weakening the threshold.

## 6. Independent causes, priority and stopping point

1. **First:** false scientific evidence — prose clinical-context admissibility and
   product/endpoint/number attribution, with the raw-JSON numeric corruption disclosed.
2. **Separate:** target-language alias coverage — Greek-alpha orthography and shortened
   protein naming; not indication semantics and not the adopted outer-affix fix.
3. **Separate H19 components:** experimental-arm/DRUG qualification overpromotion;
   modality extraction from an ADC linker; captured arm-description product enumeration;
   uncaptured BL-M02D1 coverage; unresolved product-target evidence in review.
4. **Separate identity components:** trade-name identifier policy shared by H18 and H19;
   missing construct identity bridge for the H19 cell-product pair.
5. **H16:** the P@20 threshold and modality-first review ordering; full recall is retained.

These are observations on now-exposed primary-validation data, not fresh generalization
evidence. Good recall and useful rows are recorded without claiming that this comparison
proves a causal effect of indication changes. The engine remains unvalidated by the frozen
suite. No implementation milestone is executed or implicitly approved here. **Stop after
this diagnosis and its first-failure register are frozen; do not run H6–H10.**
