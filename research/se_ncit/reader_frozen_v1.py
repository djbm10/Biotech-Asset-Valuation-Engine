import re
from bve.se.ontology.targets import resolve_target
CLASS_MAP={  # NCIt class code -> (gene or None, reason, surface forms from NCIt class name/definition)
 "C201492":("CD276",None,["B7-H3","CD276"]),"C176023":("TNFRSF17",None,["BCMA","TNFRSF17"]),
 "C201493":("IL3RA",None,["CD123"]),"C176018":("CD19",None,["CD19"]),"C201174":("MS4A1",None,["CD20"]),
 "C201173":("CD22",None,["CD22"]),"C201495":("CD33",None,["CD33"]),"C201510":("CD38",None,["CD38"]),
 "C211937":("CD5",None,["CD5"]),"C201176":("CD70",None,["CD70"]),"C226253":("CD79B",None,["CD79b"]),
 "C201172":(None,"isoform_specific_antigen",["Claudin18.2","CLDN18.2"]),"C226930":("DLL3",None,["DLL3"]),
 "C201175":("EGFR",None,["EGFR"]),"C201491":(None,"non_protein_antigen",["GD2"]),
 "C225034":("GPC3",None,["GPC-3","GPC3"]),"C212993":("GPRC5D",None,["GPRC5D"]),
 "C201497":("ERBB2",None,["HER2","ErbB2","HER-2"]),"C201178":("FOLH1",None,["PSMA"]),
 "C224031":("ROR1",None,["ROR1"]),"C201275":("MSLN",None,["mesothelin","MSLN"]),
}
norm=lambda s:re.sub(r"[^a-z0-9.]","",s.casefold())
SURFACE={}
for k,(g,_,forms) in CLASS_MAP.items():
    for f in forms+([g] if g else []): SURFACE[norm(f)]=("TARGET:"+g) if g else ("NONGENE:"+k)
MECH=re.compile(r"^(Upon|After|Following)\b")
def mech_sentence(defn):
    for s in re.split(r"(?<=\.)\s+(?=[A-Z])",defn):
        if MECH.match(s): return s
SEG=r"[A-Za-z0-9][A-Za-z0-9.*+\-]*?(?:/[A-Za-z0-9][A-Za-z0-9.*+\-]*?)*"
GOV=r"(?:in|to|toward|towards|against|kill|kills|lyse|lyses|recognize|recognizes|target|targets|of|both)"
PATS=[re.compile(GOV+r",?\s+(?:the\s+)?(?:both\s+)?("+SEG+r")(?:-?\s*(?:,|and/or|and|or)\s+("+SEG+r"))?-(?:expressing|positive|overexpressing)\b"),
      re.compile(r"(?:tumor|cancer|neoplastic|malignant)\s+(?:B-)?cells\s+(?:that\s+)?(?:express(?:ing)?|overexpress(?:ing)?)\s+(?:the\s+)?("+SEG+r")(?:\s+(?:and/or|and|or)\s+("+SEG+r"))?\b"),
      re.compile(r"\bthe\s+("+SEG+r")\s+antigen\s+on\b"),
      re.compile(r"\bbind(?:s)?\s+to\s+(?:the\s+)?("+SEG+r")(?:\s+and\s+("+SEG+r"))?\s+(?:on|expressed)\b")]
def shaped(x):
    b=x.replace("-","").replace(".","")
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9]*$",b)) and (sum(ch.isupper() for ch in b)>=2 or (any(ch.isupper() for ch in b) and any(ch.isdigit() for ch in b)))
def strict(m):
    r=resolve_target(m)
    if r is None or not r.canonical_id: return None
    matched=r.basis.matched_alias if r.basis else m
    appr=re.sub(r"[^A-Z0-9]","",matched.upper())==re.sub(r"[^A-Z0-9]","",(r.canonical_symbol or "").upper())
    if not appr and len(re.sub(r"[^A-Za-z0-9]","",matched))<3: return None
    return r.canonical_id
def read_part(p):
    p=p.strip("-.,* ")
    if norm(p) in SURFACE: return SURFACE[norm(p)]
    if shaped(p): return strict(p) or "UNRESOLVED:"+p
    return "UNRESOLVED:"+p
def mech_antigens(defn):
    s=mech_sentence(defn)
    if s is None: return None,"no_mechanism_sentence"
    got=set()
    for pat in PATS:
        for m in pat.finditer(s):
            for g in m.groups():
                if g:
                    for part in g.split("/"): got.add(read_part(part))
    bad=sorted(x for x in got if x.startswith("UNRESOLVED"))
    if bad: return None,"unresolved:"+",".join(bad)
    if not got: return None,"no_antigen"
    return frozenset(got),"ok"
