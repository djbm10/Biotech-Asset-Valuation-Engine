"""Strict, versioned policy contract for live S&E public-source acquisition.

The policy is deliberately independent of connector construction.  It defines the
supported BuyerProblem scope and validates declared public source locations before
any network or filesystem boundary is crossed.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bve.se.schemas.contracts import BuyerProblemV2


_SOURCE_FAMILY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SCOPE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_NON_CANONICAL_IPV4_RE = re.compile(r"^[0-9.]+$")


class UnsupportedBuyerProblemError(ValueError):
    """Raised when a BuyerProblem falls outside a live source policy's scope."""


def _validate_source_family(value: str) -> str:
    if not _SOURCE_FAMILY_RE.fullmatch(value):
        raise ValueError(
            "source_family must be a safe lowercase path component containing only "
            "letters, digits, and underscores"
        )
    return value


def _normalize_scope_ids(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = value.strip().upper()
        if not _SCOPE_ID_RE.fullmatch(candidate):
            raise ValueError(f"{field_name} contains an invalid canonical identifier: {value!r}")
        if candidate in seen:
            raise ValueError(f"{field_name} contains duplicate identifier {candidate!r}")
        seen.add(candidate)
        normalized.append(candidate)
    return tuple(normalized)


def _normalize_public_https_url(value: str) -> str:
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError("declared source URL must not contain whitespace")
    if "\\" in value or any(ord(character) < 32 for character in value):
        raise ValueError("declared source URL contains unsafe characters")

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"invalid declared source URL: {value!r}") from exc

    if parsed.scheme.casefold() != "https":
        raise ValueError("declared source URL must use HTTPS")
    if not parsed.netloc or parsed.hostname is None:
        raise ValueError("declared source URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("declared source URL must not contain credentials")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid declared source URL port: {value!r}") from exc

    hostname = parsed.hostname.rstrip(".").casefold()
    if not hostname or "%" in hostname:
        raise ValueError("declared source URL has an invalid hostname")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("declared source URL must not target localhost")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Reject alternate/non-canonical dotted IPv4 forms rather than allowing
        # the HTTP stack or resolver to reinterpret them as a local address.
        if _NON_CANONICAL_IPV4_RE.fullmatch(hostname):
            raise ValueError("declared source URL contains an invalid IP literal")
        if "." not in hostname:
            raise ValueError("declared source URL must use a public DNS hostname")
        try:
            canonical_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("declared source URL has an invalid hostname") from exc
    else:
        if not address.is_global:
            raise ValueError(
                "declared source URL must not use a loopback, private, link-local, "
                "or otherwise non-public IP literal"
            )
        canonical_hostname = address.compressed

    rendered_host = (
        f"[{canonical_hostname}]" if ":" in canonical_hostname else canonical_hostname
    )
    rendered_port = "" if port in {None, 443} else f":{port}"
    return urlunsplit(
        (
            "https",
            f"{rendered_host}{rendered_port}",
            parsed.path or "/",
            parsed.query,
            parsed.fragment,
        )
    )


def validate_public_https_url(value: str) -> str:
    """Validate and canonicalize one declared public HTTPS retrieval URL."""

    return _normalize_public_https_url(value)


class DeclaredSourceEntry(BaseModel):
    """One configured public document source family and its retrieval locations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family: str
    urls: tuple[str, ...] = Field(min_length=1)

    @field_validator("source_family")
    @classmethod
    def validate_source_family(cls, value: str) -> str:
        return _validate_source_family(value)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_normalize_public_https_url(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("declared source entry contains duplicate URLs")
        return normalized


class LiveSourcePolicy(BaseModel):
    """Supported scope and source requirements for one live acquisition regime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["se_live_source_policy_v1"] = "se_live_source_policy_v1"
    policy_version: str = Field(min_length=1)
    live_enabled: bool = True
    required_source_families: tuple[str, ...] = Field(min_length=1)
    optional_source_families: tuple[str, ...] = ()
    supported_targets: tuple[str, ...] = Field(min_length=1)
    supported_modalities: tuple[str, ...] = Field(min_length=1)
    declared_sources: tuple[DeclaredSourceEntry, ...] = ()

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("policy_version must not be blank")
        return value.strip()

    @field_validator("required_source_families", "optional_source_families")
    @classmethod
    def validate_source_families(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_validate_source_family(value) for value in values)
        if len(validated) != len(set(validated)):
            raise ValueError("source family list contains duplicates")
        return validated

    @field_validator("supported_targets")
    @classmethod
    def validate_supported_targets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_scope_ids(values, field_name="supported_targets")

    @field_validator("supported_modalities")
    @classmethod
    def validate_supported_modalities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_scope_ids(values, field_name="supported_modalities")

    @model_validator(mode="after")
    def validate_family_partition(self) -> "LiveSourcePolicy":
        required = set(self.required_source_families)
        optional = set(self.optional_source_families)
        overlap = sorted(required & optional)
        if overlap:
            raise ValueError(
                "source families cannot be both required and optional: " + ", ".join(overlap)
            )

        declared_families = [entry.source_family for entry in self.declared_sources]
        if len(declared_families) != len(set(declared_families)):
            raise ValueError("declared_sources contains duplicate source families")
        unknown = sorted(set(declared_families) - required - optional)
        if unknown:
            raise ValueError(
                "declared source families are absent from the required/optional policy: "
                + ", ".join(unknown)
            )
        return self

    def canonical_payload(self) -> dict[str, object]:
        """Return an order-independent JSON-compatible policy representation."""

        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "live_enabled": self.live_enabled,
            "required_source_families": sorted(self.required_source_families),
            "optional_source_families": sorted(self.optional_source_families),
            "supported_targets": sorted(self.supported_targets),
            "supported_modalities": sorted(self.supported_modalities),
            "declared_sources": [
                {
                    "source_family": entry.source_family,
                    "urls": sorted(entry.urls),
                }
                for entry in sorted(self.declared_sources, key=lambda item: item.source_family)
            ],
        }

    def canonical_json(self) -> str:
        """Serialize the canonical policy without insignificant whitespace."""

        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def configuration_hash(self) -> str:
        """Deterministic SHA-256 of the canonical policy configuration."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def validate_problem(self, problem: BuyerProblemV2) -> BuyerProblemV2:
        """Fail when ``problem`` requests a target or modality outside this policy."""

        requested_targets = {
            target.canonical_id.strip().upper()
            for target in problem.strategic_gap.target_expression.targets
        }
        requested_modalities = {
            modality.strip().upper() for modality in problem.strategic_gap.modalities
        }
        unsupported_targets = sorted(requested_targets - set(self.supported_targets))
        unsupported_modalities = sorted(
            requested_modalities - set(self.supported_modalities)
        )
        reasons: list[str] = []
        if unsupported_targets:
            reasons.append("unsupported targets: " + ", ".join(unsupported_targets))
        if unsupported_modalities:
            reasons.append("unsupported modalities: " + ", ".join(unsupported_modalities))
        if reasons:
            raise UnsupportedBuyerProblemError(
                f"BuyerProblem {problem.problem_id!r} is outside live source policy "
                f"{self.policy_version!r}: " + "; ".join(reasons)
            )
        return problem


__all__ = [
    "DeclaredSourceEntry",
    "LiveSourcePolicy",
    "UnsupportedBuyerProblemError",
    "validate_public_https_url",
]
