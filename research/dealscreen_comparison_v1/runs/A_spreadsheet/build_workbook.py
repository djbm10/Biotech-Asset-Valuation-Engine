"""Build workflow-A spreadsheet deliverables (AI-SIMULATED / INTERNAL DEVELOPMENT)."""
import csv, json, sys
from openpyxl import Workbook
from openpyxl.styles import Font

BASE = "/home/djmann/projects/bve-b8/research/dealscreen_comparison_v1"
OUT = BASE + "/runs/A_spreadsheet"
rows = list(csv.DictReader(open(BASE + "/inputs/landscape_cldn18.csv")))
ev = json.load(open(BASE + "/sources/public_evidence.json"))["items"]
ev_by = {}
for e in ev:
    ev_by.setdefault(e["program_id"], []).append(e)

def q(pid, fact=None, contains=None):
    for e in ev_by.get(pid, []):
        if fact and e["fact_type"] != fact:
            continue
        if contains and contains.lower() not in e["quote"].lower():
            continue
        return f'{e["url"]} — "{e["quote"][:220].strip()}"'
    return "landscape cell"

# ---- judgements: pid -> (call, reason, group, target, modality, indication, phase)
G_AZ, G_XNW, G_ZOL, G_SYS = "sonesitatug_vedotin(CMG901/AZD0901)", "XNW27011/ASP546C", "zolbetuximab(IMAB362)", "SYSA1801/EO-3021"
J = {}
def S(pid, call, reason, group="", t="Y", m="Y", i="Y", p="Y"):
    J[pid] = (call, reason, group, t, m, i, p)

S("CL-01", "OUT", "Naked mAb (excluded modality); marketed (Vyloy)", G_ZOL, m="N")
S("CL-02", "OUT", "Same molecule as zolbetuximab; naked mAb", G_ZOL, m="N")
S("CL-03", "IN", "CLDN18.2 MMAE ADC; Phase 3 gastric/GEJ", G_AZ)
S("CL-04", "IN", "CLDN18.2 ADC (CMG901 = sonesitatug vedotin)", G_AZ)
S("CL-05", "IN", "CLDN18.2 ADC; same molecule as CMG901/AZD0901", G_AZ)
S("CL-06", "IN", "Landscape modality 'Imaging agent' is wrong: IBI343 is a CLDN18.2 ADC (NCIt, Takeda PR); Phase 3 G/GEJ")
S("CL-07", "IN", "CLDN18.2 MMAE ADC; Phase 3 G/GEJ (China)")
S("CL-08", "IN", "CLDN18.2 ADC (garetatug rezetecan); Phase 3 G/GEJ")
S("CL-09", "OUT", "Naked mAb (osemitamab)", m="N")
S("CL-10", "IN", "CLDN18.2xCD3 bispecific T-cell engager; Phase 3 G/GEJ")
S("CL-11", "IN", "CLDN18.2 TOP1i ADC; Phase 2 G/GEJ", G_XNW)
S("CL-12", "IN", "Same molecule as XNW27011 (alias in row)", G_XNW)
S("CL-13", "IN", "CLDN18.2x4-1BB bispecific; Phase 2 incl. gastric/GEJ")
S("CL-14", "IN", "CLDN18.2 MMAE ADC (=SYSA1801), Phase 1 human data; science fits but development discontinued", G_SYS)
S("CL-15", "IN", "CLDN18.2 ADC, Phase 1 G/GEJ; same molecule as EO-3021 (NCIt alias)", G_SYS)
S("CL-16", "IN", "CLDN18.2 ADC; Phase 3 G/GEJ in registry")
S("CL-17", "IN", "CLDN18.2xCD3 TCE (HBM7022); Phase 2 gastric/GEJ")
S("CL-18", "OUT", "CAR-T (excluded modality)", m="N")
S("CL-19", "OUT", "Naked mAb", m="N")
S("CL-20", "IN", "CLDN18.2xCD3 bispecific TCE; Phase 3 incl. gastric/GEJ")
S("CL-21", "UNRESOLVED", "Modality unknown; only pancreatic trial; possibly related to QLS31905 (name) - not verified", "possible QLS31905?", m="?", i="N")
S("CL-22", "OUT", "Naked mAb", m="N")
S("CL-23", "OUT", "Target is PD-L1/CD40, not CLDN18.2 (noise)", t="N")
S("CL-24", "IN", "CLDN18.2 MMAE ADC; Phase 3 G/GEJ")
S("CL-25", "IN", "CLDN18.2 ADC; Phase 2 in CLDN18.2+ solid tumours (gastric fit to confirm)", i="?")
S("CL-26", "OUT", "RC148 is PD-1/VEGF bispecific, not CLDN18.2 (noise)", t="N")
S("CL-27", "IN", "CLDN18.2 TOP1i ADC (ex-MK-1200); Phase 2 GEJ/solid tumours")
S("CL-28", "OUT", "Naked CLDN18.2 mAb (PD-1 in target cell is trial-combination noise)", m="N")
S("CL-29", "IN", "CLDN18.2 TOP1i ADC; Phase 3 G/GEJ")
S("CL-30", "OUT", "Naked mAb; terminated", m="N")
S("CL-31", "IN", "CLDN18.2xCD47 bispecific; Phase 2 G/GEJ")
S("CL-32", "UNRESOLVED", "Boltbody ISAC (immune-stimulating conjugate, not cytotoxic ADC; landscape says mAb) - buyer scope ambiguous", m="?")
S("CL-33", "OUT", "CLDN18.2 ADC but pancreatic-only and terminated; no gastric data", i="N")
S("CL-34", "OUT", "Naked mAb", m="N")
S("CL-35", "OUT", "mRNA-encoded naked mAb; discontinued", m="N")
S("CL-36", "IN", "CLDN18.2xCD3 BiTE, Phase 1 G/GEJ human data; terminated (inactive)")
S("CL-37", "IN", "CLDN18.2 MMAE ADC; Phase 1 incl. gastric/GEJ")
S("CL-38", "IN", "Landscape says mAb but LCB02A is an ADC (ConjuAll); Phase 1/2 solid tumours", i="?")
S("CL-39", "IN", "CLDN18.2xPD-L1 bispecific, Phase 1 solid tumours; status unknown", i="?")
S("CL-40", "OUT", "Naked mAb", m="N")
S("CL-41", "OUT", "anti-CLDN18.2/IL-10 fusion protein - not ADC/bispecific", m="N")
S("CL-42", "OUT", "CAR-T", m="N")
S("CL-43", "IN", "CLDN18.2 ADC, Phase 1 solid tumours; status unknown", i="?")
S("CL-44", "IN", "CLDN18.2xCD47 bispecific, Phase 1 solid tumours", i="?")
S("CL-45", "OUT", "VHH-Fc antibody (naked)", m="N")
S("CL-46", "IN", "CLDN18.2xCDH17 bispecific ADC; Phase 1/2a solid tumours", i="?")
S("CL-47", "OUT", "CAR-T", m="N")
S("CL-48", "OUT", "TAC T-cell therapy (cell therapy)", m="N")
S("CL-49", "OUT", "CAR-T", m="N")
S("CL-50", "OUT", "Naked mAb", m="N")
S("CL-51", "IN", "CLDN18.2xCD47 bispecific, Phase 1 solid tumours; status unknown", i="?")
S("CL-52", "OUT", "Radioligand - not in buyer modality scope", m="N")
S("CL-53", "UNRESOLVED", "No target/modality information; curator found no evidence", t="?", m="?")
S("CL-54", "OUT", "Naked mAb", m="N")
S("CL-55", "IN", "CLDN18.2 ADC; Phase 1 gastric/GEJ")
S("CL-56", "OUT", "CAR-NK", m="N")
S("CL-57", "OUT", "PD-1/TIGIT - not CLDN18.2 (noise)", t="N")
S("CL-58", "OUT", "HER2 - not CLDN18.2 (noise)", t="N")
S("CL-59", "OUT", "PD-1/CTLA-4 - not CLDN18.2 (noise)", t="N")
S("CL-60", "OUT", "PD-1/CTLA-4 - not CLDN18.2 (noise)", t="N")
S("CL-61", "OUT", "Imaging agent", m="N")
S("CL-62", "OUT", "Imaging agent", m="N")
assert len(J) == 62

ABBV_RC = "https://www.1stoncology.com/blog/2024/page/503"
# ---- rights: pid -> (holder, availability, marketing, dev status, evidence)
R = {
 "CL-01": ("Astellas (acquired Ganymed)", "HELD_BY_OTHERS", "Marketed US/EU (Vyloy)", "Marketed", q("CL-01", "approval")),
 "CL-02": ("Astellas", "HELD_BY_OTHERS", "Marketed US/EU (Vyloy)", "Marketed; Phase 4", q("CL-01", "licensing")),
 "CL-03": ("AstraZeneca (global exclusive licence from KYM)", "HELD_BY_OTHERS", "Not marketed", "Phase 3 (OS benefit CLARITY-Gastric01)", q("CL-03", "licensing", "global exclusive")),
 "CL-04": ("AstraZeneca", "HELD_BY_OTHERS", "Not marketed", "Phase 3 (via AZD0901)", q("CL-04", "licensing", "global exclusive")),
 "CL-05": ("AstraZeneca", "HELD_BY_OTHERS", "Not marketed", "Phase 3", q("CL-03", "licensing", "global exclusive")),
 "CL-06": ("Takeda (ex-China licence from Innovent) - territory per Takeda PR", "HELD_BY_OTHERS", "Not marketed (under NMPA review in China)", "Phase 3 met primary endpoint", q("CL-06", "licensing")),
 "CL-07": ("LaNova / Sino Biopharm (BMS returned rights 2024)", "NOT_EVIDENCED", "Not marketed", "Phase 3 China", q("CL-07", "licensing", "handed back")),
 "CL-08": ("Hengrui; Merck KGaA holds ex-China option (exercise status unknown)", "HELD_BY_OTHERS", "Not marketed", "Phase 3 China", q("CL-08", "licensing", "option")),
 "CL-10": ("Astellas", "HELD_BY_OTHERS", "Not marketed", "Phase 3", q("CL-10", "status")),
 "CL-11": ("Astellas (worldwide ex-Greater China)", "HELD_BY_OTHERS", "Not marketed", "Phase 1/2-2", q("CL-11", "licensing", "worldwide")),
 "CL-12": ("Astellas (worldwide ex-Greater China)", "HELD_BY_OTHERS", "Not marketed", "Phase 2", q("CL-12", "alias", "Astellas has")),
 "CL-13": ("I-Mab (lead) shares worldwide ex-Greater China & S.Korea rights equally with ABL Bio", "NOT_EVIDENCED", "Not marketed", "Phase 2 (registry active)", q("CL-13", "licensing")),
 "CL-14": ("unknown (Elevation licence from CSPC; development discontinued)", "UNKNOWN", "Not marketed", "Discontinued", q("CL-14", "status", "discontinue")),
 "CL-15": ("unknown (CSPC originator; ex-China licensed to Elevation 2022)", "UNKNOWN", "Not marketed", "Phase 1; registry UNKNOWN", q("CL-15", "licensing", "exclusive")),
 "CL-16": ("Antengene (global rights per company)", "NOT_EVIDENCED", "Not marketed", "Phase 3 in registry", 'https://www.1stoncology.com/blog/2024/page/503 — "Our four global rights assets — ATG-022 (Claudin 18.2 ADC) ... have all advanced steadily as planned."'),
 "CL-17": ("AstraZeneca (sponsor; licence from Harbour BioMed not sourced here)", "HELD_BY_OTHERS", "Not marketed", "Phase 2", "landscape cell"),
 "CL-20": ("Qilu Pharmaceutical (no ex-China licence found)", "NOT_EVIDENCED", "Not marketed", "Phase 3 China", q("CL-20", "status")),
 "CL-24": ("Junshi / NingBo Junyan Hongshi (no ex-China licence found)", "NOT_EVIDENCED", "Not marketed", "Phase 3 China", "landscape cell"),
 "CL-25": ("RemeGen (self-developed)", "NOT_EVIDENCED", "Not marketed", "Phase 2", q("CL-25", "modality")),
 "CL-27": ("Kelun-Biotech (Merck returned global rights Aug 2024)", "NOT_EVIDENCED", "Not marketed", "Phase 2", 'https://synapse.patsnap.com/article/merck-co-invests-in-kelun-bispecific-adc-exits-cldn182-program — "Kelun is committed to accelerating the development of SKB315 in China and exploring possibilities for expanding into international markets."'),
 "CL-29": ("Sichuan Baili / SystImmune (US affiliate) - no licence found", "NOT_EVIDENCED", "Not marketed", "Phase 3 China (registrational)", "https://www.biospace.com/press-releases/new-clinical-data-for-izalontamab-brengitecan-and-novel-adc-pipeline-to-be-presented-at-asco-2026 — \"BL-M05D1 targets Claudin 18.2\""),
 "CL-31": ("Phanes Therapeutics (wholly owned; Merck = supply collaboration only)", "NOT_EVIDENCED", "Not marketed", "Phase 2 (TWINPEAK)", 'https://www.clinicaltrialsarena.com/?p=189720 — "clinical trial collaboration and supply agreement with Merck to evaluate PT886 in combination with KEYTRUDA"'),
 "CL-36": ("Amgen", "HELD_BY_OTHERS", "Not marketed", "Terminated", "landscape cell"),
 "CL-37": ("TORL Biotherapeutics (originator)", "NOT_EVIDENCED", "Not marketed", "Phase 1 active-not-recruiting", "https://clinicaltrials.gov/study/NCT05156866 — \"First in Human Study of TORL-2-307-ADC\""),
 "CL-38": ("LigaChem Biosciences", "NOT_EVIDENCED", "Not marketed", "Phase 1/2 started 2026", q("CL-38", "status")),
 "CL-39": ("QureBio", "UNKNOWN", "Not marketed", "Registry UNKNOWN", "landscape cell"),
 "CL-43": ("Chia Tai Tianqing", "UNKNOWN", "Not marketed", "Registry UNKNOWN", "landscape cell"),
 "CL-44": ("Sumgen Biotech", "NOT_EVIDENCED", "Not marketed", "Phase 1 active", "landscape cell"),
 "CL-46": ("VelaVigo Bio", "NOT_EVIDENCED", "Not marketed", "Phase 1/2a active", q("CL-46", "target")),
 "CL-51": ("Akeso", "UNKNOWN", "Not marketed", "Registry UNKNOWN", "landscape cell"),
 "CL-55": ("Dong-A ST", "NOT_EVIDENCED", "Not marketed", "Phase 1 active", q("CL-55", "target")),
}

SHORT = [  # rank, pid, why, risks, questions
 (1, "CL-07", "Phase 3 MMAE ADC, ex-US rights returned by BMS; fits ADC capability", "Crowded MMAE class; China-only data; Sino Biopharm may keep global", "Is Sino Biopharm seeking an ex-China partner? Phase 3 readout timing?"),
 (2, "CL-27", "TOP1i ADC, global rights back from Merck; Kelun states intent to expand internationally", "Merck walked away (reason undisclosed); Phase 2 only", "Why did Merck return it? Kelun ex-China partnering appetite/terms?"),
 (3, "CL-16", "ADC with company-stated global rights; Phase 3 in registry; FDA orphan", "Small company data depth; MSD collab is supply-only", "Is Antengene open to US out-licence? Phase 3 design/region?"),
 (4, "CL-24", "Phase 3 MMAE ADC, 1L combo ORR 73% (AACR 2025, unverified)", "No ex-China rights info; China-only", "Who holds ex-China rights? Any licence?"),
 (5, "CL-29", "Registrational Phase 3 TOP1i ADC; US affiliate SystImmune sponsors a trial", "Rights split Baili/SystImmune unknown; BMS ties on other assets", "Is BL-M05D1 outside the BMS deal? Availability?"),
 (6, "CL-20", "First CLDN18.2xCD3 TCE in Phase 3; FDA orphan (PDAC)", "TCE CRS risk; not ADC (no mfg synergy)", "Ex-China rights status; relation to ANO31905/Anova?"),
 (7, "CL-31", "US-based, wholly owned CLDN18.2xCD47 bispecific; Phase 2; Fast Track (BTC)", "CD47 class safety history; not ADC", "Partnering intent? Gastric cohort data?"),
 (8, "CL-13", "CLDN18.2x4-1BB bispecific; US company with ex-China rights", "Rights split 50/50 with ABL Bio; 4-1BB liver tox class risk", "Would both I-Mab and ABL Bio transact?"),
 (9, "CL-25", "Self-developed ADC from RemeGen (proven out-licensor)", "Solid-tumour basket; gastric data unclear", "Gastric efficacy data? Ex-China rights?"),
 (10, "CL-46", "Bispecific ADC (CLDN18.2xCDH17) - differentiated, fits ADC mfg", "Early Phase 1/2a; small private company", "Data timing; ownership; ex-China rights"),
]
SRANK = {p: r for r, p, *_ in SHORT}

# ---------- calls.csv
with open(OUT + "/calls.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["program_id", "scientific_call", "reason", "identity_group", "us_rights_holder", "availability", "marketing_status", "development_status", "shortlist_rank", "evidence"])
    for r in rows:
        pid = r["Program ID"]; c = J[pid]
        if pid in R:
            h, a, mk, ds, e = R[pid]
        else:
            h, a, mk, ds = "unknown", "UNKNOWN", ("Not marketed" if pid not in ("CL-01", "CL-02") else ""), r["Status"]
            e = q(pid, "target") if ev_by.get(pid) else "landscape cell"
        if pid == "CL-18":
            mk = "Conditionally approved in China (not U.S.)"; e = q("CL-18", "approval")
        w.writerow([pid, c[0], c[1], c[2], h, a, mk, ds, SRANK.get(pid, ""), e])

# ---------- workbook
wb = Workbook(); ws = wb.active; ws.title = "Tracker"
hdr = list(rows[0].keys()) + ["Same molecule as", "Target fit", "Modality fit", "Indication fit", "Phase fit", "Scientific call (IN/OUT/UNRESOLVED)", "Reason", "Evidence (URL + quote)"]
ws.append(hdr)
groups = {}
for pid, c in J.items():
    if c[2]: groups.setdefault(c[2], []).append(pid)
for r in rows:
    pid = r["Program ID"]; c = J[pid]
    same = "; ".join(x for x in groups.get(c[2], []) if x != pid) if c[2] else ""
    ws.append(list(r.values()) + [same, c[3], c[4], c[5], c[6], c[0], c[1], q(pid, "target") if ev_by.get(pid) else "landscape cell"])
ws.auto_filter.ref = ws.dimensions
for cell in ws[1]: cell.font = Font(bold=True)

rs = wb.create_sheet("Rights")
rs.append(["Program ID", "Program", "Originator/company (landscape)", "Current U.S. rights holder", "Availability", "Marketing status", "Development status", "Evidence (URL + quote)"])
names = {r["Program ID"]: r for r in rows}
for pid, c in J.items():
    if c[0] != "IN": continue
    h, a, mk, ds, e = R.get(pid, ("unknown", "UNKNOWN", "Not marketed", names[pid]["Status"], "landscape cell"))
    rs.append([pid, names[pid]["Program"], names[pid]["Company"], h, a, mk, ds, e])

ss = wb.create_sheet("Shortlist")
ss.append(["Rank", "Program ID", "Program", "Why attractive", "Key risks", "Open questions", "Availability"])
for rk, pid, why, risk, qs in SHORT:
    ss.append([rk, pid, names[pid]["Program"], why, risk, qs, R[pid][1]])

# ---------- valuation
VAL = [("CL-07", "LM-302", "PHASE3"), ("CL-16", "ATG-022", "PHASE3"), ("CL-27", "SKB315", "PHASE2")]
MKT = dict(pat=6000, price=150000, pen=0.15, ytp=5, life=12, r=0.10)
DEV = {"phase_2": (60, 2, 0.35), "phase_3": (180, 3, 0.50), "nda_bla": (20, 1, 0.90)}
MARGIN = 0.40  # ANALYST ASSUMPTION
SCEN = {"Base": (1.0, 1.0), "Bear": (0.5, 0.8), "Bull": (1.5, 1.0)}  # (penetration mult, PoS mult on each phase)

def model(start, pen_m, pos_m):
    phases = ["phase_2", "phase_3", "nda_bla"] if start == "PHASE2" else ["phase_3", "nda_bla"]
    years, t, preach = {}, 0, 1.0
    costs = {}
    for ph in phases:
        c, d, p = DEV[ph]
        for k in range(int(d)):
            costs[t + k + 1] = costs.get(t + k + 1, 0) + c / d * preach
        t += int(d); preach *= p * pos_m
    L, pos = t, preach
    peak = MKT["pat"] * MKT["price"] * MKT["pen"] * pen_m / 1e6
    rev = {L + k: peak * min(k / MKT["ytp"], 1) for k in range(1, MKT["life"] + 1)}
    return phases, costs, rev, L, pos, peak

def npv(start, pen_m, pos_m, deal):
    phases, costs, rev, L, pos, peak = model(start, pen_m, pos_m)
    tot = 0
    for y in range(1, L + MKT["life"] + 1):
        df = 1 / (1 + MKT["r"]) ** y
        cf = -costs.get(y, 0) + rev.get(y, 0) * pos * (MARGIN - (0.12 if deal == "license" else 0))
        if deal == "license" and y == L: cf -= 500 * pos
        tot += cf * df
    tot -= 100 if deal == "license" else 400
    return tot, L, pos, peak

results = {}
for pid, nm, st in VAL:
    vs = wb.create_sheet(f"Val_{pid}")
    vs.append([f"{nm} ({pid}) buyer-perspective rNPV, $M. ALL INPUTS HYPOTHETICAL (protocol placeholders) or ANALYST ASSUMPTION. Not a sourced valuation."])
    vs.append(["Input", "Base", "Bear", "Bull", "Label"])
    inp = [("Addressable patients", 6000, "HYPOTHETICAL"), ("Net price $", 150000, "HYPOTHETICAL"),
           ("Peak penetration", None, "HYPOTHETICAL x scenario mult (ANALYST: bear 0.5x, bull 1.5x)"),
           ("Years to peak", 5, "HYPOTHETICAL"), ("Patent life yrs from launch", 12, "HYPOTHETICAL"),
           ("Discount rate", 0.10, "HYPOTHETICAL"), ("Operating margin on sales", MARGIN, "ANALYST ASSUMPTION"),
           ("Cumulative PoS to approval", None, "HYPOTHETICAL phase PoS product (bear: each x0.8, ANALYST)"),
           ("Years to launch", None, "HYPOTHETICAL durations"), ("Licence royalty", 0.12, "HYPOTHETICAL"),
           ("Licence milestones (at launch)", 500, "HYPOTHETICAL; ANALYST: all paid at launch"),
           ("Licence upfront", 100, "HYPOTHETICAL"), ("Acquisition upfront", 400, "HYPOTHETICAL")]
    for name, v, lab in inp:
        vals = []
        for sc, (pm, sm) in SCEN.items():
            _, _, _, L, pos, _ = model(st, pm, sm)
            vals.append({"Peak penetration": 0.15 * pm, "Cumulative PoS to approval": round(pos, 6), "Years to launch": L}.get(name, v))
        vs.append([name] + vals + [lab])
    # rows 3..15 inputs; B,C,D columns
    vs.append([]); vs.append(["Peak sales $M"] + [f"={c}3*{c}4*{c}5/1e6" for c in "BCD"])  # row 17
    hdr_row = 19
    vs.cell(hdr_row, 1, "Year")
    for j, sc in enumerate(SCEN):
        vs.cell(hdr_row, 2 + j * 4, f"{sc} Rev $M"); vs.cell(hdr_row, 3 + j * 4, f"{sc} R&D cost (prob-wtd)")
        vs.cell(hdr_row, 4 + j * 4, f"{sc} License CF"); vs.cell(hdr_row, 5 + j * 4, f"{sc} Acq CF")
    _, costs0, _, L0, _, _ = model(st, 1, 1)
    nyrs = L0 + 12
    for y in range(1, nyrs + 1):
        rr = hdr_row + y; vs.cell(rr, 1, y)
        for j, sc in enumerate(SCEN):
            col = "BCD"[j]; _, costs, _, _, _, _ = model(st, *SCEN[sc])
            rc = vs.cell(rr, 2 + j * 4).column_letter; cc = vs.cell(rr, 3 + j * 4).column_letter
            k = f"($A{rr}-{col}$11)"
            vs.cell(rr, 2 + j * 4, f"=IF(AND({k}>=1,{k}<={col}$7),{col}$17*MIN({k}/{col}$6,1),0)")
            vs.cell(rr, 3 + j * 4, round(costs.get(y, 0), 6))
            df = f"/(1+{col}$8)^$A{rr}"
            vs.cell(rr, 4 + j * 4, f"=(-{cc}{rr}+{rc}{rr}*{col}$10*({col}$9-{col}$12)-IF($A{rr}={col}$11,{col}$13*{col}$10,0)){df}")
            vs.cell(rr, 5 + j * 4, f"=(-{cc}{rr}+{rc}{rr}*{col}$10*{col}$9){df}")
    last = hdr_row + nyrs; tr = last + 2
    vs.cell(tr, 1, "rNPV licence ($M) = sum(disc CF) - upfront"); vs.cell(tr + 1, 1, "rNPV acquisition ($M) = sum(disc CF) - upfront")
    for j, sc in enumerate(SCEN):
        col = "BCD"[j]
        lc = vs.cell(1, 4 + j * 4).column_letter; ac = vs.cell(1, 5 + j * 4).column_letter
        vs.cell(tr, 2 + j, f"=SUM({lc}{hdr_row+1}:{lc}{last})-{col}14")
        vs.cell(tr + 1, 2 + j, f"=SUM({ac}{hdr_row+1}:{ac}{last})-{col}15")
        results[(pid, sc, "license")] = npv(st, *SCEN[sc], "license")
        results[(pid, sc, "acquisition")] = npv(st, *SCEN[sc], "acq")
    vs.cell(tr, 5, "(columns B/C/D = Base/Bear/Bull)")
    vs.cell(tr + 3, 1, "License vs acquisition: buyer perspective. Licence keeps upfront low but royalty+milestones cut value; acquisition only makes sense if seller owns ex-China/global rights outright. Availability NOT evidenced for any program.")
wb.save(OUT + "/workbook.xlsx")
json.dump({f"{k[0]}|{k[1]}|{k[2]}": [round(v[0], 1), v[1], round(v[2], 4), round(v[3], 1)] for k, v in results.items()}, sys.stdout, indent=0)
