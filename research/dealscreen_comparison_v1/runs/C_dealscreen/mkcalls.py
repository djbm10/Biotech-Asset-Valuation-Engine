import json,csv
L={r['Program ID']:r for r in csv.DictReader(open('/home/djmann/projects/bve-b8/research/dealscreen_comparison_v1/inputs/landscape_cldn18.csv'))}
def tool(ws):
    d=json.load(open(ws+'/screening.json')); m={}
    imp=json.load(open(ws+'/identity.json')) if False else None
    for s in d['screens']:
        ext=[c for c in s['facts']] if False else None
        m[s['program_name']]=(s['disposition'],s['rank'],s['market_status'] if isinstance(s.get('market_status'),str) else json.dumps(s.get('market_status'))[:60])
    return m
T2=tool('ws2'); T1=tool('ws')
IN,OUT,UN='IN','OUT','UNRESOLVED'; UNRESOLVED=UN
PE='sources/public_evidence.json'
# pid: call, reason, group, holder, avail, marketing, devstatus, rank, evidence
C={
'CL-01':(OUT,'naked mAb; marketed (VYLOY)','G-zolbetuximab','Astellas (acquired Ganymed 2016); labeler Astellas Pharma US','HELD_BY_OTHERS','Marketed US/EU (FDA approval 2024-10-18)','marketed','', 'openFDA label; '+PE+' CL-01 EC approval + Ganymed acquisition'),
'CL-02':(OUT,'same molecule as CL-01; naked mAb; marketed','G-zolbetuximab','Astellas','HELD_BY_OTHERS','Marketed (as zolbetuximab)','Phase 4 trials','', PE+' CL-02 NCIt IMAB362=zolbetuximab'),
'CL-03':(IN,'CLDN18.2 ADC (MMAE), Ph3 OS positive','G-sonesitatug','AstraZeneca (global exclusive license from KYM, 2023)','HELD_BY_OTHERS','not marketed','active Ph3','', 'astrazeneca.com PR 2023-02-23; onclive 2026-10-25'),
'CL-04':(IN,'same molecule as CL-03 (CMG901)','G-sonesitatug','AstraZeneca','HELD_BY_OTHERS','not marketed','active','', 'astrazeneca.com PR 2023-02-23'),
'CL-05':(IN,'same molecule as CL-03','G-sonesitatug','AstraZeneca','HELD_BY_OTHERS','not marketed','active Ph3','', 'onclive 2026-10-25'),
'CL-06':(IN,'CLDN18.2 ADC (exatecan) - landscape modality "Imaging agent" is WRONG; Ph3 met primary endpoint','G-IBI343','Takeda (ex-Greater China license 2025-10-21)','HELD_BY_OTHERS','not marketed (NMPA review)','active Ph3','', 'takeda.com newsroom 2025-10-21; NCIt C189808'),
'CL-07':(IN,'CLDN18.2 ADC (MMAE) Ph3 China','G-LM302','LaNova (Sino Biopharm); BMS/Turning Point ex-China license handed back','NOT_EVIDENCED','not marketed','active Ph3 (China)','1', 'pharmaphorum 2025-07 (rights handed back); TPTX 10-Q 2022; 1stoncology 2024-04-11'),
'CL-08':(IN,'CLDN18.2 ADC (rezetecan) Ph3','G-SHRA1904','Hengrui; Merck KGaA holds ex-mainland-China option (exercise status unknown)','HELD_BY_OTHERS','not marketed','active Ph3','', 'biospace Hengrui/Merck KGaA 2023-10-30'),
'CL-09':(OUT,'naked mAb (osemitamab)','G-TST001','Transcenta','UNKNOWN','not marketed','active','', PE+' CL-09'),
'CL-10':(IN,'CLDN18.2xCD3 TCE Ph3','G-ASP2138','Astellas','HELD_BY_OTHERS','not marketed','active Ph3','', 'Astellas PR 2026-08-25 (placera)'),
'CL-11':(IN,'CLDN18.2 ADC (TOP1i) Ph1/2','G-XNW27011','Astellas (ex-Greater China license from Evopoint 2025-05-29)','HELD_BY_OTHERS','not marketed','active','', 'drugdiscoveryonline Astellas/Evopoint 2025-05-29'),
'CL-12':(IN,'same molecule as CL-11 (ASP546C)','G-XNW27011','Astellas','HELD_BY_OTHERS','not marketed','active','', PE+' CL-12'),
'CL-13':(IN,'CLDN18.2x4-1BB bispecific Ph2','G-givastomig','I-Mab (lead) and ABL Bio share worldwide ex-GC/SK rights','NOT_EVIDENCED','not marketed','active','7', 'natlawreview I-Mab PR 2025-06-30'),
'CL-14':(IN,'CLDN18.2 ADC; scientifically fits but development discontinued 2025-03','G-SYSA1801','Elevation Oncology licensed ex-GC from CSPC (2022); discontinued; return of rights not evidenced','NOT_EVIDENCED','not marketed','discontinued','', 'ELEV 8-K ex99 2022-07-28; Elevation PR 2025-03-20'),
'CL-15':(IN,'same molecule as CL-14 (EO-3021 = SYSA1801); tool did NOT flag','G-SYSA1801','CSPC (China); ex-GC licensed to Elevation 2022','NOT_EVIDENCED','not marketed','no active trial','', 'ELEV 8-K ex99 2022-07-28'),
'CL-16':(IN,'CLDN18.2 ADC, Ph3 CLINCH-3; FDA ODD gastric','G-ATG022','Antengene (no out-license found; interim report lists global rights)','NOT_EVIDENCED','not marketed','active Ph3','3', 'cancernetwork ODD; Antengene interim 2026-08-23 (patsnap synapse)'),
'CL-17':(IN,'CLDN18.2xCD3 TCE (HBM7022)','G-AZD5863','AstraZeneca (licensed from Harbour BioMed)','HELD_BY_OTHERS','not marketed','active','', PE+' CL-17 NCIt alias HBM7022; AZ sponsor'),
'CL-18':(OUT,'CAR-T','G-CT041','CARsgen','UNKNOWN','conditionally approved China','active','', PE+' CL-18'),
'CL-19':(OUT,'naked mAb','G-AB011','CARsgen','UNKNOWN','not marketed','completed','', PE+' CL-19'),
'CL-20':(IN,'CLDN18.2xCD3 TCE Ph3','G-QLS31905','Qilu (no ex-China deal found; BD listing of an unnamed CLDN18.2/CD3 TCE for licensing)','NOT_EVIDENCED','not marketed','active Ph3','2', 'pharmcube 2025-07-25; drugtimes.cn 2026-07-11 listing (asset unnamed)'),
'CL-21':(UNRESOLVED,'modality not stated; code suggests possible same molecule as QLS31905 (Anova/Qilu) - unverified','G-QLS31905?','unknown','UNKNOWN','not marketed','active','', 'CT.gov title only'),
'CL-22':(OUT,'naked mAb','G-M108','FutureGen','UNKNOWN','not marketed','active','', PE+' CL-22'),
'CL-23':(OUT,'target PD-L1/CD40 not CLDN18.2','G-FGB901','FutureGen','UNKNOWN','not marketed','active','', PE+' CL-23'),
'CL-24':(IN,'CLDN18.2 ADC (MMAE) Ph3','G-JS107','Junshi / NingBo Junyan Hongshi; no license found','UNKNOWN','not marketed','active Ph3','4', 'NCIt C190687; NCT07284134'),
'CL-25':(IN,'CLDN18.2 ADC Ph2, self-developed','G-RC118','RemeGen; no license found','UNKNOWN','not marketed','active','6', 'RemeGen 2022-12-12'),
'CL-26':(OUT,'PD-1/VEGF-type bispecific, not CLDN18.2','G-RC148','AbbVie ex-GC','HELD_BY_OTHERS','not marketed','','', 'AbbVie PR 2026-01-12'),
'CL-27':(IN,'CLDN18.2 ADC (TOP1i); alias MK-1200','G-SKB315','Merck & Co (MK-1200) ex-China per alias','HELD_BY_OTHERS','not marketed','active','', 'NCIt alias MK-1200 (public_evidence CL-27)'),
'CL-28':(OUT,'naked CLDN18.2 mAb (landscape PD-1 target is a combo artefact)','G-ASKB589','AskGene','UNKNOWN','not marketed','active Ph3','', 'NCIt (CL-28)'),
'CL-29':(IN,'CLDN18.2 ADC (TOP1i) Ph3','G-BLM05D1','Baili/SystImmune; no license found','UNKNOWN','not marketed','active Ph3','5', 'NCIt C215079'),
'CL-30':(OUT,'naked mAb; terminated','G-FL301','Flame (ex-China from NovaRock)','UNKNOWN','not marketed','terminated','', PE+' CL-30'),
'CL-31':(IN,'CLDN18.2xCD47 bispecific Ph2','G-PT886','Phanes Therapeutics (US private)','NOT_EVIDENCED','not marketed','active','9', 'Phanes PR 2026 (biospace)'),
'CL-32':(UNRESOLVED,'ISAC (immune-stimulating antibody conjugate): conjugate, not classic cytotoxic ADC; landscape says mAb - buyer to decide','G-BDC4182','Bolt Biotherapeutics','UNKNOWN','not marketed','active','', '1stoncology 2026'),
'CL-33':(IN,'CLDN18.2 ADC; terminated','G-SOT102','SOTIO','UNKNOWN','not marketed','terminated','', 'SOTIO PR 2021; NCIt'),
'CL-34':(OUT,'naked mAb','G-ZL1211','Zai Lab','UNKNOWN','not marketed','completed','', PE+' CL-34'),
'CL-35':(OUT,'mRNA-encoded mAb; discontinued','G-BNT141','BioNTech','UNKNOWN','not marketed','discontinued','', 'BNT 2023Q2 ex99'),
'CL-36':(IN,'CLDN18.2xCD3 BiTE; terminated','G-AMG910','Amgen','UNKNOWN','not marketed','terminated','', 'ckb.jax.org'),
'CL-37':(IN,'CLDN18.2 ADC (elatatug vedotin, MMAE) Ph1','G-TORL2307','TORL BioTherapeutics (US private)','UNKNOWN','not marketed','active Ph1','8', 'NCIt C185565 (cismef)'),
'CL-38':(IN,'ADC (ConjuAll platform) - landscape "Monoclonal antibody" is WRONG; first trial 2026 (phase likely 1)','G-LCB02A','LigaChem','UNKNOWN','not marketed','active','', 'asiae 2026-04-14'),
'CL-39':(IN,'PD-L1xCLDN18.2 bispecific','G-Q1802','QureBio','UNKNOWN','not marketed','no active trial','', 'NCIt (CL-39)'),
'CL-40':(OUT,'naked mAb','G-MIL93','Mabworks','UNKNOWN','not marketed','','', 'NCIt'),
'CL-41':(OUT,'anti-CLDN18.2/IL-10 fusion protein (not ADC/bispecific/TCE)','G-LB4330','L&L Bio','UNKNOWN','not marketed','active','', 'CT.gov intervention'),
'CL-42':(OUT,'CAR-T','G-LB1908','Legend','UNKNOWN','not marketed','active','', 'NCIt'),
'CL-43':(IN,'CLDN18.2 ADC','G-TQB2103','Chia Tai Tianqing','UNKNOWN','not marketed','no active trial','', 'NCIt'),
'CL-44':(IN,'CLDN18.2xCD47 bispecific','G-SG1906','Sumgen','UNKNOWN','not marketed','active Ph1','', 'NCIt'),
'CL-45':(OUT,'VHH-Fc (naked antibody-like); terminated','G-DR30303','Doer','UNKNOWN','not marketed','terminated','', 'NCIt C198698'),
'CL-46':(IN,'CLDN18.2/CDH17 bispecific ADC','G-VBC108','VelaVigo','UNKNOWN','not marketed','active Ph1/2a','10', 'CT.gov title'),
'CL-47':(OUT,'CAR-T','G-IBI345','Innovent','UNKNOWN','not marketed','completed','', 'NCIt'),
'CL-48':(OUT,'TAC T-cell therapy (cell therapy)','G-TAC01','Triumvira','UNKNOWN','not marketed','active','', 'NCIt'),
'CL-49':(OUT,'CAR-T','G-IMC002','Immunofoco','UNKNOWN','not marketed','','', 'biospace 2024-05'),
'CL-50':(OUT,'naked mAb','G-LM102','LaNova','UNKNOWN','not marketed','terminated','', 'NCIt'),
'CL-51':(IN,'CLDN18.2xCD47 bispecific','G-AK132','Akeso','UNKNOWN','not marketed','no active trial','', 'NCIt'),
'CL-52':(OUT,'radioligand (not in scope modalities)','G-SNA040','SmartNuclide','UNKNOWN','not marketed','active','', 'CT.gov title'),
'CL-53':(UNRESOLVED,'no target or modality in any source','G-Bio008','Yiling','UNKNOWN','not marketed','','', 'not found (public_evidence not_found)'),
'CL-54':(OUT,'naked mAb','G-SPX101','SparX','UNKNOWN','not marketed','terminated','', 'NCIt'),
'CL-55':(IN,'CLDN18.2 ADC Ph1','G-DA3501','Dong-A ST','UNKNOWN','not marketed','active Ph1','', 'asiae 2025-06-24'),
'CL-56':(OUT,'CAR-NK','G-EBDNK102','Beijing Biotech','UNKNOWN','not marketed','active','', 'CT.gov'),
'CL-57':(OUT,'PD-1/TIGIT, not CLDN18.2','G-rilvegostomig','AstraZeneca','HELD_BY_OTHERS','not marketed','active','', 'NCIt'),
'CL-58':(OUT,'HER2 biparatopic, not CLDN18.2','G-zanidatamab','Jazz/Zymeworks (not checked)','UNKNOWN','marketed (BTC) - not verified here','active','', 'NCIt C130010'),
'CL-59':(OUT,'PD-1/CTLA-4, not CLDN18.2','G-volrustomig','AstraZeneca','HELD_BY_OTHERS','not marketed','active','', 'NCIt'),
'CL-60':(OUT,'PD-1/CTLA-4 mAb mixture','G-QL1706','Qilu','UNKNOWN','not marketed','active','', 'NCIt'),
'CL-61':(OUT,'imaging agent','G-NY005','Wuxi No.4 Hospital','UNKNOWN','not marketed','','', 'CT.gov title'),
'CL-62':(OUT,'imaging agent','G-RESCA3A12','RenJi Hospital','UNKNOWN','not marketed','active','', 'CT.gov NCT06203613'),
}
cols=['program_id','program','scientific_call','reason','identity_group','us_rights_holder','availability','marketing_status','development_status','shortlist_rank','evidence','tool_disposition','tool_rank','tool_disposition_without_target_map','tool_market_status','differs_from_tool_why']
w=csv.writer(open('calls.csv','w',newline='')); w.writerow(cols)
from collections import Counter; cnt=Counter()
for pid,r in L.items():
    c=C[pid]; t=T2[r['Program']]; t1=T1[r['Program']]; cnt[c[0]]+=1
    td={'ELIGIBLE':IN,'EXCLUDED':OUT,'UNRESOLVED':UN}[t[0]]
    why='' if td==c[0] else ('tool UNRESOLVED: indication/modality gate UNKNOWN; AI evidence supports call' if t[0]=='UNRESOLVED' else 'tool used landscape modality text, which is wrong per cited source' if c[0]==IN else 'tool cannot judge this modality/scope; see reason')
    w.writerow([pid,r['Program'],c[0],c[1],c[2],c[3],c[4],c[5],c[6],c[7],c[8],t[0],t[1] if t[1] is not None else '',t1[0],t[2],why])
print(cnt)
