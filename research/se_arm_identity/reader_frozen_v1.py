import re
#: A trailing arm/dose qualifier: separated from the product name, closed vocabulary.
QUAL=re.compile(r"""(?ix)
 (?:^|[\s\-–:,(]+)
 (?:
   (?:dose|dosage)(?:\s*level)?\s*[0-9]{1,2}[a-z]? |
   dl\s*[0-9]{1,2} |
   (?:iv\s+)?(?:high|low|middle|mid|medium|intermediate)[\s-]+dose |
   (?:cohort|arm|group|part)\s+(?:[0-9]{1,2}|[a-h]) 
 )\s*\)?\s*$""")
def arm_base(name):
    m=QUAL.search(name)
    if not m: return None
    base=name[:m.start()].strip(" -–:,(")
    return base or None
