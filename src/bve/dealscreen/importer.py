"""Bring-your-own-landscape importer for CSV and XLSX provider exports.

Rules:
- Every imported value becomes a ``SOURCE_PROVIDED`` claim carrying its row, column, source
  system and dataset version. The raw row is kept verbatim.
- A row is rejected only for a stated reason, never dropped silently.
- A byte-identical repeat of a row is recorded as a duplicate of the first, not re-imported.
- One asset per (source system, external ID). Two rows with the same key are the same
  program reported twice, and any field they disagree on becomes a conflict for review.
  Rows with different keys are never merged here, even when they share a name or code
  (see ``identity.py``).
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from bve.data.data_quality import DataQualityChecker
from bve.dealscreen import DEALSCREEN_VERSION
from bve.dealscreen.mapping import DATE_FIELDS, LIST_FIELDS, REQUIRED_FIELDS, MappingProfile
from bve.dealscreen.models import (
    DuplicateRow,
    ImportedRow,
    ImportManifest,
    ImportResult,
    LandscapeAsset,
    RejectedRow,
    SourceClaim,
)


class LandscapeImportError(ValueError):
    """The file as a whole cannot be imported (unreadable, wrong headers, bad license)."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_rows(path: Path, sheet: str | None) -> tuple[list[str], Iterator[dict[str, str]]]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        handle = path.open(encoding="utf-8-sig", newline="")
        reader = csv.DictReader(handle)
        headers = [h.strip() for h in (reader.fieldnames or [])]

        def rows() -> Iterator[dict[str, str]]:
            with handle:
                for raw in reader:
                    if None in raw:
                        extra = raw.pop(None)  # type: ignore[call-overload]
                        raw["__extra_cells__"] = ";".join(str(v) for v in extra or [])
                    yield {str(k).strip(): _cell(v) for k, v in raw.items()}

        return headers, rows()
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LandscapeImportError(
                "reading .xlsx needs openpyxl: install the `dealscreen` extra"
            ) from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        worksheet = workbook[sheet] if sheet else workbook.worksheets[0]
        iterator = worksheet.iter_rows(values_only=True)
        try:
            header_row = next(iterator)
        except StopIteration as exc:
            raise LandscapeImportError(f"{path}: the sheet is empty") from exc
        headers = [_cell(h) for h in header_row]

        def xrows() -> Iterator[dict[str, str]]:
            for values in iterator:
                yield {headers[i]: _cell(v) for i, v in enumerate(values) if i < len(headers)}
            workbook.close()

        return headers, xrows()
    raise LandscapeImportError(f"{path}: unsupported file type {path.suffix!r} (use .csv or .xlsx)")


def _parse_date(text: str, formats: list[str]) -> date | None:
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _asset_id(source_system: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{source_system}|{external_id}".encode()).hexdigest()[:12]
    return f"ds:{digest}"


def split_list(text: str, separator: str) -> list[str]:
    return [part.strip() for part in text.split(separator) if part.strip()]


def import_landscape(
    path: str | Path,
    profile: MappingProfile,
    *,
    sheet: str | None = None,
) -> ImportResult:
    source = Path(path)
    if not source.exists():
        raise LandscapeImportError(f"{source}: file not found")
    headers, raw_rows = _read_rows(source, sheet)
    missing = [
        f"{field} (header {profile.columns[field]!r})"
        for field in profile.columns
        if profile.columns[field] not in headers
    ]
    if missing:
        raise LandscapeImportError(
            f"{source}: mapped headers not found: {', '.join(missing)}. "
            f"Headers in file: {headers}"
        )

    source_sha = _sha256_file(source)
    dataset_version = f"{profile.name}@{source_sha[:12]}"
    checker = DataQualityChecker()
    by_hash: dict[str, int] = {}
    rows: list[ImportedRow] = []
    rejected: list[RejectedRow] = []
    duplicates: list[DuplicateRow] = []
    warnings: list[str] = []
    rows_read = 0

    for index, raw in enumerate(raw_rows, start=1):
        if not any(raw.values()):
            continue  # a blank spreadsheet line is not a record
        rows_read += 1
        row_hash = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        if row_hash in by_hash:
            duplicates.append(
                DuplicateRow(row_number=index, row_hash=row_hash, duplicate_of_row=by_hash[row_hash])
            )
            continue
        fields = {field: raw.get(header, "") for field, header in profile.columns.items()}
        reasons: list[str] = []
        if raw.get("__extra_cells__"):
            reasons.append("row has more cells than the header (malformed CSV quoting?)")
        quality = checker.validate(
            profile.name,
            {k: (v or None) for k, v in fields.items()},
            required_fields=list(REQUIRED_FIELDS),
            primary_key_field="external_id",
        )
        reasons.extend(quality.errors)
        reasons.extend(
            f"required field {field!r} is empty" for field in REQUIRED_FIELDS if not fields.get(field)
        )
        for field in DATE_FIELDS:
            if fields.get(field) and _parse_date(fields[field], profile.date_formats) is None:
                reasons.append(
                    f"{field} {fields[field]!r} does not match date formats {profile.date_formats}"
                )
        if reasons:
            rejected.append(
                RejectedRow(row_number=index, row_hash=row_hash, raw=raw, reasons=sorted(set(reasons)))
            )
            continue
        by_hash[row_hash] = index
        rows.append(ImportedRow(row_number=index, row_hash=row_hash, raw=raw, fields=fields))

    assets = _group_assets(rows, profile, dataset_version)
    if not rows:
        warnings.append("no rows were imported")
    manifest = ImportManifest(
        dataset_version=dataset_version,
        source_system=profile.source_system,
        source_file=str(source),
        source_sha256=source_sha,
        profile_name=profile.name,
        profile_sha256=profile.sha256(),
        license_status=profile.license_status,
        allowed_use=profile.allowed_use,
        rows_read=rows_read,
        rows_imported=len(rows),
        rows_rejected=len(rejected),
        rows_exact_duplicate=len(duplicates),
        assets=len(assets),
        importer_version=DEALSCREEN_VERSION,
    )
    if rows_read != len(rows) + len(rejected) + len(duplicates):  # pragma: no cover - invariant
        raise AssertionError("row accounting does not reconcile")
    return ImportResult(
        manifest=manifest, rows=rows, rejected=rejected, duplicates=duplicates,
        assets=assets, warnings=warnings,
    )


def _group_assets(
    rows: list[ImportedRow], profile: MappingProfile, dataset_version: str
) -> list[LandscapeAsset]:
    grouped: dict[tuple[str, str], list[ImportedRow]] = {}
    for row in rows:
        system = row.fields.get("source_system") or profile.source_system
        grouped.setdefault((system, row.fields["external_id"]), []).append(row)

    assets: list[LandscapeAsset] = []
    for (system, external_id), members in grouped.items():
        asset_id = _asset_id(system, external_id)
        claims: list[SourceClaim] = []
        for row in members:
            source_date = _parse_date(row.fields.get("source_date", ""), profile.date_formats)
            reference = row.fields.get("source_reference") or None
            for field, value in row.fields.items():
                if not value or field in {"external_id", "source_system"}:
                    continue
                claims.append(
                    SourceClaim(
                        claim_id=f"{asset_id}:r{row.row_number}:{field}",
                        asset_id=asset_id,
                        field=field,
                        value_as_written=value,
                        source_system=system,
                        dataset_version=dataset_version,
                        row_number=row.row_number,
                        column=profile.columns[field],
                        source_reference=reference,
                        source_date=source_date,
                    )
                )
        first = members[0].fields
        aliases: list[str] = []
        for row in members:
            for alias in split_list(row.fields.get("aliases", ""), profile.list_separator):
                if alias not in aliases and alias != first["program_name"]:
                    aliases.append(alias)
        assets.append(
            LandscapeAsset(
                asset_id=asset_id,
                source_system=system,
                external_id=external_id,
                program_name=first["program_name"],
                aliases=aliases,
                company=first.get("company") or None,
                row_numbers=[row.row_number for row in members],
                claims=claims,
            )
        )
    return assets


__all__ = ["LIST_FIELDS", "LandscapeImportError", "import_landscape", "split_list"]
