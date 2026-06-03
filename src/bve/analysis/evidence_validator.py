"""
P2.7 — Evidence pack ingestion & YAML validation with Validator class.

Loads as-of evidence snapshot YAMLs from research/evidence/**/*.yaml and
validates their structure, required fields, and consistency constraints.
Evidence packs document what was knowable at an analysis date from
contemporaneous public sources, enabling reproducible as-of validation.

Evidence YAML schema
--------------------
asof_date: "YYYY-MM-DD"              # ISO date string
company: str                         # Company name
ticker: str                          # Stock ticker (1–6 uppercase letters)
drug: str                            # Drug name / identifier
indication: str                      # Indication description
analysis_phase: str                  # Phase label (e.g. "phase_3")
knowable:                            # Dict of labeled evidence items
  <key>:
    description: str                 # Required
    source: str                      # Required
    confidence: High | Medium | Low  # Required
    notes: str                       # Optional
not_knowable:                        # List of hindsight exclusions (>=1 required)
  - item: str                        # Required
    actual_disclosure: str           # Required
    error_if_used: str               # Required
error_decomposition:                 # Optional block
  primary_error_driver: str
  foreseeable_errors: list[str]
  unforeseeable_errors: list[str]
  peak_sales_error_attribution: dict # Optional sub-block
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_CONFIDENCE = {"High", "Medium", "Low"}
_TICKER_RE = re.compile(r"^[A-Z]{1,6}$")

_REQUIRED_TOP_LEVEL = [
    "asof_date", "company", "ticker", "drug",
    "indication", "analysis_phase", "knowable", "not_knowable",
]
_REQUIRED_KNOWABLE_ITEM = ["source", "confidence"]
_REQUIRED_NOT_KNOWABLE_ITEM = ["item", "actual_disclosure", "error_if_used"]


# ---------------------------------------------------------------------------
# Structured data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnowableItem:
    """One piece of evidence that was observable at the analysis date."""
    key: str
    source: str
    confidence: str          # "High" | "Medium" | "Low"
    description: Optional[str] = None   # Free-text description; absent for numeric data items
    notes: Optional[str] = None


@dataclass(frozen=True)
class NotKnowableItem:
    """One hindsight exclusion — explicitly not available at analysis date."""
    item: str
    actual_disclosure: str
    error_if_used: str


@dataclass(frozen=True)
class ErrorDecomposition:
    """Post-hoc attribution of model error sources."""
    primary_error_driver: Optional[str] = None
    foreseeable_errors: tuple[str, ...] = field(default_factory=tuple)
    unforeseeable_errors: tuple[str, ...] = field(default_factory=tuple)
    peak_sales_error_attribution: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidencePack:
    """
    Fully validated as-of evidence snapshot for one drug program.

    Attributes
    ----------
    asof_date : date
        The date as of which this evidence was contemporaneously observable.
    company : str
        Company name.
    ticker : str
        Stock ticker (uppercase, 1–6 chars).
    drug : str
        Drug name / identifier.
    indication : str
        Indication description.
    analysis_phase : str
        Development phase label (e.g. "phase_3").
    knowable_items : tuple[KnowableItem, ...]
        All evidence items tagged as knowable at the analysis date.
    not_knowable_items : tuple[NotKnowableItem, ...]
        All items explicitly excluded as hindsight.
    error_decomposition : Optional[ErrorDecomposition]
        Optional post-hoc error attribution block.
    source_path : Optional[pathlib.Path]
        File the pack was loaded from (None for in-memory packs).
    """
    asof_date: date
    company: str
    ticker: str
    drug: str
    indication: str
    analysis_phase: str
    knowable_items: tuple[KnowableItem, ...]
    not_knowable_items: tuple[NotKnowableItem, ...]
    error_decomposition: Optional[ErrorDecomposition] = None
    source_path: Optional[pathlib.Path] = None

    # ------------------------------------------------------------------ #
    # Convenience accessors                                                #
    # ------------------------------------------------------------------ #

    def knowable_by_key(self, key: str) -> Optional[KnowableItem]:
        """Return the knowable item with the given key, or None."""
        for item in self.knowable_items:
            if item.key == key:
                return item
        return None

    @property
    def high_confidence_count(self) -> int:
        """Number of knowable items with High confidence."""
        return sum(1 for k in self.knowable_items if k.confidence == "High")

    @property
    def medium_confidence_count(self) -> int:
        """Number of knowable items with Medium confidence."""
        return sum(1 for k in self.knowable_items if k.confidence == "Medium")

    @property
    def low_confidence_count(self) -> int:
        """Number of knowable items with Low confidence."""
        return sum(1 for k in self.knowable_items if k.confidence == "Low")

    @property
    def overall_confidence(self) -> str:
        """
        Aggregate confidence grade across all knowable items.

        Returns "High" if all items are High, "Low" if any item is Low,
        otherwise "Medium".
        """
        levels = {k.confidence for k in self.knowable_items}
        if "Low" in levels:
            return "Low"
        if levels == {"High"}:
            return "High"
        return "Medium"


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError:
    """One validation failure in an evidence YAML file."""
    path: str      # Dot-notation path to the failing field, e.g. "knowable.pricing_norms.confidence"
    message: str   # Human-readable explanation


@dataclass
class EvidenceValidationResult:
    """
    Outcome of validating one evidence YAML file.

    Attributes
    ----------
    ok : bool
        True if no errors were found.
    errors : list[ValidationError]
        All validation errors found.  Empty when ok=True.
    pack : Optional[EvidencePack]
        Parsed and validated pack; None when ok=False.
    """
    ok: bool
    errors: list[ValidationError]
    pack: Optional[EvidencePack] = None

    def error_messages(self) -> list[str]:
        """Return plain error messages as strings."""
        return [f"{e.path}: {e.message}" for e in self.errors]


# ---------------------------------------------------------------------------
# Validator class
# ---------------------------------------------------------------------------

class EvidenceValidator:
    """
    Load and validate as-of evidence YAML files.

    Usage
    -----
    >>> validator = EvidenceValidator()
    >>> result = validator.validate_file(pathlib.Path("research/evidence/vertex_ivacaftor_2010/asof.yaml"))
    >>> if result.ok:
    ...     pack = result.pack
    >>> results = validator.batch_validate_dir(pathlib.Path("research/evidence"))
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def validate_file(self, path: pathlib.Path) -> EvidenceValidationResult:
        """
        Load and validate a single evidence YAML file.

        Parameters
        ----------
        path : pathlib.Path
            Absolute or relative path to the YAML file.

        Returns
        -------
        EvidenceValidationResult
            ok=True with a populated pack, or ok=False with errors.
        """
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return EvidenceValidationResult(
                ok=False,
                errors=[ValidationError("file", f"File not found: {path}")],
            )
        except yaml.YAMLError as exc:
            return EvidenceValidationResult(
                ok=False,
                errors=[ValidationError("file", f"YAML parse error: {exc}")],
            )

        return self._validate_dict(raw, source_path=path)

    def validate_dict(self, raw: dict[str, Any]) -> EvidenceValidationResult:
        """
        Validate an already-loaded dict (useful for testing).

        Parameters
        ----------
        raw : dict
            Parsed YAML contents as a Python dict.

        Returns
        -------
        EvidenceValidationResult
        """
        return self._validate_dict(raw, source_path=None)

    def batch_validate_dir(
        self,
        directory: pathlib.Path,
        pattern: str = "**/asof.yaml",
    ) -> list[EvidenceValidationResult]:
        """
        Validate all evidence YAML files found under ``directory``.

        Parameters
        ----------
        directory : pathlib.Path
            Root directory to search recursively.
        pattern : str
            Glob pattern (default: ``**/asof.yaml``).

        Returns
        -------
        list[EvidenceValidationResult]
            One result per file found.  Empty list when no files match.
        """
        results = []
        for yaml_path in sorted(directory.glob(pattern)):
            results.append(self.validate_file(yaml_path))
        return results

    def load_pack(self, path: pathlib.Path) -> EvidencePack:
        """
        Load and validate a YAML file, raising ValueError on any error.

        Parameters
        ----------
        path : pathlib.Path
            Path to the evidence YAML.

        Returns
        -------
        EvidencePack

        Raises
        ------
        ValueError
            If the file fails validation.
        """
        result = self.validate_file(path)
        if not result.ok:
            msg = "; ".join(result.error_messages())
            raise ValueError(f"Evidence validation failed for {path}: {msg}")
        return result.pack  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _validate_dict(
        self,
        raw: Any,
        source_path: Optional[pathlib.Path],
    ) -> EvidenceValidationResult:
        errors: list[ValidationError] = []

        if not isinstance(raw, dict):
            return EvidenceValidationResult(
                ok=False,
                errors=[ValidationError("root", "Expected a YAML mapping at the top level")],
            )

        # -- Required top-level fields -----------------------------------
        for req in _REQUIRED_TOP_LEVEL:
            if req not in raw or raw[req] is None:
                errors.append(ValidationError(req, f"Required field '{req}' is missing or null"))

        if errors:
            # Can't proceed without the basics
            return EvidenceValidationResult(ok=False, errors=errors)

        # -- asof_date ---------------------------------------------------
        asof_date = self._parse_date(raw["asof_date"], "asof_date", errors)

        # -- ticker ------------------------------------------------------
        ticker = str(raw["ticker"]).strip()
        if not _TICKER_RE.match(ticker):
            errors.append(ValidationError(
                "ticker",
                f"Ticker '{ticker}' must be 1–6 uppercase letters (A-Z)",
            ))

        # -- company / drug / indication / analysis_phase ----------------
        for str_field in ("company", "drug", "indication", "analysis_phase"):
            if not str(raw.get(str_field, "")).strip():
                errors.append(ValidationError(str_field, f"'{str_field}' must be a non-empty string"))

        # -- knowable items ----------------------------------------------
        knowable_raw = raw.get("knowable", {})
        knowable_items = self._parse_knowable(knowable_raw, errors)

        # -- not_knowable items ------------------------------------------
        not_knowable_raw = raw.get("not_knowable", [])
        not_knowable_items = self._parse_not_knowable(not_knowable_raw, errors)

        # -- error_decomposition (optional) ------------------------------
        error_decomp = self._parse_error_decomposition(
            raw.get("error_decomposition"), errors
        )

        if errors:
            return EvidenceValidationResult(ok=False, errors=errors)

        pack = EvidencePack(
            asof_date=asof_date,  # type: ignore[arg-type]
            company=str(raw["company"]).strip(),
            ticker=ticker,
            drug=str(raw["drug"]).strip(),
            indication=str(raw["indication"]).strip(),
            analysis_phase=str(raw["analysis_phase"]).strip(),
            knowable_items=tuple(knowable_items),
            not_knowable_items=tuple(not_knowable_items),
            error_decomposition=error_decomp,
            source_path=source_path,
        )
        return EvidenceValidationResult(ok=True, errors=[], pack=pack)

    # -- Field-level parsers --------------------------------------------- #

    @staticmethod
    def _parse_date(
        value: Any,
        path: str,
        errors: list[ValidationError],
    ) -> Optional[date]:
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (ValueError, TypeError):
            errors.append(ValidationError(path, f"'{value}' is not a valid ISO date (YYYY-MM-DD)"))
            return None

    @staticmethod
    def _parse_knowable(
        raw: Any,
        errors: list[ValidationError],
    ) -> list[KnowableItem]:
        if not isinstance(raw, dict):
            errors.append(ValidationError("knowable", "Must be a YAML mapping (dict)"))
            return []
        if not raw:
            errors.append(ValidationError("knowable", "Must contain at least one evidence item"))
            return []

        items: list[KnowableItem] = []
        for key, value in raw.items():
            prefix = f"knowable.{key}"
            if not isinstance(value, dict):
                errors.append(ValidationError(prefix, "Each knowable item must be a mapping"))
                continue
            for req in _REQUIRED_KNOWABLE_ITEM:
                if req not in value or value[req] is None:
                    errors.append(ValidationError(
                        f"{prefix}.{req}",
                        f"Required field '{req}' is missing or null",
                    ))
            # Confidence enum check
            conf = value.get("confidence")
            if conf is not None and conf not in _VALID_CONFIDENCE:
                errors.append(ValidationError(
                    f"{prefix}.confidence",
                    f"'{conf}' is not a valid confidence level; expected one of {sorted(_VALID_CONFIDENCE)}",
                ))
            # Build item only if the required fields are present
            if all(req in value and value[req] is not None for req in _REQUIRED_KNOWABLE_ITEM):
                items.append(KnowableItem(
                    key=key,
                    source=str(value["source"]).strip(),
                    confidence=str(value["confidence"]),
                    description=str(value["description"]).strip() if value.get("description") else None,
                    notes=str(value["notes"]).strip() if value.get("notes") else None,
                ))
        return items

    @staticmethod
    def _parse_not_knowable(
        raw: Any,
        errors: list[ValidationError],
    ) -> list[NotKnowableItem]:
        if not isinstance(raw, list):
            errors.append(ValidationError("not_knowable", "Must be a YAML sequence (list)"))
            return []
        if not raw:
            errors.append(ValidationError(
                "not_knowable",
                "Must contain at least one hindsight exclusion",
            ))
            return []

        items: list[NotKnowableItem] = []
        for idx, entry in enumerate(raw):
            prefix = f"not_knowable[{idx}]"
            if not isinstance(entry, dict):
                errors.append(ValidationError(prefix, "Each entry must be a mapping"))
                continue
            for req in _REQUIRED_NOT_KNOWABLE_ITEM:
                if req not in entry or entry[req] is None:
                    errors.append(ValidationError(
                        f"{prefix}.{req}",
                        f"Required field '{req}' is missing or null",
                    ))
            if all(req in entry and entry[req] is not None for req in _REQUIRED_NOT_KNOWABLE_ITEM):
                items.append(NotKnowableItem(
                    item=str(entry["item"]).strip(),
                    actual_disclosure=str(entry["actual_disclosure"]).strip(),
                    error_if_used=str(entry["error_if_used"]).strip(),
                ))
        return items

    @staticmethod
    def _parse_error_decomposition(
        raw: Any,
        errors: list[ValidationError],
    ) -> Optional[ErrorDecomposition]:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            errors.append(ValidationError(
                "error_decomposition",
                "Must be a YAML mapping if present",
            ))
            return None

        def _to_str_tuple(val: Any) -> tuple[str, ...]:
            if isinstance(val, list):
                return tuple(str(v) for v in val)
            return ()

        peak_attr = raw.get("peak_sales_error_attribution") or {}

        return ErrorDecomposition(
            primary_error_driver=str(raw["primary_error_driver"]).strip()
            if raw.get("primary_error_driver")
            else None,
            foreseeable_errors=_to_str_tuple(raw.get("foreseeable_errors")),
            unforeseeable_errors=_to_str_tuple(raw.get("unforeseeable_errors")),
            peak_sales_error_attribution=dict(peak_attr) if isinstance(peak_attr, dict) else {},
        )


# ---------------------------------------------------------------------------
# Module-level convenience helpers
# ---------------------------------------------------------------------------

def load_evidence_pack(path: pathlib.Path) -> EvidencePack:
    """Load and validate a single evidence YAML; raise ValueError on failure."""
    return EvidenceValidator().load_pack(path)


def load_all_evidence_packs(
    directory: Optional[pathlib.Path] = None,
) -> list[EvidencePack]:
    """
    Load all valid evidence YAML files found under ``directory``.

    Silently skips invalid files (use ``batch_validate_dir`` for detailed errors).

    Parameters
    ----------
    directory : pathlib.Path, optional
        Root to search.  Defaults to ``research/evidence/`` relative to this
        file's package root.

    Returns
    -------
    list[EvidencePack]
        Only successfully validated packs.
    """
    if directory is None:
        # Navigate: src/bve/analysis/ → project root → research/evidence/
        directory = pathlib.Path(__file__).parent.parent.parent.parent / "research" / "evidence"

    validator = EvidenceValidator()
    return [
        r.pack
        for r in validator.batch_validate_dir(directory)
        if r.ok and r.pack is not None
    ]
