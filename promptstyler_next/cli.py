"""Portable CLI. All commands use the same validated Engine as the integrations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import Engine, StylerError, __version__
from .catalog import Pack
from .validation import parse_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="promptstyler-next", description="Model-aware creative styling, offline."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--pack", type=Path, action="append", default=[], help="Add a trusted local JSON pack (repeatable)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("styles", help="Search style metadata.")
    listing.add_argument("--query", default="")
    listing.add_argument("--category")
    listing.add_argument("--model")
    listing.add_argument("--kind", choices=("style", "grade", "modifier"))
    listing.add_argument("--limit", type=int, default=100)
    commands.add_parser("profiles", help="List model capabilities and source citations.")
    compose = commands.add_parser("compose", help="Compose a JSON recipe from a file or stdin.")
    compose.add_argument("recipe", nargs="?", default="-", help="JSON file, or - for stdin.")
    validate = commands.add_parser("validate", help="Validate JSON packs without executing code.")
    validate.add_argument("paths", nargs="+", type=Path)
    recommend = commands.add_parser("recommend", help="Rank styles by metadata overlap.")
    recommend.add_argument("prompt")
    recommend.add_argument("--model", default="generic")
    recommend.add_argument("--limit", type=int, default=6)
    server_parser = commands.add_parser("serve", help="Start the local style workbench and API.")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args(argv)
    try:
        engine = Engine.builtin().with_packs(args.pack)
        result: Any
        if args.command == "styles":
            result = engine.list_styles(
                query=args.query, category=args.category, model=args.model, kind=args.kind, limit=args.limit
            )
        elif args.command == "profiles":
            result = engine.profiles()
        elif args.command == "compose":
            if args.recipe == "-":
                raw = sys.stdin.buffer.read(65537)
            else:
                with Path(args.recipe).open("rb") as handle:
                    raw = handle.read(65537)
            request = parse_json(raw)
            if not isinstance(request, dict):
                raise StylerError("invalid_type", "Recipe must be a JSON object.", "recipe")
            result = engine.compose(request).to_dict()
        elif args.command == "validate":
            packs = [Pack.load(path) for path in args.paths]
            # Test collisions and model references through exactly the loading boundary.
            Engine.from_packs(args.paths)
            result = [{"id": pack.id, "version": pack.version, "styles": len(pack.styles)} for pack in packs]
        elif args.command == "recommend":
            result = engine.recommend(prompt=args.prompt, model=args.model, limit=args.limit)
        else:
            from .service import serve

            serve(engine, host=args.host, port=args.port)
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except StylerError as exc:
        print(json.dumps({"error": exc.to_dict()}), file=sys.stderr)
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "io_error",
                        "message": "Cannot access the requested local file or address.",
                        "path": "",
                    }
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
