"""Transcribe the frozen evidence library's licensing quotes into a vendor-style deals file (cycle R1).

Each row cites one library item by index; the quote is copied verbatim. Structured fields (type, parties,
territory, date) are read from the quote only. Items carrying only payment terms are not rights events and
are listed in SKIPPED. Run: python research/dealscreen_rights_v1/build_rights_file.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT.parents[0] / "dealscreen_comparison_v1" / "sources" / "public_evidence.json"
items = json.loads(LIB.read_text(encoding="utf-8"))["items"]

# (library index, deal id, type label, exclusivity, licensee/acquirer, licensor/acquired, territory as written,
#  event date stated in the quote, status label, related deal)
ROWS = [
    (5, "R01", "Acquisition", "", "Astellas", "Ganymed", "", "", "", ""),
    (10, "R02", "Acquisition", "", "Astellas", "Ganymed", "", "", "", ""),
    (14, "R03", "Licensing", "Exclusive", "AstraZeneca", "KYM Biosciences", "global", "2023-02-23", "", ""),
    (19, "R04", "Licensing", "Exclusive", "AstraZeneca", "KYM Biosciences", "global", "2023-02-23", "", ""),
    (30, "R05", "Licensing", "", "Takeda", "Innovent Biologics", "worldwide outside of Greater China", "2025-10-21", "", ""),
    (35, "R06", "Licensing", "Exclusive", "Turning Point Therapeutics", "LaNova Medicines",
     "worldwide basis excluding Greater China and South Korea", "2022-05-04", "", ""),
    (37, "R07", "Termination", "", "Bristol Myers Squibb", "LaNova Medicines", "", "", "Terminated", ""),
    (38, "R08", "Rights returned", "", "Bristol Myers Squibb", "LaNova", "", "", "", ""),
    (42, "R09", "Option", "Exclusive", "Merck KGaA, Darmstadt, Germany", "Hengrui", "worldwide, outside of mainland China",
     "2023-10-30", "", ""),
    (42, "R10", "Option", "", "Merck KGaA, Darmstadt, Germany", "Hengrui", "mainland China", "2023-10-30", "", ""),
    (58, "R11", "Licensing", "Exclusive", "Astellas", "Evopoint Biosciences",
     "worldwide (excluding China's mainland, Hong Kong, Macao and Taiwan region)", "2025-05-29", "", ""),
    (67, "R12", "Co-development", "", "ABL Bio", "I-Mab", "worldwide rights, excluding Greater China and South Korea",
     "", "", ""),
    (70, "R13", "Licensing", "Exclusive", "Elevation Oncology", "CSPC Megalith Biopharmaceutical",
     "all global territories outside Greater China (mainland China, Hong Kong, Macau and Taiwan)", "2022-07-28", "", ""),
    (76, "R14", "Licensing", "Exclusive", "Elevation Oncology", "CSPC Megalith Biopharmaceutical",
     "all global territories outside Greater China (mainland China, Hong Kong, Macau and Taiwan)", "2022-07-28", "", ""),
    (102, "R15", "Licensing", "Exclusive", "AbbVie", "RemeGen", "outside of the Greater China territory", "2026-01-12", "", ""),
    (109, "R16", "Licensing", "Exclusive", "Flame Biosciences", "NovaRock Biotherapeutics", "territories excluding China",
     "", "", ""),
    (110, "R17", "Acquisition", "", "Leap Therapeutics", "Flame Biosciences", "", "", "", ""),
]
SKIPPED = {4: "payment terms only", 9: "payment terms only", 15: "payment terms only", 20: "payment terms only",
           36: "payment terms only", 43: "payment terms for a future option exercise; not an exercise",
           56: "payment terms only", 57: "duplicate of item 58 without territory", 59: "payment terms only",
           71: "payment terms only", 77: "payment terms only"}

out = ROOT / "inputs" / "rights_cldn18.csv"
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["Deal ID", "Program ID", "Deal Type", "Exclusivity", "Licensee", "Licensor", "Territory", "Deal Date",
                "Deal Status", "Related Deal", "Source URL", "Source Quote", "Source Date", "Library Item"])
    for idx, deal, kind, excl, lee, lor, terr, d, status, rel in ROWS:
        it = items[idx]
        assert it["fact_type"] == "licensing", idx
        w.writerow([deal, it["program_id"], kind, excl, lee, lor, terr, d, status, rel, it["url"], it["quote"],
                    it.get("date") or "", idx])
lic = {i for i, it in enumerate(items) if it["fact_type"] == "licensing"}
covered = {r[0] for r in ROWS} | set(SKIPPED)
assert lic == covered, sorted(lic ^ covered)
print(f"wrote {out} ({len(ROWS)} rows; {len(SKIPPED)} library items skipped with reasons)")
