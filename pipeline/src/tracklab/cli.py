"""Command-line interface for tracklab.

Wires up the five subcommands described in tasks/todo.md. Each handler is a
stub for now; its logic lands in the task that owns it (see tasks/todo.md).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from tracklab.formats.football_report import freeze_football
from tracklab.ingest.fetch import freeze_source, ingest_source, make_client
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import Source, load_manifest, save_manifest

_Handler = Callable[[argparse.Namespace], int]
_DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parent / "bronze" / "schemas"


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


def _cmd_freeze_schema(args: argparse.Namespace) -> int:
    if args.sport != "football":
        raise NotImplementedError(f"tracklab freeze-schema {args.sport}: not implemented yet")
    return freeze_football(
        manifest_path=args.manifest,
        data_dir=args.data_dir,
        reports_dir=args.reports_dir,
        docs_dir=args.docs_dir,
        schemas_dir=args.schemas_dir or _DEFAULT_SCHEMAS_DIR / args.sport,
        workers=args.workers,
    )


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

    freeze_schema = subparsers.add_parser(
        "freeze-schema",
        help="Probe a raw bundle, freeze its CSV schemas, write docs/formats/<sport>.md.",
    )
    freeze_schema.add_argument("sport", choices=("football", "basketball"))
    freeze_schema.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest/sources.json"),
        help="Path to sources.json (default: manifest/sources.json).",
    )
    freeze_schema.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Data root holding raw/<source_id>/ (default: data).",
    )
    freeze_schema.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where the per-match report CSV goes (default: reports).",
    )
    freeze_schema.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("../docs/formats"),
        help="Where <sport>.md goes (default: ../docs/formats, the repo's docs from pipeline/).",
    )
    freeze_schema.add_argument(
        "--schemas-dir",
        type=Path,
        default=None,
        help="Where *.schema.json go (default: src/tracklab/bronze/schemas/<sport>).",
    )
    freeze_schema.add_argument(
        "--workers",
        type=int,
        default=max(1, min(8, os.cpu_count() or 1)),
        help="Matches probed in parallel (default: min(8, CPUs)).",
    )
    freeze_schema.set_defaults(func=_cmd_freeze_schema)

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
