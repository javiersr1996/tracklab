"""Command-line interface for tracklab.

Wires up the five subcommands described in tasks/todo.md. Each handler is a
stub for now; its logic lands in the task that owns it (see tasks/todo.md).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from tracklab.bronze.basketball.tracking import build_tracking as build_basketball_tracking
from tracklab.bronze.common import raw_root_for
from tracklab.formats.football_report import freeze_football
from tracklab.ingest.fetch import freeze_source, ingest_source, make_client
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import Source, load_manifest, save_manifest

_Handler = Callable[[argparse.Namespace], int]
_DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parent / "bronze" / "schemas"

# (sport, table group) -> builder. Each bronze task registers its group here; asking
# for a group that is not registered fails before anything is built.
_BronzeBuilder = Callable[[Source, Path, Path], object]
_BRONZE_BUILDERS: dict[tuple[str, str], _BronzeBuilder] = {
    ("basketball", "tracking"): build_basketball_tracking,
}


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
    manifest = load_manifest(args.manifest)
    sources = [s for s in manifest.sources if s.sport == args.sport]
    if len(sources) != 1:
        sys.exit(
            f"tracklab: expected one {args.sport} source in the manifest, found {len(sources)}"
        )
    source = sources[0]
    groups = [g for g in args.tables.split(",") if g] if args.tables else None
    known = sorted(g for sport, g in _BRONZE_BUILDERS if sport == args.sport)
    if groups is None:
        groups = known
    unknown = [g for g in groups if (args.sport, g) not in _BRONZE_BUILDERS]
    if unknown:
        sys.exit(f"tracklab: no bronze builder for {args.sport} {unknown} (known: {known})")
    raw_root = raw_root_for(args.data_dir, source.source_id)
    started = time.perf_counter()
    for group in groups:
        print(f"bronze {args.sport} {group}: {raw_root}")
        _BRONZE_BUILDERS[(args.sport, group)](source, raw_root, args.data_dir)
    print(f"total seconds={time.perf_counter() - started:.1f}")
    return 0


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
    bronze.add_argument("sport", choices=("football", "basketball"))
    bronze.add_argument(
        "--tables",
        default=None,
        help="Comma-separated table groups to build, e.g. tracking (default: every group).",
    )
    bronze.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest/sources.json"),
        help="Path to sources.json (default: manifest/sources.json).",
    )
    bronze.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Data root: reads raw/<source_id>/, writes bronze/<sport>/<table>/ (default: data).",
    )
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
