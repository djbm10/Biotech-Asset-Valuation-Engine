# TARGET_QUERY_GREEK_ORTHOGRAPHY v1 — failed preregistration, no implementation

Rules/oracle builder were committed in `ebff4b4`. Oracle derivation predicted 85 RESOLVED, three AMBIGUOUS and eight UNRESOLVED Greek forms. These are expected labels, not candidate results. No production implementation existed or was evaluated.

Review exposed an invalid G5 oracle: it treated every raw whole-string abstention as absence of a valid target anywhere in the query. The frozen whole name “Serine/threonine-protein kinase MRCK beta” contains the separately asserted, unique alias “MRCK beta” for the same CDC42BPB gene. Its Greek form can legitimately contain the corresponding shorter authority alias even when the conservative new whole-name fallback declines strings containing slash. The first criterion would incorrectly label that supported target as a false attribution.

`protocol_counterexample.json` captures both source records asserting the shorter alias and their common current identifier. Preserve this failed preregistration and the 85/3/8 raw oracle. There is no candidate to revert. A successor must freeze biological reference identity separately from raw orthographic eligibility before implementing. This changes no scientific expected identity, introduces no product/query-specific rule, and uses no candidate outcomes. H21–H25/H6–H10 remain untouched; human-PoC remains stopped.
