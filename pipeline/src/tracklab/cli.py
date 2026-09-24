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

from tracklab.bronze.basketball.aggregates import build_aggregates as build_basketball_aggregates
from tracklab.bronze.basketball.events import build_events as build_basketball_events
from tracklab.bronze.basketball.meta import build_meta as build_basketball_meta
from tracklab.bronze.basketball.tracking import build_tracking as build_basketball_tracking
from tracklab.bronze.common import raw_root_for
from tracklab.bronze.football.aggregates import build_aggregates as build_football_aggregates
from tracklab.bronze.football.events import build_events as build_football_events
from tracklab.bronze.football.meta import build_meta as build_football_meta
from tracklab.bronze.football.tracking import build_tracking as build_football_tracking
from tracklab.fixtures import run_fixtures
from tracklab.formats.basketball import freeze_basketball
from tracklab.formats.football_report import freeze_football
from tracklab.ingest.fetch import freeze_source, ingest_source, make_client
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import Source, load_manifest, save_manifest
from tracklab.paths import data_root
from tracklab.silver.orientation import SPORTS, run_orientation
from tracklab.silver.possessions import run_possessions
from tracklab.silver.stats import run_stats

_Handler = Callable[[argparse.Namespace], int]
_DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parent / "bronze" / "schemas"

# (sport, table group) -> builder. Each bronze task registers its group here; asking
# for a group that is not registered fails before anything is built.
_BronzeBuilder = Callable[[Source, Path, Path], object]
BRONZE_BUILDERS: dict[tuple[str, str], _BronzeBuilder] = {
    ("basketball", "tracking"): build_basketball_tracking,
    ("basketball", "events"): build_basketball_events,
    ("basketball", "meta"): build_basketball_meta,
    ("basketball", "aggregates"): build_basketball_aggregates,
    ("football", "tracking"): build_football_tracking,
    ("football", "meta"): build_football_meta,
    ("football", "events"): build_football_events,
    ("football", "aggregates"): build_football_aggregates,
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
    schemas_dir = args.schemas_dir or _DEFAULT_SCHEMAS_DIR / args.sport
    if args.sport == "football":
        return freeze_football(
            manifest_path=args.manifest,
            data_dir=args.data_dir,
            reports_dir=args.reports_dir,
            docs_dir=args.docs_dir,
            schemas_dir=schemas_dir,
            workers=args.workers,
        )
    if args.sport == "basketball":
        return freeze_basketball(
            manifest_path=args.manifest,
            data_dir=args.data_dir,
            reports_dir=args.reports_dir,
            docs_dir=args.docs_dir,
            schemas_dir=schemas_dir,
        )
    raise NotImplementedError(f"tracklab freeze-schema {args.sport}: not implemented yet")


def _cmd_bronze(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    sources = [s for s in manifest.sources if s.sport == args.sport]
    if len(sources) != 1:
        sys.exit(
            f"tracklab: expected one {args.sport} source in the manifest, found {len(sources)}"
        )
    source = sources[0]
    groups = [g for g in args.tables.split(",") if g] if args.tables else None
    known = sorted(g for sport, g in BRONZE_BUILDERS if sport == args.sport)
    if groups is None:
        groups = known
    unknown = [g for g in groups if (args.sport, g) not in BRONZE_BUILDERS]
    if unknown:
        sys.exit(f"tracklab: no bronze builder for {args.sport} {unknown} (known: {known})")
    raw_root = raw_root_for(args.data_dir, source.source_id)
    started = time.perf_counter()
    for group in groups:
        print(f"bronze {args.sport} {group}: {raw_root}")
        BRONZE_BUILDERS[(args.sport, group)](source, raw_root, args.data_dir)
    print(f"total seconds={time.perf_counter() - started:.1f}")
    return 0


def _cmd_orientation(args: argparse.Namespace) -> int:
    sports = SPORTS if args.sport == "both" else (args.sport,)
    return run_orientation(
        sports=sports,
        manifest_path=args.manifest,
        data_dir=args.data_dir,
        reports_dir=args.reports_dir,
        docs_dir=args.docs_dir,
    )


def _cmd_possessions(args: argparse.Namespace) -> int:
    return run_possessions(data_dir=args.data_dir, reports_dir=args.reports_dir)


def _cmd_publish(args: argparse.Namespace) -> int:
    raise NotImplementedError("tracklab publish: not implemented yet")


def _cmd_stats(args: argparse.Namespace) -> int:
    return run_stats(data_dir=args.data_dir, reports_dir=args.reports_dir)


def _cmd_fixtures(args: argparse.Namespace) -> int:
    return run_fixtures(data_dir=args.data_dir, out_dir=args.out_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracklab",
        description="Track Lab data pipeline. --data-dir defaults to $TRACKLAB_DATA_ROOT or data.",
    )
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
        default=data_root(),
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
        default=data_root(),
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
        default=data_root(),
        help="Data root: reads raw/<source_id>/, writes bronze/<sport>/<table>/ (default: data).",
    )
    bronze.set_defaults(func=_cmd_bronze)

    orientation = subparsers.add_parser(
        "orientation",
        help="Probe attack direction and court geometry; write bronze.common.orientation.",
    )
    orientation.add_argument(
        "--sport",
        choices=(*SPORTS, "both"),
        default="both",
        help="Which sport to probe (default: both).",
    )
    orientation.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest/sources.json"),
        help="Path to sources.json (default: manifest/sources.json).",
    )
    orientation.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: reads bronze/<sport>/, writes bronze/common/orientation/ (default: data).",
    )
    orientation.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where orientation_<sport>.csv go (default: reports).",
    )
    orientation.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("../docs"),
        help="Where decisions.md goes (default: ../docs, the repo's docs from pipeline/).",
    )
    orientation.set_defaults(func=_cmd_orientation)

    possessions = subparsers.add_parser(
        "possessions",
        help="Score the two candidate rules for a football team possession.",
    )
    possessions.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the football bronze tables are read from it (default: data).",
    )
    possessions.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where possessions_football.csv goes (default: reports).",
    )
    possessions.set_defaults(func=_cmd_possessions)

    publish = subparsers.add_parser("publish", help="Write JSON for the web from silver.")
    publish.set_defaults(func=_cmd_publish)

    stats = subparsers.add_parser(
        "stats", help="Count what silver holds; write reports/stats_silver.csv."
    )
    stats.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the silver tables are read from <data-dir>/silver/ (default: data).",
    )
    stats.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where stats_silver.csv goes (default: reports).",
    )
    stats.set_defaults(func=_cmd_stats)

    fixtures = subparsers.add_parser(
        "fixtures", help="Cut one possession per sport out of bronze, for CI."
    )
    fixtures.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Where the full bronze is read from (default: data, never the data root).",
    )
    fixtures.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tests/fixtures/data"),
        help="Data root the cut lands in (default: tests/fixtures/data).",
    )
    fixtures.set_defaults(func=_cmd_fixtures)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: _Handler = args.func
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
