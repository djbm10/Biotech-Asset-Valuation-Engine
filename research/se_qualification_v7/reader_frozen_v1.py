import re
from bve.se.discovery.asset_qualification import is_development_code
HEADS={"chemotherapy","chemotherapies","regimen","regimens","treatment","treatments","therapy","therapies","agents","conditioning","immunosuppression","consolidation","induction","lymphodepletion","care"}
CONSTRUCT={"car","cart","cell","cells","antibody","antibodies","nanobody","vector","mrna","vaccine","virus","tcr","nk","til","lnp"}
def descriptor(name):
    core=re.sub(r"\([^)]*\)|\[[^\]]*\]","",name)
    toks=[t for t in re.split(r"[^A-Za-z0-9]+",core) if t]
    if not toks: return None
    parts={p.casefold() for t in re.split(r"\s+",core) for p in re.split(r"[^A-Za-z0-9]+",t) if p}
    if parts & CONSTRUCT: return None
    if any(is_development_code(t) for t in re.split(r"\s+",core.strip()) if t): return None
    last=toks[-1].casefold()
    if last in HEADS: return f"head:{last}"
    if last=="based" and re.search(r"-based\s*$",core.strip(),re.I): return "elliptical_based"
    return None
