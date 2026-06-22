"""
CLI entry point: bve-replay-document

Re-run signal extraction on raw document already stored in the knowledge database.
Useful for debugging extraction failures, testing model improvements, and auditing
what the extractor produces for a specific document.

This command does NOT persist results by default — use --save to write them back
into the knowledge store.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Re-run extraction on stored raw document")
    parser.add_argument("--db", required=True, help="Path to knowledge SQLite database")
    parser.add_argument(
        "--document-id",
        required=True,
        help="document_id (raw_documents.id) to replay",
    )
    parser.add_argument(
        "--backend",
        choices=["anthropic", "openai", "fake"],
        default="fake",
        help="LLM backend for extraction (default: fake)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override (e.g. claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist extraction result and any created signal to the knowledge store",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write extraction result JSON to file path (default: stdout)",
    )
    parser.add_argument(
        "--extract-science-evidence",
        action="store_true",
        help="Extract validated ScienceEvidenceBundle from the document",
    )
    parser.add_argument(
        "--science-thesis",
        action="store_true",
        help="Build compact ScienceThesis summary from extracted science evidence",
    )
    parser.add_argument(
        "--science-evidence-output-dir",
        default=None,
        help="Write a replayable ScienceEvidenceArtifact JSON to this directory",
    )
    parser.add_argument(
        "--science-evidence-artifact",
        default=None,
        help="Load ScienceEvidenceArtifact JSON instead of calling the science extractor",
    )
    parser.add_argument(
        "--science-evidence-artifact-hash-policy",
        choices=["warn", "fail", "ignore"],
        default="warn",
        help="Behavior when loaded artifact document_hash differs from current document text",
    )
    parser.add_argument("--verbose", action="store_true", help="Print full JSON result")
    return parser


def _extract_science_evidence_output(
    doc,
    llm_client,
    *,
    include_science_thesis: bool = False,
    artifact_output_dir: str | Path | None = None,
    artifact_path: str | Path | None = None,
    artifact_hash_policy: str = "warn",
    model_id: str | None = None,
) -> dict:
    """Return JSON-safe science evidence extraction output for one document."""
    from bve.intelligence.science_evidence_artifact import (
        artifact_path_for_document,
        build_science_evidence_artifact,
        load_science_evidence_artifact,
        save_science_evidence_artifact,
    )
    from bve.intelligence.science_evidence_llm_extractor import ScienceEvidenceLLMExtractor
    from bve.intelligence.science_evidence_surface import build_compact_evidence_surface

    hints = doc.entity_hints
    written_artifact_path: Path | None = None
    artifact_warnings: list[str] = []

    if artifact_path is not None:
        artifact = load_science_evidence_artifact(
            artifact_path,
            current_document_text=doc.raw_text,
            mismatch_policy=artifact_hash_policy,
        )
        bundle = artifact.bundle
        artifact_warnings = list(artifact.artifact_warnings)
        loaded_artifact_path = str(artifact_path)
    else:
        bundle = ScienceEvidenceLLMExtractor(llm_client).extract_bundle(
            asset_id=hints.asset_id,
            asset_name=hints.drug_name or "",
            indication=hints.indication or "",
            source_id=doc.id,
            source_uri=doc.source_url,
            source_type=doc.source,
            document_title=doc.title,
            published_at=doc.published_at.isoformat() if doc.published_at else None,
            document_text=doc.raw_text,
        )
        loaded_artifact_path = None
        if artifact_output_dir is not None:
            artifact = build_science_evidence_artifact(
                bundle,
                document_text=doc.raw_text,
                source_document_id=doc.id,
                asset_id=hints.asset_id,
                model_id=model_id,
            )
            written_artifact_path = artifact_path_for_document(
                artifact_output_dir,
                asset_id=hints.asset_id or "unknown_asset",
                document_id=doc.id,
            )
            save_science_evidence_artifact(artifact, written_artifact_path)
            artifact_warnings = list(artifact.artifact_warnings)

    output = {
        "science_evidence_bundle": bundle.model_dump(mode="json"),
        "science_evidence_warnings": list(bundle.bundle_warnings),
        "science_evidence_surface": build_compact_evidence_surface(bundle),
        "science_evidence_artifact_path": str(written_artifact_path)
        if written_artifact_path is not None
        else loaded_artifact_path,
        "science_evidence_artifact_warnings": artifact_warnings,
    }

    if include_science_thesis:
        from bve.intelligence.science_thesis_builder import ScienceThesisBuilder
        from bve.intelligence.science_thesis_summary import build_science_summary

        thesis = ScienceThesisBuilder().from_existing_evidence(science_evidence_bundle=bundle)
        output["science_thesis_summary"] = build_science_summary(
            thesis,
            modifier_applied=False,
        )

    return output


def main() -> None:
    args = _build_parser().parse_args()

    if args.science_thesis and not args.extract_science_evidence:
        print("ERROR: --science-thesis requires --extract-science-evidence", file=sys.stderr)
        sys.exit(2)
    if args.science_evidence_output_dir and not args.extract_science_evidence:
        print(
            "ERROR: --science-evidence-output-dir requires --extract-science-evidence",
            file=sys.stderr,
        )
        sys.exit(2)
    if args.science_evidence_artifact and not args.extract_science_evidence:
        print(
            "ERROR: --science-evidence-artifact requires --extract-science-evidence",
            file=sys.stderr,
        )
        sys.exit(2)

    from bve.connectors.llm_client import AnthropicClient, FakeLLMClient, OpenAIClient
    from bve.intelligence.extraction.extractor import SignalExtractor
    from bve.intelligence.extraction.knowledge_store import KnowledgeStore
    from bve.intelligence.extraction.raw_document import RawDocument
    from bve.pipeline.watchlist_runner import ExtractionRuntimeConfig

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    knowledge = KnowledgeStore(str(db_path))

    row = knowledge._conn.execute(
        "SELECT payload_json FROM raw_documents WHERE id = ?",
        (args.document_id,),
    ).fetchone()
    if row is None:
        print(f"Document '{args.document_id}' not found in {db_path}", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(row[0])
    doc = RawDocument.model_validate(payload)

    ext_cfg = ExtractionRuntimeConfig(backend=args.backend, model=args.model)
    if ext_cfg.backend == "anthropic":
        llm = AnthropicClient(model=ext_cfg.model or "claude-sonnet-4-6")
    elif ext_cfg.backend == "openai":
        llm = OpenAIClient(model=ext_cfg.model or "gpt-4o")
    else:
        llm = FakeLLMClient()

    extractor = SignalExtractor(llm_client=llm)

    print(f"Replaying extraction for document: {doc.id}")
    print(f"  source: {doc.source}")
    print(f"  asset: {doc.entity_hints.asset_id} / {doc.entity_hints.company_id}")
    print(f"  title: {doc.title[:80]}")
    print()

    result = extractor.extract(doc)
    output_data = result.model_dump(mode="json")

    if args.extract_science_evidence:
        output_data.update(
            _extract_science_evidence_output(
                doc,
                llm,
                include_science_thesis=args.science_thesis,
                artifact_output_dir=args.science_evidence_output_dir,
                artifact_path=args.science_evidence_artifact,
                artifact_hash_policy=args.science_evidence_artifact_hash_policy,
                model_id=ext_cfg.model,
            )
        )

    if args.save:
        from bve.intelligence.knowledge_layer import SourceTrace

        trace = SourceTrace(
            source_type="replay",
            source_ref=f"replay:document:{doc.id}",
        )
        knowledge.add_extraction_result(
            result,
            source_trace=trace,
            raw_document_id=doc.id,
        )
        print(f"Saved extraction result: {result.id}")
        if result.signal:
            knowledge.add_structured_signal(
                result.signal,
                source_trace=trace,
                extraction_result_id=result.id,
            )
            print(f"Saved structured signal: {result.signal.id}")
        else:
            print("No signal produced — extraction result saved, no signal.")

    output_json = json.dumps(output_data, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"\nResult written to: {args.output}")
    else:
        print(output_json)

    knowledge.close()


if __name__ == "__main__":
    main()
