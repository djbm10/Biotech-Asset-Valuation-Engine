"""Re-fetch every reference URL and check each quoted passage verbatim (whitespace-normalized).

ClinicalTrials.gov study pages are checked against the v2 API JSON for the same NCT, which is
what the page renders. A failed fetch is FETCH_FAILED, never a pass.
"""

import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

NCT = re.compile(r"clinicaltrials\.gov/study/(NCT\d{8})")


def norm(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = text.replace("\\n", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def fetch(url: str) -> str | None:
    if m := NCT.search(url):
        url = f"https://clinicaltrials.gov/api/v2/studies/{m.group(1)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research verification)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    if url.endswith(tuple("0123456789")) and "api/v2" in url:
        raw = json.dumps(json.loads(raw), ensure_ascii=False)
    return norm(raw)


def main(ref: Path, out: Path) -> None:
    data = json.loads(ref.read_text())
    cache, results = {}, []
    for e in data["entries"]:
        for i, ev in enumerate(e["evidence"]):
            if ev["url"] not in cache:
                cache[ev["url"]] = fetch(ev["url"])
                time.sleep(0.5)
            page = cache[ev["url"]]
            status = "FETCH_FAILED" if page is None else ("VERIFIED" if norm(ev["passage"]) in page else "NOT_FOUND")
            results.append({"ref_id": e["ref_id"], "i": i, "url": ev["url"], "supports": ev["supports"], "status": status})
    out.write_text(json.dumps(results, indent=1) + "\n")
    from collections import Counter
    print(Counter(r["status"] for r in results))
    for r in results:
        if r["status"] != "VERIFIED":
            print(r["ref_id"], r["status"], r["url"][:90], r["supports"])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
