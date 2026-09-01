"""English command-line interface for production extraction."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .api import extract
from .categories import PUBLIC_CATEGORIES, WORK_TEXT


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="segnatura",
        description="Extract classified text and stable citations from EPUB files.")
    parser.add_argument("epub", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--format", choices=("text", "units-json", "rag-jsonl"),
                        default="text")
    parser.add_argument(
        "--category", action="append", choices=(*PUBLIC_CATEGORIES, "all"),
        help=("category to extract; repeat for multiple categories "
              "(default: work_text)"),
    )
    parser.add_argument(
        "--edition-profile", dest="edition_profile", type=Path,
        help="edition-specific .segnatura.json correction profile",
    )
    parser.add_argument("--max-tokens", type=int, default=350)
    parser.add_argument("--min-tokens", type=int, default=80)
    parser.add_argument("--overlap-tokens", type=int, default=40)
    parser.add_argument("--context-tokens", type=int, default=1200)
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser


def _render(book, args) -> str:
    selected = tuple(args.category or (WORK_TEXT,))
    categories = "all" if "all" in selected else selected
    if args.format == "text":
        return book.text(categories=categories)
    if args.format == "units-json":
        payload = {
            "schema": "segnatura-extraction-1",
            "book": book.book_metadata(),
            "units": [unit.to_dict() for unit in book.units(
                categories=categories)],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    records = book.rag_records(
        categories=categories,
        max_tokens=args.max_tokens,
        min_tokens=args.min_tokens,
        overlap_tokens=args.overlap_tokens,
        context_tokens=args.context_tokens,
    )
    return "\n".join(json.dumps(record.to_dict(), ensure_ascii=False)
                     for record in records)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        book = extract(args.epub, edition_profile=args.edition_profile)
        output = _render(book, args)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Wrote {args.output}", file=sys.stderr)
        else:
            print(output)
        return 0
    except Exception as error:
        print(f"segnatura: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    main()
