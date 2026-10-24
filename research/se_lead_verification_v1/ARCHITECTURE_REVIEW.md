# Qualification and source architecture review

The follow-up is a manual evidence overlay, not an automatic qualification change.

| Required distinction | Existing support | Observed gap / follow-up handling |
|---|---|---|
| Named preclinical vs clinical asset | Registry phases, evidence facts, CandidateCard.stage; Assessed statuses | A name-shape classification does not establish stage. HXN keeps preclinical evidence; cizutamig has exact intervention/alias and disease-specific Phase 1 records. |
| Approved comparator | bd_triage.LabelSnapshot exact FDA label matching | No match is UNKNOWN. No new approval lookup or global non-approval inference; UCB's dated investigational statement is attributed to UCB. |
| Acquired/partnered program | OwnershipRight contract can represent territory/indication/rights type; registry has provenance-preserving relationships | bd_triage has no acquired-program category; CandidateCard.company holds registry sponsors, not transaction events. Follow-up stores commercial context independently from scientific maturity and rights. |
| Relevant asset, unknown rights | Existing reporting already warns sponsorship is not ownership | Follow-up makes territorial_rights and availability separate mandatory fields. UCB acquisition evidence is not converted to universal rights or availability. |
| Inadequately identified construct | asset_qualification positive drug context; registry identity-bearing evidence and reversible merges; bd_triage name shape | Display classify_name('cizutamig') returns NOT_ONE_PRODUCT, despite primary identification. HXN-1031 returns NAMED_PRODUCT; generic CD19 BCMA T cell engager returns DESCRIPTIVE_CONSTRUCT. Do not repair with a seeded asset list. Existing production rules unchanged. |

The new research renderer reuses bd_brief.Assessed / EvidenceStatus / Source and verifies local
source hashes and selected spans/JSON paths. Supported facts require a value and primary link;
acquired/partnered display context requires a supported company relationship; identified lead
categories require a supported identity. These are reporting invariants, not scientific gates.
Manual interpretation can still be wrong: hashes and types establish custody, not entailment.
No registry merges, authority overrides, human-PoC confirmation, ranking or engine grade promotion.
OwnershipRight currently defaults geography to GLOBAL. No OwnershipRight is created here:
unknown territorial scope must not be silently converted to that default in any future integration.

## Actual acquisition observations

- DeclaredUrlConnector + CorpusStore successfully retained seven HTML pages through the existing
  bounded HTTP boundary. Two CT.gov named-query JSON responses were retained through get_json;
  this direct follow-up avoids pretending target+modality discovery queries were executed.
- Earendil /pipeline: HTTP success, 2,558 decoded characters, parsed body only a page title.
  Connector reports INDEXED/OK but retrieves **no HXN-1031 evidence**. The linked JavaScript
  bundle (359,668 characters) contains the exact program/target row. One bounded direct bundle
  retrieval verified it manually; no crawler/browser runtime or general JavaScript parser added.
  Stage display arrays were not promoted to verified clinical entry or a precise milestone.
- UCB completion and September releases: substantive text retained, but parsed publication_date
  is None although dates are explicit in the body. They were admitted as current observations,
  not backdated. Manual evidence records June 17 / September 29 disclosure dates. A historical
  PUBLISHED_AT replay would withhold them. Date extraction needs a separate bounded fix/evaluation.
- CT.gov follow-up: 9 cizutamig/CND106 matches, no next page; 0 exact HXN spelling matches.
  No global clinical-trial completeness claim: alternate codes, other registries and unpublished
  studies remain possible. No posted results returned. Stored registry sponsor Candid is compatible
  with UCB acquisition and is not proof of independence or rights.
- ClinicalTrialsGovConnector's discovery text flattens title/summary/interventions/sponsor;
  its native protocol retains structured fields, but the brief must explicitly preserve phase,
  actual vs estimated enrollment/start, study condition, status and update date. The follow-up
  trial table derives those fields directly and retains negative/withdrawn records.
- Default acquisition still does not autonomously connect a discovered name to the right issuer's
  acquisition announcement, resolve regional rights, or recover JavaScript-only pipeline rows.
  This work used named follow-up and manual source selection; it improves these two dossiers,
  not source-discovery recall or general autonomous qualification accuracy.

## Before/after audit (two exposed development cases)

Before: HXN named preclinical antibody, Helixon affiliation only; clinical entry/rights unknown.
After: independently reacquired ACR evidence plus Earendil program listing and bounded negative
registry query. Clinical entry, chain of title, territorial rights and availability remain unknown.

Before: cizutamig nominated, explicit antibody scaffold missing on the acquired ACR page; pooled
safety known; Candid/UCB disclosures did not establish the acquisition event.
After: UCB confirms bispecific format and completed acquisition announcement; CT.gov explicitly
links CND106, identifies disease-specific Phase 1/1b studies and distinguishes estimated enrollment,
withdrawn/healthy studies and stale registry status. Acquired-program context replaces an unresolved
corporate relationship. SEC-filed issuer and EpimAb disclosures additionally establish a historical
license excluding Greater China; current amendments and complete rights still require confirmation.
No efficacy or global-rights claim added. Discovery endpoint remains untouched.

No population accuracy, precision or analyst-time estimate is valid from this selected pair.
Final independent BD assessment remains OUTSTANDING. Implementer review finds a useful research
handoff for deciding whom to investigate/contact and which evidence to request, not a deal shortlist.
