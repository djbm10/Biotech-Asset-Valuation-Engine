from __future__ import annotations

import csv
import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.se.acquisition.policy import (
    DeclaredSourceEntry,
    LiveSourcePolicy,
    UnsupportedBuyerProblemError,
    validate_public_https_url,
)
from bve.se.schemas.contracts import BuyerProblemV2


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _policy(**updates) -> LiveSourcePolicy:
    payload = {
        "schema_version": "se_live_source_policy_v1",
        "policy_version": "2026.07.1",
        "live_enabled": True,
        "required_source_families": ["clinicaltrials_gov", "sec_edgar"],
        "optional_source_families": ["pubmed", "company_press_release"],
        "supported_targets": ["CD19", "BCMA"],
        "supported_modalities": ["T_CELL_ENGAGER", "ADC"],
        "declared_sources": [
            {
                "source_family": "company_press_release",
                "urls": ["https://www.example.com/pipeline", "https://example.com/news"],
            }
        ],
    }
    payload.update(updates)
    return LiveSourcePolicy.model_validate(payload)


def _problem(*, target: str = "CD19", modality: str = "T_CELL_ENGAGER") -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "schema_version": "se_buyer_problem_v2",
            "problem_id": "source-policy-test",
            "version": "1.0.0",
            "buyer": {
                "buyer_id": "buyer-1",
                "name": "Buyer",
                "as_of_date": "2026-07-12",
            },
            "strategic_gap": {
                "therapeutic_areas": ["oncology"],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": target, "label": target}],
                },
                "modalities": [modality],
            },
        }
    )


def test_policy_is_strict_and_versioned() -> None:
    policy = _policy()

    assert policy.schema_version == "se_live_source_policy_v1"
    assert policy.live_enabled is True
    assert policy.required_source_families == ("clinicaltrials_gov", "sec_edgar")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _policy(unexpected=True)


def test_declared_source_entry_requires_nonempty_urls() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        DeclaredSourceEntry(source_family="company_press_release", urls=[])


@pytest.mark.parametrize(
    "source_family",
    ["../conference_ash", "conference/ash", "conference\\ash", ".", "Conference_ASH"],
)
def test_source_family_must_be_a_safe_path_component(source_family: str) -> None:
    with pytest.raises(ValidationError, match="safe lowercase path component"):
        DeclaredSourceEntry(
            source_family=source_family,
            urls=["https://example.com/source"],
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/source",
        "https://user:secret@example.com/source",
        "https://localhost/source",
        "https://feeds.localhost/source",
        "https://127.0.0.1/source",
        "https://10.0.0.7/source",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/source",
        "https://[fe80::1]/source",
        "https://0177.0.0.1/source",
        "https://internal/source",
    ],
)
def test_declared_urls_must_be_public_https(url: str) -> None:
    with pytest.raises(ValidationError):
        DeclaredSourceEntry(source_family="company_press_release", urls=[url])


def test_declared_urls_are_normalized_and_deduplicated() -> None:
    entry = DeclaredSourceEntry(
        source_family="company_press_release",
        urls=["HTTPS://EXAMPLE.COM:443/news"],
    )
    assert entry.urls == ("https://example.com/news",)

    with pytest.raises(ValidationError, match="duplicate URLs"):
        DeclaredSourceEntry(
            source_family="company_press_release",
            urls=["https://example.com", "HTTPS://EXAMPLE.COM:443/"],
        )


def test_public_url_validator_exposes_the_same_fail_closed_boundary() -> None:
    assert validate_public_https_url("HTTPS://EXAMPLE.COM:443/news") == (
        "https://example.com/news"
    )
    with pytest.raises(ValueError, match="localhost"):
        validate_public_https_url("https://localhost/news")


def test_source_families_are_unique_and_partitioned() -> None:
    with pytest.raises(ValidationError, match="both required and optional"):
        _policy(optional_source_families=["pubmed", "sec_edgar"])

    duplicated = [
        {
            "source_family": "company_press_release",
            "urls": ["https://example.com/news"],
        },
        {
            "source_family": "company_press_release",
            "urls": ["https://example.org/news"],
        },
    ]
    with pytest.raises(ValidationError, match="duplicate source families"):
        _policy(declared_sources=duplicated)


def test_declared_source_must_belong_to_policy_partition() -> None:
    with pytest.raises(ValidationError, match="absent from the required/optional policy"):
        _policy(
            declared_sources=[
                {
                    "source_family": "conference_ash",
                    "urls": ["https://example.com/ash"],
                }
            ]
        )


def test_supported_scope_is_nonempty_and_unique() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        _policy(supported_targets=[])
    with pytest.raises(ValidationError, match="duplicate identifier"):
        _policy(supported_modalities=["ADC", "adc"])


def test_configuration_hash_is_canonical_and_sensitive_to_changes() -> None:
    first = _policy()
    reordered = _policy(
        required_source_families=["sec_edgar", "clinicaltrials_gov"],
        optional_source_families=["company_press_release", "pubmed"],
        supported_targets=["BCMA", "CD19"],
        supported_modalities=["ADC", "T_CELL_ENGAGER"],
        declared_sources=[
            {
                "source_family": "company_press_release",
                "urls": ["https://example.com/news", "https://www.example.com/pipeline"],
            }
        ],
    )
    changed_payload = deepcopy(first.model_dump(mode="json"))
    changed_payload["policy_version"] = "2026.07.2"
    changed = LiveSourcePolicy.model_validate(changed_payload)

    assert len(first.configuration_hash) == 64
    assert first.configuration_hash == reordered.configuration_hash
    assert first.configuration_hash != changed.configuration_hash


def test_problem_scope_validation_accepts_supported_problem() -> None:
    problem = _problem(target="BCMA", modality="ADC")
    assert _policy().validate_problem(problem) is problem


@pytest.mark.parametrize(
    ("target", "modality", "message"),
    [
        ("DLL3", "ADC", "unsupported targets: DLL3"),
        ("CD19", "CAR_T", "unsupported modalities: CAR_T"),
    ],
)
def test_problem_scope_validation_fails_closed(
    target: str,
    modality: str,
    message: str,
) -> None:
    with pytest.raises(UnsupportedBuyerProblemError, match=message):
        _policy().validate_problem(_problem(target=target, modality=modality))


def test_production_declared_urls_do_not_seed_development_asset_identities() -> None:
    policy_path = PROJECT_ROOT / "examples/configs/se/live_cd19_bcma_tce_policy.yaml"
    reference_path = (
        PROJECT_ROOT
        / "research/se_benchmarks/cd19_bcma/development/reference_universe.csv"
    )
    policy = LiveSourcePolicy.model_validate(yaml.safe_load(policy_path.read_text()))
    declared_url_text = re.sub(
        r"[^a-z0-9]+",
        "",
        " ".join(url for source in policy.declared_sources for url in source.urls).casefold(),
    )
    with reference_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    asset_identifiers = {
        normalized
        for row in rows
        for value in [row["canonical_asset"], *row.get("aliases", "").split("|")]
        if len(normalized := re.sub(r"[^a-z0-9]+", "", value.casefold())) >= 6
    }

    assert not sorted(identifier for identifier in asset_identifiers if identifier in declared_url_text)
