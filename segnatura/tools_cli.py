"""Launcher for the optional Edition Profile application."""
from __future__ import annotations

import argparse
from pathlib import Path


def edition_profile_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="segnatura-edition-profile",
        description=("Create edition-specific, human-approved correction "
                     "files."))
    parser.add_argument(
        "root", nargs="?", type=Path,
        default=None,
        help=("optional folder containing EPUB files; omit it to choose "
              "an EPUB from the application"),
    )
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    audit = parser.add_argument_group("optional independent LLM audit")
    audit.add_argument(
        "--audit-lm-studio", metavar="MODEL",
        help="audit every EPUB block with the model loaded in LM Studio",
    )
    audit.add_argument("--audit-base-url", default="http://localhost:1234/v1")
    audit.add_argument("--audit-api-key", default="lm-studio")
    audit.add_argument(
        "--audit-timeout", type=float, default=900.0,
        help="seconds allowed for each model call (default: 900)",
    )
    audit.add_argument("--audit-reasoning-effort")
    args = parser.parse_args(argv)
    from .gold_app import run
    root = args.root or Path.cwd()
    backend = None
    if args.audit_lm_studio:
        from .llm import OpenAICompatibleBackend
        backend = OpenAICompatibleBackend.lm_studio(
            args.audit_lm_studio,
            base_url=args.audit_base_url,
            api_key=args.audit_api_key,
            timeout=args.audit_timeout,
            reasoning_effort=args.audit_reasoning_effort,
            max_tokens=6000,
            cache=None,
        )
    run(root, port=args.port,
        open_browser=not args.no_browser, audit_backend=backend)
    return 0
