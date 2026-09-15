# M18 — mention precision: measurement and design

**Status: analysis complete, engine integration not yet written.** All numbers below are
measured on frozen artifacts; nothing in the engine has changed yet.

## 1. The predicted failure classes are not the actual ones

The directive anticipated cell lines (`HEK293`), residue tokens (`LYS191`), assay constants
(`IC50`), gene/protein symbols and cytokines. Those exist in the candidate population but
are a small minority. Sampling M17's 4,480 `unknown_word` false accepts at random shows the
class is dominated by **ordinary prose**:

- English words — `legitimate`, `victim`, `timeliness`, `backbone`, `taxonomy`, `worsen`,
  `handoffs`, `wormhole`
- **non-English abstract text** — `besserten`, `analizaron`, `permitir`, `szorong`,
  `keztetnek`, `profond`, `lograron`
- place and person names — `Beirut`, `Saito`, `Lugano`, `Luquan`, `Deoksan`
- taxonomy — `Anelloviridae`, `Mitragyna`, `cetaceans`, `taeniospiralis`
- chemistry and anatomy nouns — `phenolics`, `pentamers`, `colostrum`, `mesolimbic`,
  `thalami`

Composition: 2,878 lowercase, 1,325 titlecase, 204 all-caps, 443 hyphenated; the length
mode is 5–8 characters.

**Why the shape model fires on these.** It was trained on DRUG names versus TARGET labels
and other ontology vocabulary — a *biomedical symbol* contrast. It was never shown a single
ordinary word, so prose is out of distribution and it nominates confidently. This is a
training-contrast gap, not a threshold that is merely set too low.

A second honest note: `unknown_word` is not purely junk. The sample contains `benzhexol`
(a trihexyphenidyl synonym, i.e. a real CHRM1 drug), `ibritumomab`, `lestaurinib` and
`butylphthalide` — real molecules the frozen ontology lacks a record for. Any filter that
simply deletes the class would delete true assets.

## 2. Two signals measured, one of them backwards

### Prose discriminator (trained, then largely rejected)

`m18_train_prose_discriminator.py` trains drug names against prose harvested from the
M15/M16/B8 corpora — a second adversarial contrast rather than a hand-built stoplist. Two
properties keep it target-agnostic: a token can only become a negative if the frozen
ontology has **no DRUG record** for it (so no real drug can be trained against), and all
869 benchmark strings across the five targets are excluded outright. M17 was held out of
training entirely.

Held out: 40,952 positives / 19,373 negatives, vocabulary 19,097, threshold −0.7646 at a
pre-declared 98% recall floor, buying 85.0% precision.

Applied to M17's actual candidates it rejected only **511 of 4,480** (11%). The reason is
selection: M17's `unknown_word` population is precisely the prose that *already* beat the
shape model, so it is adversarially hard by construction. Held-out accuracy on generic
prose does not transfer to the surviving tail. Kept as a secondary signal only.

### Document frequency — the hypothesis was inverted

I expected junk to be high-frequency prose. Measured on M17, the opposite holds:

| class | median corpus DF | p10 | p90 |
|---|---|---|---|
| gold | 40 | 9 | 81 |
| trap | 10 | 2 | 23 |
| known_molecule | 2 | 1 | 15 |
| **unknown_word** | **1** | **0** | 23 |
| development_code | 0 | 0 | 0 |

Gold is the *most* frequent class — a corpus about a target discusses that target's drugs
constantly — and junk is overwhelmingly seen once. Rejecting frequent tokens would have
destroyed the gold set. Inverted into a **minimum corpus support** rule, the same signal
becomes the strongest available.

## 3. The protected-route finding that makes this safe

Partitioning M17's 8,080 candidates by whether they are protected (exact ontology drug
match, or containing a digit and therefore development-code shaped):

**The unprotected population is 4,938 candidates: 4,480 `unknown_word` + 458 `other`, and
zero gold, zero known_molecule, zero trap, zero development_code.**

So a filter applied only to unprotected candidates cannot cost a real molecule on this
benchmark. That is structural rather than lucky — benchmark gold is cut from ontology
DIRECT_TARGET edges, so gold assets are ontology-known by construction. It is also exactly
why this result must not be over-claimed: a genuinely novel asset absent from the ontology
would be unprotected, and the benchmarks cannot see that case.

## 4. Rule selection

Measured on M17 (8,080 candidates) and M16R (4,665), with protected routes always kept:

| rule | M17 cut | M16R cut | gold/known/trap lost |
|---|---|---|---|
| `df>=5` only | 3,755 (46.5%) | 1,866 (40.0%) | **0** |
| `df>=5 OR drug-shaped` | 671 (8.3%) | 157 (3.4%) | **0** |
| **`df>=5, or df>=2 if drug-shaped`** | **2,903 (35.9%)** | **1,498 (32.1%)** | **0** |

**Selected: the third.** Plain `df>=5` cuts more and loses nothing measurable, but it would
reject a novel single-mention asset — precisely the "legitimate uncommon small-molecule
names" the directive requires preserving — and the benchmarks are blind to that failure
because their gold is ontology-derived. The third rule requires only minimal corroboration
(≥2 documents) for a drug-shaped token and full support (≥5) otherwise, which also matches
the existing `MIN_SUPPORTED_DOCS` concept and M11's rule that co-occurrence is not identity.

## 5. Integration point

`pipeline.py:343`, `candidates = list(registry.assets.values())`.

The corpus-support signal does **not** require re-reading the corpus: `IdentityMention`
carries `source_document_id`, so distinct-document support per asset is already in the
registry. Measured on M17 it separates exactly as external token DF does:

| class | median distinct documents | p10 | p25 |
|---|---|---|---|
| gold | 40 | 10 | 21 |
| trap | 8 | 1 | 4 |
| known_molecule | 1 | 1 | 1 |
| unknown_word | 1 | 1 | 1 |
| other | 1 | 1 | 1 |

`known_molecule` sitting at median 1 is the reason the exact-ontology route must remain a
protected bypass rather than a feature fed into the rule.

## 6. What remains

1. Red tests first, then the filter at `pipeline.py:343`, applied only to unprotected
   candidates, reading support from `registry.mentions`.
2. Replay the frozen M15/M16/M17 corpora and confirm every acceptance criterion:
   unchanged discovery, unchanged identification, no new false target assertions, no new
   trap errors, and the unresolved count materially down from 7,966.
3. Report before/after including runtime and memory.

## 7. Artifacts

In `/home/djmann/staging/pdcd1_baseline` (outside the repo):
`m18_dump_candidates.py`, `m18_train_prose_discriminator.py`, `m18_eval_filter.py`,
`prose_discriminator_v1.json`, `M18_filter_eval_M17.json`,
`M17_candidates.tsv` / `M16R_candidates.tsv` / `M15_candidates.tsv`,
`M17_doc_freq.json` / `M16_doc_freq.json`.
