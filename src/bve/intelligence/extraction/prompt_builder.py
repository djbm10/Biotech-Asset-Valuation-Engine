"""
Prompt construction for the signal extraction pipeline.

``PromptBuilder`` builds the system and user prompts passed to the LLM.
All methods are pure functions of their inputs — no state, no I/O.

Prompt versioning
-----------------
``CURRENT_PROMPT_VERSION`` is bumped whenever the template changes so that
``ExtractionResult.prompt_version`` can be correlated with quality metrics.
"""
from __future__ import annotations

from bve.intelligence.extraction.raw_document import RawDocument

CURRENT_PROMPT_VERSION: str = "v1.0"

# Maximum characters of raw_text injected into the prompt.
# Long documents are truncated to keep token cost bounded.
_MAX_TEXT_CHARS: int = 16_000

_SYSTEM_PROMPT = """\
You are a biotech intelligence extraction system that reads pharmaceutical and \
biotech documents and extracts structured event data.

CRITICAL OUTPUT RULE: Return ONLY a single valid JSON object. No markdown, no \
code fences, no preamble, no explanation. Your entire response must be parseable \
by json.loads() without any pre-processing.\
"""

_EVENT_TAXONOMY = """\
EVENT TAXONOMY — use exactly one of these 20 snake_case values for "event_type":

CLINICAL
  trial_readout          Phase 1/2/3 primary endpoint results reported (topline or final)
  interim_analysis       DSMB/IDMC interim data cut (futility, early stop, or continue)
  enrollment_update      Enrollment rate above/on/below plan; amended timeline
  endpoint_change        Protocol amendment modifying primary or key secondary endpoint
  safety_signal          AE, SUSAR, DILI, black-box warning, or clinical hold related to AEs
  conference_presentation  Data presented at ASCO, ASH, ADA, ESC, AACR, DDW, etc.
  publication            Peer-reviewed journal publication of trial or clinical results

REGULATORY
  fda_approval           NDA/BLA approved — full, accelerated, or conditional
  fda_rejection          Complete Response Letter (CRL) issued
  fda_designation        BTD, RMAT, ODD, Fast Track, or Priority Review granted
  regulatory_hold        Full or partial clinical hold placed or lifted
  label_expansion        Supplemental NDA/BLA for new indication, population, or line
  payer_coverage         CMS NCD, formulary decision, ICER assessment, step-therapy

BUSINESS
  partnership            License, co-development, collaboration, or acquisition
  financing              Equity offering, convertible note, or debt raise
  sec_filing             10-K / 10-Q / 8-K with material pipeline disclosure
  management_change      CEO, CMO, CSO, or board member hire or departure

COMPETITIVE & LIFECYCLE
  competitor_event       Competitor trial readout, approval, CRL, or major setback
  patent_event           IPR, litigation, patent grant, or LOE extension/settlement
  program_discontinuation  Asset discontinued, trial terminated, or IND withdrawn\
"""

_JSON_SCHEMA = """\
Return EXACTLY this JSON structure (all keys required; use null for absent values):

{
  "event_type": "<one of the 20 values above — required>",
  "signal_date": "<YYYY-MM-DD of when the event occurred — required>",
  "confidence": <0.0–1.0 — your confidence in ALL extracted fields combined>,
  "ambiguity_flag": <true if event type is unclear or multiple distinct events present>,
  "rationale": "<1–2 sentences explaining your event_type and key field choices>",

  "trial_phase": "<phase_1 | phase_2 | phase_3 | nda_bla | null>",
  "trial_nct_id": "<NCTxxxxxxxx | null>",
  "primary_endpoint_met": <true | false | null>,
  "interim_flag": <true | false>,
  "hazard_ratio": <positive float | null — HR for time-to-event endpoints, e.g. 0.72>,
  "p_value": <float 0.0–1.0 | null>,
  "response_rate": <float 0.0–1.0 | null — e.g. 0.42 for 42% ORR>,
  "safety_grade": <integer 1–5 (CTCAE grade) | null>,

  "fda_action_type": "<approval | crl | hold | hold_lifted | designation | null>",
  "designation_type": "<BTD | FTD | ODD | RMAT | priority_review | null>",

  "deal_value_millions": <positive float | null — total deal value USD millions>,
  "deal_type": "<string describing deal structure | null>",
  "payer_name": "<payer or PBM name | null>"
}

EXTRACTION RULES:
1. Set "confidence" to 0.0 when the document does not contain enough information
   to classify the event type reliably.
2. Set "ambiguity_flag" to true when: (a) multiple distinct events appear, (b) the
   event type could reasonably be two different categories, or (c) the document is
   clearly not a biotech intelligence event (investor relations boilerplate only).
3. "hazard_ratio" must be a positive number (HR < 1 means treatment benefit; HR > 1
   means harm). Never negate it.
4. "response_rate" is a proportion, not a percentage: 42% ORR → 0.42.
5. Only set "primary_endpoint_met" when the document explicitly states whether the
   primary endpoint was met or not met.
6. For "fda_designation" events, set both fda_action_type="designation" and the
   specific designation_type.
7. For clinical holds, use event_type="regulatory_hold", fda_action_type="hold"
   or "hold_lifted" as appropriate.\
"""


class PromptBuilder:
    """
    Builds the (system_prompt, user_prompt) pair for a given ``RawDocument``.

    All methods are stateless.  A single instance can be reused across many
    extraction calls.
    """

    CURRENT_VERSION: str = CURRENT_PROMPT_VERSION

    def build_system_prompt(self) -> str:
        """Return the invariant system instruction."""
        return _SYSTEM_PROMPT

    def build_user_prompt(self, document: RawDocument) -> str:
        """
        Build the document-specific user prompt.

        Injects entity context (drug name, indication, ticker) and the
        document text (truncated to ``_MAX_TEXT_CHARS``).  The schema and
        taxonomy are appended unchanged.

        Parameters
        ----------
        document:
            The normalized document to analyze.

        Returns
        -------
        str
            Complete user prompt ready to pass to ``LLMClient.complete()``.
        """
        hints  = document.entity_hints
        text   = document.raw_text[:_MAX_TEXT_CHARS]
        truncated = len(document.raw_text) > _MAX_TEXT_CHARS

        entity_lines: list[str] = []
        if hints.drug_name:
            entity_lines.append(f"  Drug / Asset: {hints.drug_name}")
        if hints.indication:
            entity_lines.append(f"  Indication:   {hints.indication}")
        if hints.ticker:
            entity_lines.append(f"  Ticker:       {hints.ticker}")
        if hints.nct_id:
            entity_lines.append(f"  NCT ID:       {hints.nct_id}")

        entity_section = (
            "ASSET CONTEXT (provided by pipeline operator — do not override these):\n"
            + ("\n".join(entity_lines) if entity_lines else "  (none provided)")
        )

        pub_str = (
            document.published_at.strftime("%Y-%m-%d")
            if document.published_at else "unknown"
        )
        source_str = (
            f"  Source type:  {document.source}\n"
            f"  Published:    {pub_str}\n"
            f"  URL:          {document.source_url or 'not available'}\n"
            f"  Title:        {document.title}"
        )

        trunc_note = (
            f"\n  [Document truncated to {_MAX_TEXT_CHARS:,} chars]"
            if truncated else ""
        )

        return (
            f"DOCUMENT METADATA:\n{source_str}\n\n"
            f"{entity_section}\n\n"
            f"DOCUMENT TEXT:{trunc_note}\n"
            f"{'='*60}\n"
            f"{text}\n"
            f"{'='*60}\n\n"
            f"{_EVENT_TAXONOMY}\n\n"
            f"{_JSON_SCHEMA}"
        )
