"""BVE DealScreen: buyer-specific BD screening and valuation workbench (MVP).

Lane 4 (platform / workflow). Imports a provider landscape export, screens it with the
existing S&E gate engine, records analyst decisions, hands selected assets to BVE's
valuation CLI, and writes an auditable workbook and memo.

Validation grade: UNVALIDATED. Synthetic-data demonstration only. See
``docs/change_requests/CR-2026-10-26-dealscreen-mvp.md``.
"""

VALIDATION_GRADE = "UNVALIDATED"
VALIDATION_WARNING = (
    "This output is UNVALIDATED-grade only. Screening uses source-provided vendor "
    "assertions that BVE has not independently confirmed. Do not use for trade sizing, "
    "acquisition probability or a transaction decision."
)
DEALSCREEN_VERSION = "dealscreen_mvp_v1"
