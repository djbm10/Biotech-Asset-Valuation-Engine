# Ontology resolution ambiguities — observed, logged, not patched

Symbol resolution goes through `bve.se.ontology.targets.normalize_target`, which returns a canonical
symbol or `None` (and `None` also means *ambiguous*, not only *unknown*). Several call sites treat
that answer as authoritative — deliberately, so that no hand-maintained symbol list can drift from
the published snapshot.

The cost is that the snapshot's own ambiguities become the engine's ambiguities. Those observed so
far are recorded here rather than patched, because hand-editing any one of them would falsify the
claim that the ontology is the authority. Opened 2026-09-24 out of the class-terms v5 arc.

Snapshot: `data/se/ontology/current` (ChEMBL_37 + Open Targets; see the resolver_v2 provenance note).

| input | resolves to | why it matters | disposition |
|---|---|---|---|
| `DNT` | `NT5C` | In `CD19-CAR-DNT cells`, `DNT` means *double-negative T cell* — a cell population, not a target. The class-term rule consumes it as a target designation, so the name is classified from a false premise even though the verdict (class term) is independently correct. | Logged. The operator's ruling: this *"should not motivate a class-term exception."* |
| `aNKT` (in `CD19.CAR-aNKT cells`) | — | Same shape as `DNT`: a cell population read as a designation. | Logged with `DNT`. |
| `CD20` | `None` (**ambiguous**, not unknown) | `CAR-20` therefore survives as an asset while `CART22` and `CART-138` are demoted — an inconsistency visible to any reviewer, driven entirely by the snapshot. | Amendment B1.3 of `class_terms_v5.md`. Reported, not patched. |
| `T` | `TBXT` | A single-letter token resolves to a real gene. Any code that offers raw tokens to `normalize_target` before consuming modality vocabulary will classify every `CAR-T` name as carrying a foreign target symbol. | Caused a scorer defect (92 vs 20); fixed in `ca70f3c` by tokenizing in the rule's order. `class_terms` was never affected. |
| `CART` | `CARTPT` | As above, for the `CART` modality abbreviation. | With `T`. |

## The reusable rule

**Consume modality vocabulary and filler *before* asking the ontology.** `T`, `CART`, `DNT` and
`aNKT` are all real symbols and all, in drug-name context, modality words. A predicate that queries
the ontology first will resolve them and be confidently wrong; one that classifies vocabulary first
never offers them. `bve.se.discovery.class_terms.individuating_residue` does it in the correct order —
copy that order, and do not reimplement the tokenization in analysis scripts.
