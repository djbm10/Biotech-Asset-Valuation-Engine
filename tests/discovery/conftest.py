"""Canned CT.gov protocol fixtures for offline discovery tests."""
from __future__ import annotations

from typing import Optional

import pytest


def make_protocol(
    *,
    nct_id: str,
    drug: Optional[str] = None,
    drug_type: str = "DRUG",
    drug_other_names: Optional[list[str]] = None,
    extra_interventions: Optional[list[tuple[str, str]]] = None,
    phases: Optional[list[str]] = None,
    status: str = "RECRUITING",
    enrollment: Optional[int] = None,
    lead_sponsor: str = "Acme Therapeutics",
    sponsor_class: str = "INDUSTRY",
    conditions: Optional[list[str]] = None,
    title: str = "A study",
    primary_completion: Optional[str] = None,
    start: Optional[str] = None,
) -> dict:
    """Build a minimal CT.gov v2 ``protocolSection`` dict."""
    interventions = []
    if drug is not None:
        iv: dict = {"type": drug_type, "name": drug}
        if drug_other_names:
            iv["otherNames"] = drug_other_names
        interventions.append(iv)
    for itype, iname in extra_interventions or []:
        interventions.append({"type": itype, "name": iname})

    proto: dict = {
        "identificationModule": {"nctId": nct_id, "briefTitle": title},
        "statusModule": {"overallStatus": status},
        "designModule": {},
        "armsInterventionsModule": {"interventions": interventions},
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": lead_sponsor, "class": sponsor_class}
        },
        "conditionsModule": {"conditions": conditions or []},
    }
    if phases is not None:
        proto["designModule"]["phases"] = phases
    if enrollment is not None:
        proto["designModule"]["enrollmentInfo"] = {"count": enrollment}
    if primary_completion is not None:
        proto["statusModule"]["primaryCompletionDateStruct"] = {"date": primary_completion}
    if start is not None:
        proto["statusModule"]["startDateStruct"] = {"date": start}
    return proto


@pytest.fixture
def make_protocol_fixture():
    return make_protocol
