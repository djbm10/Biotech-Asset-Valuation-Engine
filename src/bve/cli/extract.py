"""
CLI entry point: extract a structured signal from one document.

Registered as ``bve-extract`` in pyproject.toml.

Usage examples
--------------
    # From a local press release text file
    bve-extract --text path/to/press_release.txt \\
                --asset-id asset-dupilumab-001 \\
                --company-id company-regn-001 \\
                --drug-name dupilumab \\
                --title "Regeneron FDA Approval Press Release" \\
                --backend anthropic

    # From a URL (fetches and strips HTML)
    bve-extract --url https://ir.example.com/news/2024-03-01 \\
                --asset-id asset-xyz-001 \\
                --company-id company-abc-001 \\
                --drug-name "XYZ-101" \\
                --backend openai \\
                --out-json result.json

    # Write result to JSON file
    bve-extract --text doc.txt --asset-id a1 --company-id c1 --out-json out.json

Exit codes
----------
0   ExtractionStatus.SUCCESS
1   Any non-SUCCESS status or argument error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from bve.intelligence.extraction.extractor import SignalExtractor
from bve.intelligence.extraction.llm_client import AnthropicClient, OpenAIClient
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionStatus


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE  = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def _fetch_url(url: str, timeout: int = 15) -> str:
    """HTTP GET + HTML strip."""
    try:
        import httpx
        resp = httpx.get(url, follow_redirects=True, timeout=timeout)
        resp.raise_for_status()
        return _strip_html(resp.text)
    except ImportError:
        pass
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "bve-extract/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _strip_html(r.read().decode("utf-8", errors="replace"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-extract",
        description="Extract a structured intelligence signal from one document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input source (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--text",
        metavar="FILE",
        help="Path to a plain-text file to extract from.",
    )
    source_group.add_argument(
        "--url",
        metavar="URL",
        help="HTTP URL to fetch and extract from (HTML is stripped).",
    )

    # Identity (required)
    parser.add_argument(
        "--asset-id",
        required=True,
        metavar="ID",
        help="Intelligence asset ID (EntityHints.asset_id).",
    )
    parser.add_argument(
        "--company-id",
        required=True,
        metavar="ID",
        help="Intelligence company ID (EntityHints.company_id).",
    )

    # Entity context (optional but improve extraction quality)
    parser.add_argument("--drug-name", metavar="NAME",  help="Drug INN or brand name.")
    parser.add_argument("--nct-id",    metavar="NCT",   help="ClinicalTrials.gov NCT ID.")
    parser.add_argument("--indication",metavar="TEXT",  help="Indication description.")
    parser.add_argument("--ticker",    metavar="TICK",  help="Company ticker symbol.")

    # Document metadata overrides
    parser.add_argument(
        "--title",
        metavar="TEXT",
        help="Document title (auto-extracted from URL; required for --text).",
    )
    parser.add_argument(
        "--source-type",
        metavar="TYPE",
        default="manual",
        choices=[
            "press_release", "sec_filing", "clinicaltrials_gov",
            "conference_abstract", "publication", "fda_website",
            "news_aggregator", "manual",
        ],
        help="Source type tag (default: manual).",
    )
    parser.add_argument(
        "--published-at",
        metavar="ISO",
        help="Publication date as ISO datetime (e.g., 2024-03-28T09:00:00Z).",
    )

    # LLM backend
    parser.add_argument(
        "--backend",
        choices=["anthropic", "openai"],
        default="anthropic",
        help="LLM backend to use (default: anthropic).",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help=(
            "Model identifier. Defaults: anthropic→claude-sonnet-4-6, "
            "openai→gpt-4o-2024-11-20."
        ),
    )
    parser.add_argument(
        "--api-key",
        metavar="KEY",
        help="API key (falls back to ANTHROPIC_API_KEY / OPENAI_API_KEY env vars).",
    )

    # Output
    parser.add_argument(
        "--out-json",
        metavar="FILE",
        help="Write ExtractionResult JSON to this file instead of stdout.",
    )
    parser.add_argument(
        "--event-id",
        metavar="ID",
        help="Event ID to embed in the StructuredSignal (auto-generated when omitted).",
    )

    return parser


def main() -> None:  # noqa: C901 (complexity OK for CLI)
    parser = _build_parser()
    args   = parser.parse_args()

    # ------------------------------------------------------------------ #
    # 1. Load document text
    # ------------------------------------------------------------------ #
    raw_text:    str
    source_url:  Optional[str] = None
    title:       str           = args.title or ""
    published_at: Optional[datetime] = None

    if args.published_at:
        try:
            published_at = datetime.fromisoformat(
                args.published_at.replace("Z", "+00:00")
            )
        except ValueError:
            print(
                f"Error: --published-at {args.published_at!r} is not a valid ISO datetime.",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.text:
        text_path = Path(args.text)
        if not text_path.exists():
            print(f"Error: file not found: {text_path}", file=sys.stderr)
            sys.exit(1)
        raw_text   = text_path.read_text(encoding="utf-8", errors="replace")
        source_url = f"file://{text_path.resolve()}"
        if not title:
            title = text_path.stem.replace("_", " ").replace("-", " ").title()
    else:
        # --url mode
        try:
            raw_text   = _fetch_url(args.url)
            source_url = args.url
            if not title:
                title = urlparse(args.url).path.rstrip("/").split("/")[-1] or args.url
        except Exception as exc:
            print(f"Error: failed to fetch {args.url!r}: {exc}", file=sys.stderr)
            sys.exit(1)

    if not raw_text.strip():
        print("Error: document text is empty.", file=sys.stderr)
        sys.exit(1)

    if not title:
        title = "Untitled document"

    # ------------------------------------------------------------------ #
    # 2. Build EntityHints and RawDocument
    # ------------------------------------------------------------------ #
    hints = EntityHints(
        asset_id=args.asset_id,
        company_id=args.company_id,
        drug_name=args.drug_name,
        nct_id=args.nct_id,
        indication=args.indication,
        ticker=args.ticker,
    )

    document = RawDocument.from_text(
        id=str(uuid.uuid4()),
        source=args.source_type,
        title=title,
        raw_text=raw_text,
        entity_hints=hints,
        source_url=source_url,
        published_at=published_at,
    )

    # ------------------------------------------------------------------ #
    # 3. Build LLM client
    # ------------------------------------------------------------------ #
    default_models = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o-2024-11-20"}
    model = args.model or default_models[args.backend]

    try:
        if args.backend == "anthropic":
            llm_client = AnthropicClient(model=model, api_key=args.api_key)
        else:
            llm_client = OpenAIClient(model=model, api_key=args.api_key)
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 4. Extract
    # ------------------------------------------------------------------ #
    extractor = SignalExtractor(llm_client=llm_client)
    event_id  = args.event_id or str(uuid.uuid4())

    print(
        f"Extracting from {len(raw_text):,}-char document using {model}...",
        file=sys.stderr,
    )

    result = extractor.extract(document, event_id=event_id)

    # ------------------------------------------------------------------ #
    # 5. Output
    # ------------------------------------------------------------------ #
    result_json = result.model_dump_json(indent=2)

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.write_text(result_json, encoding="utf-8")
        print(f"Result written to {out_path}", file=sys.stderr)
    else:
        print(result_json)

    # Print summary to stderr
    print(
        f"Status: {result.status.value}  |  "
        f"Event: {result.event_type_detected or 'n/a'}  |  "
        f"Confidence: {result.extraction_confidence:.2f}  |  "
        f"Latency: {result.latency_ms}ms",
        file=sys.stderr,
    )

    if result.validation_errors:
        for err in result.validation_errors:
            print(f"  Validation error: {err}", file=sys.stderr)

    sys.exit(0 if result.status == ExtractionStatus.SUCCESS else 1)


if __name__ == "__main__":
    main()
