"""Column-mapping profiles: how one provider's export headers map to DealScreen fields.

A profile is YAML so an analyst can write one for a new vendor export without code. It
also carries the dataset's license metadata (DATA_SOURCE_POLICY), and the importer refuses
a file whose profile does not declare it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Canonical DealScreen fields. ``program_name`` and ``external_id`` are required in every
#: profile; the rest are optional because vendors export different subsets.
CANONICAL_FIELDS: tuple[str, ...] = (
    "external_id",
    "source_system",
    "program_name",
    "aliases",
    "target",
    "mechanism",
    "modality",
    "therapeutic_area",
    "indication",
    "phase",
    "development_status",
    "as_of_date",
    "company",
    "trial_ids",
    "us_rights",
    "us_rights_holder",
    "geographic_rights",
    "partnerships",
    "source_reference",
    "source_date",
    "data_flags",
)
REQUIRED_FIELDS: tuple[str, ...] = ("external_id", "program_name")
LIST_FIELDS: frozenset[str] = frozenset(
    {"aliases", "target", "indication", "trial_ids", "partnerships", "source_reference"}
)
DATE_FIELDS: frozenset[str] = frozenset({"as_of_date", "source_date"})
_LICENSES = {"public", "licensed", "proprietary", "scraped", "synthetic", "internal"}
_USES = {"commercial", "research_only", "internal_only", "demonstration_only"}


class MappingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    #: Constant source system name when the export has no column for it.
    source_system: str = Field(min_length=1)
    license_status: str
    allowed_use: str
    #: canonical field -> header in the vendor file
    columns: dict[str, str]
    list_separator: str = ";"
    #: vendor therapeutic-area label -> S&E canonical area (e.g. Immunology -> AUTOIMMUNE)
    therapeutic_area_map: dict[str, str] = Field(default_factory=dict)
    #: vendor phase label (casefolded) -> S&E development_stage_order
    phase_map: dict[str, int] = Field(default_factory=dict)
    date_formats: list[str] = Field(default_factory=lambda: ["%Y-%m-%d"])

    @model_validator(mode="after")
    def _check(self) -> MappingProfile:
        unknown = sorted(set(self.columns) - set(CANONICAL_FIELDS))
        if unknown:
            raise ValueError(f"profile maps unknown canonical fields {unknown}")
        missing = [f for f in REQUIRED_FIELDS if f not in self.columns]
        if missing:
            raise ValueError(f"profile must map required fields {missing}")
        if self.license_status not in _LICENSES:
            raise ValueError(f"license_status must be one of {sorted(_LICENSES)}")
        if self.allowed_use not in _USES:
            raise ValueError(f"allowed_use must be one of {sorted(_USES)}")
        headers = list(self.columns.values())
        if len(headers) != len(set(headers)):
            raise ValueError("two canonical fields map to the same header")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> MappingProfile:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: a mapping profile must be a YAML mapping")
        return cls(**data)

    def sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def stage_order(self, phase_text: str) -> int | None:
        return self.phase_map.get(" ".join(phase_text.casefold().split()))
