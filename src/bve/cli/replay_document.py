"""
CLI entry point: bve-replay-document

Re-run signal extraction on a raw document that is already stored in the
knowledge database. Useful for debugging extraction failures, testing model
improvements, and auditing what the extractor produces for a specific document.

The command does NOT persist results by default — use --save to write them
back into the knowledge store.

Usage
-----
    bve-replay-document --db outputs/intelligence_phase2/knowledge.db \\
        --document-id <id>

    bve-replay-document --db outputs/intelligence_phase2/knowledge.db \\
        --document-id <id> --save --verbose

    bve-replay-document --db outputs/intelligence_phase2/knowledge.db \\
        --document-id <id> --backend anthropic --model claude-sonnet-4-6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Re-run extraction on a stored raw document"
    )
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
        help="Persist the extraction result and any created signal to the knowledge store",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write extraction result JSON to this file path (default: stdout)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    import logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.extraction.extractor import SignalExtractor
    from bve.intelligence.extraction.llm_client import (
        AnthropicClient,
        FakeLLMClient,
        OpenAIClient,
    )
    from bve.intelligence.extraction.raw_document import RawDocument
    from bve.pipeline.watchlist_runner import ExtractionRuntimeConfig

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    knowledge = KnowledgeStore(str(db_path))

    # Load the raw document from the knowledge store.
    row = knowledge._conn.execute(
        "SELECT payload_json FROM raw_documents WHERE id = ?",
        (args.document_id,),
    ).fetchone()
    if row is None:
        print(f"Document '{args.document_id}' not found in {db_path}", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(row[0])
    doc = RawDocument.model_validate(payload)

    # Build the extractor.
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
    print(f"  asset:  {doc.entity_hints.asset_id} / {doc.entity_hints.company_id}")
    print(f"  title:  {doc.title[:80]}")
    print()

    result = extractor.extract(doc)

    output_data = result.model_dump(mode="json")

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
