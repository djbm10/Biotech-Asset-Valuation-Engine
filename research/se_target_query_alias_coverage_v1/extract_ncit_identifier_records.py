import json
import zipfile
import xml.etree.ElementTree as E
from pathlib import Path

p = Path("/tmp/target_query_alias_coverage_v1")
R = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
OWL_NS = "{http://www.w3.org/2002/07/owl#}"
T = "{http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#}"
rows = []
with zipfile.ZipFile(p / "Thesaurus_26.09d.OWL.zip") as z, z.open("Thesaurus.owl") as f:
    for event, e in E.iterparse(f, events=("end",)):
        if e.tag != OWL_NS + "Class" or not e.get(R + "about"):
            continue
        code = e.get(R + "about").split("#")[-1]
        props = {
            k: [x.text for x in e.findall(T + k) if x.text]
            for k in ("P90", "P108", "P93", "P369", "P106")
        }
        genes = []
        for r in e.iter(OWL_NS + "Restriction"):
            on = r.find(OWL_NS + "onProperty")
            val = r.find(OWL_NS + "someValuesFrom")
            if on is not None and val is not None and on.get(R + "resource", "").endswith("#R54"):
                genes.append(val.get(R + "resource", "").split("#")[-1])
        if props["P93"] or props["P369"]:
            rows.append({"code": code, **props, "encoded_by": genes})
        e.clear()
(p / "ncit_identifier_records.json").write_text(json.dumps(rows, sort_keys=True, indent=2) + "\n")
print(
    json.dumps(
        {
            "records": len(rows),
            "protein_xref": sum(bool(r["P93"]) for r in rows),
            "gene_xref": sum(bool(r["P369"]) for r in rows),
        }
    )
)
