"""Command-line interface for tracklab.

Wires up the five subcommands described in tasks/todo.md. Each handler is a
stub for now; its logic lands in the task that owns it (see tasks/todo.md).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

_Handler = Callable[[argparse.Namespace], int]


def _cmd_ingest(args: argparse.Namespace) -> int:
    raise NotImplementedError("tracklab ingest: not implemented yet")


def _cmd_freeze(args: argparse.Namespace) -> int:
    raise NotImplementedError("tracklab freeze: not implemented yet")


def _cmd_bronze(args: argparse.Namespace) -> int:
    raise NotImplementedError("tracklab bronze: not implemented yet")


def _cmd_publish(args: argparse.Namespace) -> int:
    raise NotImplementedError("tracklab publish: not implemented yet")


def _cmd_stats(args: argparse.Namespace) -> int:
    raise NotImplementedError("tracklab stats: not implemented yet")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tracklab", description="Track Lab data pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Download and verify a source's raw files.")
    ingest.set_defaults(func=_cmd_ingest)

    freeze = subparsers.add_parser("freeze", help="Pin a source's commit and file hashes.")
    freeze.set_defaults(func=_cmd_freeze)

    bronze = subparsers.add_parser("bronze", help="Convert verified raw files to typed Parquet.")
    bronze.set_defaults(func=_cmd_bronze)

    publish = subparsers.add_parser("publish", help="Write JSON for the web from silver.")
    publish.set_defaults(func=_cmd_publish)

    stats = subparsers.add_parser("stats", help="Compute and write stats.json.")
    stats.set_defaults(func=_cmd_stats)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: _Handler = args.func
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
