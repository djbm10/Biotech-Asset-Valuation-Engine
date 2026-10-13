import concurrent.futures
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote
import requests

P = Path("/tmp/target_identity_authority_raw")
OUT = P / "uniprot"
OUT.mkdir(exist_ok=True)
universe = json.loads((P / "uniprot_request_universe.json").read_text())


def get(acc):
    url = "https://rest.uniprot.org/uniprotkb/" + quote(acc, safe="") + ".json"
    r = None
    errors = []
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=45)
            if r.status_code in [429, 500, 502, 503, 504]:
                errors.append({"attempt": attempt + 1, "status": r.status_code})
                time.sleep(2)
                continue
            break
        except requests.RequestException as e:
            errors.append({"attempt": attempt + 1, "error": str(e)})
            time.sleep(2)
    if r is None:
        return {"accession": acc, "url": url, "errors": errors, "status": "TRANSPORT_FAILURE"}
    name = quote(acc, safe="") + ".json"
    (OUT / name).write_bytes(r.content)
    receipt = {
        "accession": acc,
        "url": url,
        "final_url": r.url,
        "http_status": r.status_code,
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "artifact": "uniprot/" + name,
        "headers": dict(r.headers),
        "redirects": [
            {"url": h.url, "status": h.status_code, "headers": dict(h.headers)} for h in r.history
        ],
        "errors": errors,
    }
    release = r.headers.get("x-uniprot-release")
    receipt["release_matches"] = r.status_code != 200 or release == "2026_03"
    (OUT / (quote(acc, safe="") + ".receipt.json")).write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    return receipt


receipts = []
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for i, row in enumerate(pool.map(get, universe)):
        receipts.append(row)
        if i % 25 == 0:
            print(i + 1, "/", len(universe), row.get("http_status"), flush=True)
(P / "uniprot_receipts.json").write_text(
    json.dumps(sorted(receipts, key=lambda x: x["accession"]), sort_keys=True, indent=2) + "\n"
)
print("done", len(receipts), flush=True)
