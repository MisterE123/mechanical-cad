"""Explicit document validation, replay and export, separate from source Git."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from .errors import CADException
from .model import load_document, save_document


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a mechanical CAD document (millimetres).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "validate",
        "replay",
        "export-step",
        "export-stl",
        "check-geometry",
        "set-parameter",
    ):
        sub = subparsers.add_parser(command)
        sub.add_argument("document", type=Path)
        if command in {"replay", "export-step", "export-stl", "check-geometry"}:
            sub.add_argument(
                "--result-version",
                type=int,
                choices=(1, 2),
                default=1,
                help="Explicitly opt into typed sketch outputs (2); legacy default is 1.",
            )
        if command == "replay":
            sub.add_argument("--output", type=Path)
        elif command in {"export-step", "export-stl"}:
            sub.add_argument("output", type=Path)
        elif command == "set-parameter":
            sub.add_argument("name")
            sub.add_argument("value", help="Number or arithmetic expression")
            sub.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        document = load_document(args.document)
        if args.command == "validate":
            print(
                f"Valid schema and DAG: {document.name}, {len(document.features)} features, {document.content_hash}"
            )
            return 0
        if args.command == "set-parameter":
            changed = document.with_parameter(args.name, args.value)
            save_document(changed, args.output)
            print(f"Saved {args.output}")
            return 0
        if args.command == "replay":
            from .engine import regenerate
            from .kernel_ocp import OCPKernel

            replay = regenerate(document, OCPKernel(), result_version=args.result_version)
            text = json.dumps(replay.result, indent=2, allow_nan=False) + "\n"
            if args.output:
                args.output.write_text(text, encoding="utf-8")
            else:
                print(text, end="")
            return 0 if replay.ok else 1
        from .actions import run_geometry_action

        outcome = run_geometry_action(
            document,
            args.command.replace("-", "_"),
            destination=getattr(args, "output", None),
            result_version=args.result_version,
        )
        if not outcome["ok"]:
            error = outcome["error"]
            # Retain established CLI categories for geometry and filesystem
            # errors; the sidecar exposes the helper's finer action diagnostics.
            code = {
                "geometry_check_failed": "export_geometry_invalid",
                "export_failed": "export_geometry_invalid",
                "export_io_error": "io_error",
            }.get(error["code"], error["code"])
            raise CADException(code, error["message"])
        if args.command == "check-geometry":
            print(json.dumps(outcome["geometry_check"], indent=2, allow_nan=False))
            return 0
        print(f"Exported {args.output}")
        return 0
    except (CADException, OSError) as exc:
        code = exc.code if isinstance(exc, CADException) else "io_error"
        print(f"{code}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; explicit argv supports in-process testing.

    With omitted argv, this entry point owns the CLI process until teardown.
    Native STEP logs can flush after Python returns, so their stdout descriptor
    remains redirected while Python/argparse output uses a reserved descriptor.
    """
    if argv is not None:
        return _run(argv)
    sys.stdout.flush()
    with os.fdopen(os.dup(1), "w", encoding="utf-8") as output:
        os.dup2(2, 1)
        with contextlib.redirect_stdout(output):
            return _run()


if __name__ == "__main__":
    raise SystemExit(main())
