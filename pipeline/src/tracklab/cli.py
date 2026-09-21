"""Command-line interface for tracklab.

Wires up the five subcommands described in tasks/todo.md. Each handler is a
stub for now; its logic lands in the task that owns it (see tasks/todo.md).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from tracklab.ingest.fetch import freeze_source, ingest_source, make_client
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import Source, load_manifest, save_manifest

_Handler = Callable[[argparse.Namespace], int]


def _source(args: argparse.Namespace) -> Source:
    try:
        return load_manifest(args.manifest).source(args.source_id)
    except KeyError as exc:
        sys.exit(f"tracklab: {exc.args[0]}")


def _cmd_ingest(args: argparse.Namespace) -> int:
    source = _source(args)
    raw_root: Path = args.data_dir / "raw" / source.source_id
    if args.from_existing is not None:
        receipt = ingest_local(source, args.from_existing, raw_root)
    else:
        with make_client() as client:
            receipt = ingest_source(client, source, raw_root)
    print(receipt.summary)
    return 1 if receipt.failed else 0


def _cmd_freeze(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    source = _source(args)
    if args.from_existing is not None:
        frozen = freeze_local(args.from_existing, source)
    else:
        with make_client() as client:
            frozen = freeze_source(client, source)
    manifest.replace(frozen)
    save_manifest(manifest, args.manifest)
    lfs = sum(1 for f in frozen.files if f.lfs)
    print(f"commit={frozen.commit} files={len(frozen.files)} lfs={lfs}")
    return 0


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
    ingest.add_argument("source_id", help="Source id from the manifest, e.g. opendata-football.")
    ingest.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest/sources.json"),
        help="Path to sources.json (default: manifest/sources.json).",
    )
    ingest.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Data root; files land under <data-dir>/raw/<source_id>/ (default: data).",
    )
    ingest.add_argument(
        "--from-existing",
        type=Path,
        default=None,
        help="Verify a source in place inside an existing clone, instead of downloading.",
    )
    ingest.set_defaults(func=_cmd_ingest)

    freeze = subparsers.add_parser("freeze", help="Pin a source's commit and file hashes.")
    freeze.add_argument("source_id", help="Source id from the manifest, e.g. opendata-football.")
    freeze.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest/sources.json"),
        help="Path to sources.json (default: manifest/sources.json).",
    )
    freeze.add_argument(
        "--from-existing",
        type=Path,
        default=None,
        help="Freeze from an existing local clone's HEAD instead of the GitHub API.",
    )
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
