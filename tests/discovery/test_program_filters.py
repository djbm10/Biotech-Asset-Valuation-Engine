"""Tests for comparator/generic + device-company filters."""
from __future__ import annotations

from tests.discovery.conftest import make_protocol

from bve.discovery.program_cluster import cluster_programs
from bve.discovery.program_filters import (
    is_device_or_dx_company,
    is_generic_comparator,
)
from bve.discovery.sponsor_trials import parse_protocol


class TestGenericComparator:
    def test_plain_generics(self):
        assert is_generic_comparator("Warfarin")
        assert is_generic_comparator("Gemcitabine")
        assert is_generic_comparator("Gemzar")

    def test_canonical_key_path(self):
        # CT.gov labels a warfarin arm "anticoagulation".
        assert is_generic_comparator("Warfarin/Coumadin", drug_key="anticoagulation")

    def test_multiword_phrase(self):
        assert is_generic_comparator("Standard of Care chemotherapy")

    def test_real_coded_asset_is_not_comparator(self):
        assert not is_generic_comparator("VK2735", drug_key="vk2735")
        assert not is_generic_comparator("ARV-471", drug_key="arv471")

    def test_substring_does_not_overmatch(self):
        # "cisplatin" is a generic, but an unrelated token must not trip it.
        assert not is_generic_comparator("Aspirinox-12", drug_key="aspirinox12")


class TestDeviceCompany:
    def test_obvious_device_dx(self):
        assert is_device_or_dx_company("Intuitive Surgical")
        assert is_device_or_dx_company("Hologic Diagnostics")
        assert is_device_or_dx_company("Acme Medical Devices")

    def test_normal_biotech_is_not(self):
        assert not is_device_or_dx_company("Viking Therapeutics, Inc.")
        assert not is_device_or_dx_company("Arvinas, Inc.")


class TestClusterDropsComparators:
    def test_generic_program_dropped_real_lead_surfaces(self):
        company = "Verastem"
        protos = [
            make_protocol(nct_id="N1", drug="Gemcitabine", phases=["PHASE3"],
                          enrollment=400, status="RECRUITING", lead_sponsor=company),
            make_protocol(nct_id="N2", drug="VS-6766", phases=["PHASE3"],
                          enrollment=300, status="RECRUITING", lead_sponsor=company),
        ]
        trials = [parse_protocol(p, company) for p in protos]
        programs = cluster_programs(trials)
        drugs = {p.drug for p in programs}
        assert "VS-6766" in drugs
        assert not any("gemcitabine" in p.drug.lower() for p in programs)
