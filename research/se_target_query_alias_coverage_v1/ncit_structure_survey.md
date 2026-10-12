# NCIt bulk authority structure survey (diagnosis only)

Release 26.09d captured from the official archive. The ZIP SHA-256 and source URL
are in ncit_release_receipt.json. extract_ncit_identifier_records.py extracts the
verbatim class properties P90/P108/P93/P369/P106 and R54 encoded-by links from
Thesaurus.owl; no target/query-specific selection. The resulting 13,032 identifier
records include 6,499 protein-accession and 6,533 HGNC gene records.

Structural screen: exactly one accession, one NCIt protein concept using that
accession, one encoded gene with one HGNC identifier, and protein semantic type:
6,060 eligible; 374 excluded for multiple concepts sharing an accession; 56 lacking
a unique encoded HGNC gene; 5 without protein semantic type; 4 with multiple
accessions. This is NOT alias admission. P90 term-group/source annotations and
protein-form/whole-protein scope still need contract-level evaluation. Do not
collapse isoforms, activated forms, complexes or measurements into genes merely
from a cross-reference.

Bulk source population may naturally contain frozen holdout targets. Their rows
were not used as probes or tuning examples; no heldout expected asset answers were
read in this survey. H21–H25 and H6–H10 remain unrun.
