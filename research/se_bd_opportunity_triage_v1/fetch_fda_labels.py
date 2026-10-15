"""Freeze an openFDA drug-label snapshot for the names a BD brief displays.

Keys: displayed names (first 10 reviewable, deferred and excluded entries of each demo run)
plus the ChEMBL authority record name each entry carries. One phrase query per key against
`openfda.brand_name` and `openfda.generic_name`; raw responses are hashed. Matching (exact
normalized equality) happens later, offline, in `bve.se.reporting.bd_triage`.
"""

import hashlib
import json
import re
import sys
import time
from pathlib import Path

import urllib.error
import urllib.parse
import urllib.request

import yaml

from bve.se.reporting.bd_brief import _partial_matches

RUNS = ("tac01_protoid_v1", "mint5_protoid_v1")
_RECORD = re.compile(r"molecule type of DRUG:(.+?) \(CHEMBL")
_FIELDS = ("brand_name", "generic_name", "application_number", "manufacturer_name")


def get_json(url: str, params: dict) -> dict | None:
    req = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "bve-research-script"}
    )
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # openFDA: zero matches
                return None
            if exc.code == 400:  # unparseable phrase; recorded, never read as "no label"
                return {"query_error": 400}
            if attempt == 5:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == 5:
                raise
        time.sleep(2**attempt)
    return None


def keys() -> list[str]:
    out = set()
    for run in RUNS:
        sl = json.loads((Path.home() / "se_runs" / run / "shortlist.json").read_text())
        for e in sl["entries"][:10] + sl["deferred"][:10] + sl["excluded"][:10]:
            out.add(e["name"])
            for f in e["facts"]:
                if f["label"] == "Authority modality" and (m := _RECORD.search(f.get("note") or "")):
                    out.add(m.group(1))
        # v1.1 extension: partial-target matches the brief now displays (multi-target runs).
        problem = yaml.safe_load((Path.home() / "se_runs" / run / "problem.yaml").read_text())
        result = json.loads((Path.home() / "se_runs" / run / "result.json").read_text())
        requested = {f"TARGET:{t['canonical_id']}" for t in problem["strategic_gap"]["target_expression"]["targets"]}
        for m in _partial_matches(result, requested):
            out.add(m["name"])
            if m.get("authority_name"):
                out.add(m["authority_name"])
    return sorted(out)


def main(raw_dir: Path, snapshot: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    labels, queries = {}, []
    for key in keys():
        for field in ("brand_name", "generic_name"):
            phrase = re.sub(r"[^\w\s-]", " ", key).strip()
            payload = get_json(
                "https://api.fda.gov/drug/label.json",
                {"search": f'openfda.{field}:"{phrase}"', "limit": 100},
            )
            blob = json.dumps(payload, sort_keys=True).encode()
            sha = hashlib.sha256(blob).hexdigest()
            (raw_dir / f"{sha}.json").write_bytes(blob)
            results = (payload or {}).get("results", [])
            queries.append({
                "key": key, "field": field, "sha256": sha, "n": len(results),
                "error": (payload or {}).get("query_error"),
            })
            for r in results:
                o = r.get("openfda", {})
                labels[r["set_id"]] = {
                    "set_id": r["set_id"],
                    "effective_time": r.get("effective_time"),
                    **{f: sorted(o.get(f, [])) for f in _FIELDS},
                    "indications": " ".join(r.get("indications_and_usage", []))[:600],
                    "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={r['set_id']}",
                }
            time.sleep(0.3)
    snapshot.write_text(json.dumps(
        {"source": "openFDA drug/label (FDA SPL)", "retrieved": time.strftime("%Y-%m-%d"),
         "queries": queries, "labels": dict(sorted(labels.items()))},
        indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(len(queries), len(labels))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
