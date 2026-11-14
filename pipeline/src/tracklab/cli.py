"""Command-line interface for tracklab.

Wires up the five subcommands described in tasks/todo.md. Each handler is a
stub for now; its logic lands in the task that owns it (see tasks/todo.md).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import TextIO

from tracklab.bronze.basketball.aggregates import build_aggregates as build_basketball_aggregates
from tracklab.bronze.basketball.events import build_events as build_basketball_events
from tracklab.bronze.basketball.meta import build_meta as build_basketball_meta
from tracklab.bronze.basketball.tracking import build_tracking as build_basketball_tracking
from tracklab.bronze.common import raw_root_for
from tracklab.bronze.football.aggregates import build_aggregates as build_football_aggregates
from tracklab.bronze.football.bodypose import build_bodypose as build_football_bodypose
from tracklab.bronze.football.events import build_events as build_football_events
from tracklab.bronze.football.meta import build_meta as build_football_meta
from tracklab.bronze.football.tracking import build_tracking as build_football_tracking
from tracklab.build import default_record_dir, run_build
from tracklab.euroleague.aggregates import SEASONS as EUROLEAGUE_SEASONS
from tracklab.euroleague.aggregates import run_euroleague_publish
from tracklab.euroleague.sweep import run_euroleague_sweep
from tracklab.fixtures import run_fixtures
from tracklab.formats.basketball import freeze_basketball
from tracklab.formats.football_report import freeze_football
from tracklab.ingest.fetch import freeze_source, ingest_source, make_client
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import Source, load_manifest, save_manifest
from tracklab.learn.browser import run_learn_browser
from tracklab.learn.clock import run_learn_clock
from tracklab.learn.dribble import run_learn_dribble
from tracklab.learn.entry_lesson import run_learn_entry
from tracklab.learn.gravity import run_learn_gravity
from tracklab.learn.hypotheses import run_learn_hypotheses
from tracklab.learn.passes import run_learn_pass
from tracklab.learn.possession import run_learn_possession
from tracklab.learn.rebound import run_learn_rebound
from tracklab.learn.speed import run_learn_speed
from tracklab.load.postgres import run_load_postgres
from tracklab.paths import data_root
from tracklab.pose.coverage import run_pose_coverage
from tracklab.pose.freeze import run_pose_freeze
from tracklab.pose.metric import run_pose_metric
from tracklab.pose.probe import run_pose_probe
from tracklab.pose.protocol import run_pose_protocol
from tracklab.pose.sweep import CLIP as POSE_CLIP
from tracklab.pose.sweep import run_pose_sweep
from tracklab.pose.verdict import run_pose_verdict
from tracklab.publish.examples import run_publish_examples
from tracklab.publish.history import run_publish_history
from tracklab.publish.lineage import run_publish_lineage
from tracklab.publish.occupancy import run_publish_occupancy
from tracklab.publish.platform import run_publish_platform
from tracklab.publish.pose import run_publish_pose
from tracklab.publish.possessions import run_publish_possessions
from tracklab.publish.quality import run_publish_quality
from tracklab.publish.runs import run_publish_runs
from tracklab.publish.scouting import run_publish_scouting
from tracklab.publish.stats import run_publish_stats
from tracklab.publish.warehouse import run_publish_warehouse
from tracklab.publish.warehouse_pg import WHERE, run_publish_warehouse_pg
from tracklab.quality.run import CHECKS, run_quality
from tracklab.runs.candidates import run_runs_effect, run_runs_freeze
from tracklab.runs.coverage import run_runs_coverage
from tracklab.runs.probe import run_runs_probe
from tracklab.runs.protocol import run_runs_protocol
from tracklab.silver.orientation import SPORTS, run_orientation
from tracklab.silver.possessions import run_possessions
from tracklab.silver.stats import run_stats
from tracklab.sqlcourse.course import run_sql_course

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
    ("football", "bodypose"): build_football_bodypose,
}
# The source a group reads when it is not the sport's own bundle `opendata-<sport>`.
BRONZE_SOURCE_IDS: dict[tuple[str, str], str] = {("football", "bodypose"): "opendata-bodypose"}


def bronze_source_id(sport: str, group: str) -> str:
    return BRONZE_SOURCE_IDS.get((sport, group), f"opendata-{sport}")


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
    groups = [g for g in args.tables.split(",") if g] if args.tables else None
    known = sorted(g for sport, g in BRONZE_BUILDERS if sport == args.sport)
    if groups is None:
        # Without --tables: the sport's own bundle. A group on another source (the body pose's
        # 2.5 GB of zips) is asked for by name.
        groups = [g for g in known if (args.sport, g) not in BRONZE_SOURCE_IDS]
    unknown = [g for g in groups if (args.sport, g) not in BRONZE_BUILDERS]
    if unknown:
        sys.exit(f"tracklab: no bronze builder for {args.sport} {unknown} (known: {known})")
    started = time.perf_counter()
    for group in groups:
        source = manifest.source(bronze_source_id(args.sport, group))
        raw_root = raw_root_for(args.data_dir, source.source_id)
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


def _cmd_publish_possessions(args: argparse.Namespace) -> int:
    return run_publish_possessions(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_lineage(args: argparse.Namespace) -> int:
    return run_publish_lineage(args.out_dir, check=args.check)


def _cmd_publish_stats(args: argparse.Namespace) -> int:
    return run_publish_stats(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_platform(args: argparse.Namespace) -> int:
    return run_publish_platform(
        record_path=args.run,
        record_dir=args.record_dir,
        out_dir=args.out_dir,
        check=args.check,
    )


def _cmd_publish_history(args: argparse.Namespace) -> int:
    return run_publish_history(record_dir=args.record_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_warehouse(args: argparse.Namespace) -> int:
    return run_publish_warehouse(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_examples(args: argparse.Namespace) -> int:
    return run_publish_examples(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_scouting(args: argparse.Namespace) -> int:
    return run_publish_scouting(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_occupancy(args: argparse.Namespace) -> int:
    return run_publish_occupancy(args.data_dir, args.out_dir, check=args.check)


def _cmd_publish_runs(args: argparse.Namespace) -> int:
    return run_publish_runs(args.data_dir, args.reports_dir, args.out_dir, check=args.check)


def _cmd_pose_coverage(args: argparse.Namespace) -> int:
    return run_pose_coverage(args.data_dir, args.reports_dir, check=args.check)


def _cmd_pose_sweep(args: argparse.Namespace) -> int:
    return run_pose_sweep(args.reports_dir, args.clip, check=args.check)


def _cmd_pose_protocol(args: argparse.Namespace) -> int:
    return run_pose_protocol(args.data_dir, args.reports_dir, check=args.check)


def _cmd_pose_probe(args: argparse.Namespace) -> int:
    return run_pose_probe(args.data_dir, args.reports_dir, args.clip, check=args.check)


def _cmd_pose_freeze(args: argparse.Namespace) -> int:
    return run_pose_freeze(args.reports_dir, date=args.date)


def _cmd_pose_verdict(args: argparse.Namespace) -> int:
    return run_pose_verdict(args.data_dir, args.reports_dir, check=args.check)


def _cmd_pose_metric(args: argparse.Namespace) -> int:
    return run_pose_metric(args.data_dir, args.reports_dir, check=args.check)


def _cmd_publish_pose(args: argparse.Namespace) -> int:
    return run_publish_pose(
        args.data_dir,
        args.reports_dir,
        args.out_dir,
        args.manifest,
        args.schema,
        check=args.check,
    )


def _cmd_publish_warehouse_pg(args: argparse.Namespace) -> int:
    return run_publish_warehouse_pg(
        data_dir=args.data_dir, out_dir=args.out_dir, dsn_env=args.dsn_env, where=args.where
    )


def _cmd_load_postgres(args: argparse.Namespace) -> int:
    return run_load_postgres(
        data_dir=args.data_dir,
        dsn_env=args.dsn_env,
        reader_password_env=args.reader_password_env,
    )


def _cmd_publish_quality(args: argparse.Namespace) -> int:
    return run_publish_quality(
        data_dir=args.data_dir,
        reports_dir=args.reports_dir,
        out_dir=args.out_dir,
        docs_dir=args.docs_dir,
        check=args.check,
    )


def _cmd_stats(args: argparse.Namespace) -> int:
    return run_stats(data_dir=args.data_dir, reports_dir=args.reports_dir)


def _cmd_quality(args: argparse.Namespace) -> int:
    checks = [args.check] if args.check else sorted(CHECKS)
    return run_quality(checks, data_dir=args.data_dir, reports_dir=args.reports_dir)


def _cmd_fixtures(args: argparse.Namespace) -> int:
    return run_fixtures(data_dir=args.data_dir, out_dir=args.out_dir)


def _cmd_runs_protocol(args: argparse.Namespace) -> int:
    return run_runs_protocol(args.data_dir, args.reports_dir, check=args.check)


def _cmd_runs_coverage(args: argparse.Namespace) -> int:
    return run_runs_coverage(args.data_dir, args.reports_dir, check=args.check)


def _cmd_runs_probe(args: argparse.Namespace) -> int:
    return run_runs_probe(args.data_dir, args.reports_dir, check=args.check)


def _cmd_runs_effect(args: argparse.Namespace) -> int:
    return run_runs_effect(args.data_dir, args.reports_dir, check=args.check)


def _cmd_runs_freeze(args: argparse.Namespace) -> int:
    return run_runs_freeze(args.reports_dir, date=args.date)


def _cmd_learn_gravity(args: argparse.Namespace) -> int:
    return run_learn_gravity(args.data_dir, args.quality, check=args.check)


def _cmd_learn_speed(args: argparse.Namespace) -> int:
    return run_learn_speed(args.data_dir, args.out, args.possessions, check=args.check)


def _cmd_learn_rebound(args: argparse.Namespace) -> int:
    return run_learn_rebound(args.data_dir, args.out, check=args.check)


def _cmd_learn_hypotheses(args: argparse.Namespace) -> int:
    return run_learn_hypotheses(args.data_dir, args.out, args.quality, check=args.check)


def _cmd_learn_clock(args: argparse.Namespace) -> int:
    return run_learn_clock(args.data_dir, args.out, args.possessions, check=args.check)


def _cmd_learn_pass(args: argparse.Namespace) -> int:
    return run_learn_pass(args.data_dir, args.out, args.possessions, check=args.check)


def _cmd_learn_entry(args: argparse.Namespace) -> int:
    return run_learn_entry(args.data_dir, args.out, args.quality, check=args.check)


def _cmd_learn_dribble(args: argparse.Namespace) -> int:
    return run_learn_dribble(args.data_dir, args.out, args.possessions, check=args.check)


def _cmd_learn_possession(args: argparse.Namespace) -> int:
    return run_learn_possession(args.data_dir, args.out, check=args.check)


def _cmd_learn_browser(args: argparse.Namespace) -> int:
    return run_learn_browser(args.public, check=args.check)


def _cmd_sql_course(args: argparse.Namespace) -> int:
    return run_sql_course(args.public, check=args.check)


def _cmd_euroleague_fetch(args: argparse.Namespace) -> int:
    # The downloader is not part of the repository: the command runs only where the file is.
    # Imported by name, so the type check reads the same with the file and without it.
    try:
        fetch = importlib.import_module("tracklab.euroleague.fetch")
    except ModuleNotFoundError:
        print("euroleague fetch: the downloader is not part of this repository", file=sys.stderr)
        return 2
    return int(fetch.run_euroleague_fetch(args.season, args.data_dir))


def _cmd_euroleague_publish(args: argparse.Namespace) -> int:
    seasons = args.season or list(EUROLEAGUE_SEASONS)
    return run_euroleague_publish(args.data_dir, args.out_dir, seasons, check=args.check)


def _cmd_euroleague_sweep(args: argparse.Namespace) -> int:
    return run_euroleague_sweep(
        args.data_dir, args.web_dir, args.season or list(EUROLEAGUE_SEASONS)
    )


def _cmd_build(args: argparse.Namespace) -> int:
    return run_build(
        select=args.select, record_dir=args.record_dir, data_dir=data_root(), full=args.full
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracklab",
        description="Pitch & Parquet data pipeline. "
        "--data-dir defaults to $TRACKLAB_DATA_ROOT or data.",
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
        help="Comma-separated table groups to build, e.g. tracking (default: every group of the "
        "sport's own bundle; `football bodypose` reads other zips and is asked for by name).",
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
    publish_sub = publish.add_subparsers(dest="publish_command", required=True)

    publish_possessions = publish_sub.add_parser(
        "possessions", help="Pick 6 curated possessions per sport and write their JSON."
    )
    publish_possessions.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver and the basketball events_chances bronze table are read "
        "from it (default: data).",
    )
    publish_possessions.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where possessions/*.json and index.json go (default: ../web/public/data).",
    )
    publish_possessions.add_argument(
        "--check",
        action="store_true",
        help="Recompute in memory and compare bytes with the versioned file(s); write nothing. "
        "Says PARTIAL: when the data it recomputes from is not at hand.",
    )
    publish_possessions.set_defaults(func=_cmd_publish_possessions)

    publish_lineage = publish_sub.add_parser(
        "lineage",
        help="Write web/public/data/lineage.json: the Dagster asset graph, dbt tests included. "
        "Needs `dbt parse` first.",
    )
    publish_lineage.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where lineage.json goes (default: ../web/public/data).",
    )
    publish_lineage.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare against the versioned file; write nothing.",
    )
    publish_lineage.set_defaults(func=_cmd_publish_lineage)

    publish_stats = publish_sub.add_parser(
        "stats", help="Write stats.json: rows per table and sport, bronze/silver bytes."
    )
    publish_stats.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; bronze and silver are read from it (default: data).",
    )
    publish_stats.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where stats.json goes (default: ../web/public/data).",
    )
    publish_stats.add_argument(
        "--check",
        action="store_true",
        help="Recompute in memory and compare bytes with the versioned file(s); write nothing. "
        "Says PARTIAL: when the data it recomputes from is not at hand.",
    )
    publish_stats.set_defaults(func=_cmd_publish_stats)

    publish_platform = publish_sub.add_parser(
        "platform",
        help="Write web/public/data/platform.json: the measured title, layers, tables and "
        "per-match numbers from the newest `tracklab build` record.",
    )
    publish_platform.add_argument(
        "--run",
        type=Path,
        default=None,
        help="A specific build/<utc>_<sha7>.json record (default: the newest one).",
    )
    publish_platform.add_argument(
        "--record-dir",
        type=Path,
        default=default_record_dir(),
        help="Where to look for the newest record when --run is not given "
        "(default: $TRACKLAB_DATA_ROOT/build, else data/build).",
    )
    publish_platform.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where platform.json goes, and where index.json/stats.json are read from "
        "(default: ../web/public/data).",
    )
    publish_platform.add_argument(
        "--check",
        action="store_true",
        help="Write nothing; compare the published bytes (measured live), title and subtitle, "
        "and rows per table and per match against the record and stats.json, exit 1 if "
        "they differ.",
    )
    publish_platform.set_defaults(func=_cmd_publish_platform)

    publish_history = publish_sub.add_parser(
        "history",
        help="Write web/public/data/history.json: one entry per build record (steps, dbt tests, "
        "contracts); it only grows, an entry already there is never rewritten or dropped.",
    )
    publish_history.add_argument(
        "--record-dir",
        type=Path,
        default=default_record_dir(),
        help="Where the build records are (default: $TRACKLAB_DATA_ROOT/build, else data/build).",
    )
    publish_history.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where history.json goes (default: ../web/public/data).",
    )
    publish_history.add_argument(
        "--check",
        action="store_true",
        help="Write nothing; compare every record on disk with its entry and exit 1 if one is "
        "missing or differs. No records, or none of them in the file, is PARTIAL.",
    )
    publish_history.set_defaults(func=_cmd_publish_history)

    publish_warehouse = publish_sub.add_parser(
        "warehouse",
        help="Write web/public/data/warehouse/*.parquet and warehouse.json: the gold tables "
        "the browser queries, byte-reproducible.",
    )
    publish_warehouse.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; gold is read from it (default: data).",
    )
    publish_warehouse.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where warehouse.json and warehouse/ go (default: ../web/public/data).",
    )
    publish_warehouse.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare rows and sha256 against the files on disk "
        "and warehouse.json; write nothing.",
    )
    publish_warehouse.set_defaults(func=_cmd_publish_warehouse)

    publish_examples = publish_sub.add_parser(
        "examples",
        help="Write warehouse_examples.json: what the /warehouse example queries must return, "
        "computed from gold without SQL, and the basketball alias figures.",
    )
    publish_examples.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; gold and the bronze aliases are read from it (default: data).",
    )
    publish_examples.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where warehouse_examples.json goes (default: ../web/public/data).",
    )
    publish_examples.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare with the file on disk; write nothing.",
    )
    publish_examples.set_defaults(func=_cmd_publish_examples)

    publish_scouting = publish_sub.add_parser(
        "scouting",
        help="Write scouting.json: the pools, the sample floors and the expected values and "
        "percentiles of the probe players of the scouting page, computed in plain Python from "
        "the published warehouse Parquet.",
    )
    publish_scouting.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; only the bronze basketball aliases are read from it (default: data).",
    )
    publish_scouting.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where scouting.json goes and warehouse.json and warehouse/ are read from "
        "(default: ../web/public/data).",
    )
    publish_scouting.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare byte for byte with the file on disk; write nothing.",
    )
    publish_scouting.set_defaults(func=_cmd_publish_scouting)

    publish_occupancy = publish_sub.add_parser(
        "occupancy",
        help="Write occupancy.json: where the players of each football position group are, a "
        "share per cell of one pitch with every team attacking left to right, pooled over the "
        "matches outside the Analytics Cup fence.",
    )
    publish_occupancy.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver frames and dimensions and the bronze football match_players are "
        "read from it (default: data).",
    )
    publish_occupancy.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where occupancy.json goes (default: ../web/public/data).",
    )
    publish_occupancy.add_argument(
        "--check",
        action="store_true",
        help="Recompute when every match of the file is at hand and compare the bytes (FULL n/n); "
        "on a slice run the code and say PARTIAL k/n; write nothing.",
    )
    publish_occupancy.set_defaults(func=_cmd_publish_occupancy)

    publish_runs = publish_sub.add_parser(
        "runs",
        help="Write runs.json (P5, published dead: the figures of the reports, the funnel, "
        "the per-match tables) and the hook's two clips under runs/.",
    )
    publish_runs.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the calibration frames of the clips are read from it (default: data).",
    )
    publish_runs.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where the P5 reports live (default: reports).",
    )
    publish_runs.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where runs.json and runs/ go (default: ../web/public/data).",
    )
    publish_runs.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare with the files on disk; write nothing.",
    )
    publish_runs.set_defaults(func=_cmd_publish_runs)

    publish_pose = publish_sub.add_parser(
        "pose",
        help="Write the Body Pose sample's clip (P6) under pose/ and its record, "
        "reports/pose_clip.json.",
    )
    publish_pose.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the sample and the bronze of the match are read from it.",
    )
    publish_pose.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where pose_clip.json goes (default: reports).",
    )
    publish_pose.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where pose/ goes (default: ../web/public/data).",
    )
    publish_pose.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest/sources.json"),
        help="Path to sources.json, which pins the sample's sha256.",
    )
    publish_pose.add_argument(
        "--schema",
        type=Path,
        default=Path("../web/lib/pose/schema.json"),
        help="JSON schema the clip must validate against.",
    )
    publish_pose.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare with the files on disk; write nothing.",
    )
    publish_pose.set_defaults(func=_cmd_publish_pose)

    publish_warehouse_pg = publish_sub.add_parser(
        "warehouse-pg",
        help="Write warehouse_pg.json: rows, EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and table "
        "sizes of the example queries in the Postgres `tracklab load postgres` filled.",
    )
    publish_warehouse_pg.add_argument(
        "--dsn-env",
        default="TRACKLAB_PG_DSN",
        help="Environment variable holding the connection string (default: TRACKLAB_PG_DSN).",
    )
    publish_warehouse_pg.add_argument(
        "--where",
        required=True,
        choices=sorted(WHERE),
        help="Which Postgres this is; the JSON says it in words, never the host.",
    )
    publish_warehouse_pg.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; gold is counted to check the load is current (default: data).",
    )
    publish_warehouse_pg.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where warehouse_pg.json goes and warehouse_examples.json is read from "
        "(default: ../web/public/data).",
    )
    publish_warehouse_pg.set_defaults(func=_cmd_publish_warehouse_pg)

    load = subparsers.add_parser("load", help="Load gold into a database outside the repo.")
    load_sub = load.add_subparsers(dest="load_command", required=True)
    load_postgres = load_sub.add_parser(
        "postgres",
        help="Apply pipeline/sql/ and load the gold dimensional model into Postgres, "
        "incrementally: only new, changed and gone rows are written.",
    )
    load_postgres.add_argument(
        "--dsn-env",
        default="TRACKLAB_PG_DSN",
        help="Environment variable holding the connection string (default: TRACKLAB_PG_DSN).",
    )
    load_postgres.add_argument(
        "--reader-password-env",
        default=None,
        help="Environment variable holding a password for the read-only role "
        "warehouse_reader; given, the role can log in with it (default: unchanged).",
    )
    load_postgres.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; gold is read from it (default: data).",
    )
    load_postgres.set_defaults(func=_cmd_load_postgres)

    publish_quality = publish_sub.add_parser(
        "quality",
        help="Write quality.json and docs/bulletin.md from reports/quality_*.csv.",
    )
    publish_quality.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the hook shot reads bronze and silver from it (default: data).",
    )
    publish_quality.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where quality_<check>.csv are read from (default: reports).",
    )
    publish_quality.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where quality.json goes (default: ../web/public/data).",
    )
    publish_quality.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("../docs"),
        help="Where bulletin.md goes (default: ../docs, the repo's docs from pipeline/).",
    )
    publish_quality.add_argument(
        "--check",
        action="store_true",
        help="Recompute in memory and compare bytes with the versioned file(s); write nothing. "
        "Says PARTIAL: when the data it recomputes from is not at hand.",
    )
    publish_quality.set_defaults(func=_cmd_publish_quality)

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

    quality = subparsers.add_parser(
        "quality", help="Run the data quality checks; write reports/quality_<check>.csv."
    )
    quality.add_argument(
        "check", nargs="?", choices=sorted(CHECKS), help="One check (default: all of them)."
    )
    quality.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver is read from <data-dir>/silver/ (default: data).",
    )
    quality.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where quality_<check>.csv go (default: reports).",
    )
    quality.set_defaults(func=_cmd_quality)

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

    pose = subparsers.add_parser("pose", help="P6: the Body Pose of the full matches.")
    pose_sub = pose.add_subparsers(dest="pose_command", required=True)
    pose_coverage = pose_sub.add_parser(
        "coverage",
        help="Write reports/pose_coverage.json: frames, frame-players with pose and joint "
        "observations per match, period and player, with the denominator of each.",
    )
    pose_coverage.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; bronze/football/bodypose_* are read from it (default: data).",
    )
    pose_coverage.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where pose_coverage.json goes (default: reports).",
    )
    pose_coverage.add_argument(
        "--check",
        action="store_true",
        help="Recount the whole matches at hand and compare with the versioned file; write "
        "nothing. FULL n/n if every match was recounted, PARTIAL k/n on a slice.",
    )
    pose_coverage.set_defaults(func=_cmd_pose_coverage)
    pose_sweep = pose_sub.add_parser(
        "sweep",
        help="Write reports/pose_sweep.json: task 60's synthetic sweep of the cadence of s (and, "
        "for information, of h), from the mae of the versioned clip; no data is read.",
    )
    pose_sweep.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where pose_sweep.json goes (default: reports).",
    )
    pose_sweep.add_argument(
        "--clip",
        type=Path,
        default=POSE_CLIP,
        help="The versioned clip whose skeletons give the mae (default: "
        "../web/public/data/pose/1925299_phase406.json).",
    )
    pose_sweep.add_argument(
        "--check",
        action="store_true",
        help="Regenerate the whole sweep in memory and compare the bytes; write nothing.",
    )
    pose_sweep.set_defaults(func=_cmd_pose_sweep)
    pose_protocol = pose_sub.add_parser(
        "protocol",
        help="Write reports/pose_protocol.json in stage design: task 60's protocol after the six "
        "reviews, with the sha256 of the sweep and the coverage inside its fingerprint.",
    )
    pose_protocol.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the denominators are counted from bronze/football/bodypose_* "
        "(default: data).",
    )
    pose_protocol.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where pose_protocol.json goes and pose_sweep.json, pose_coverage.json are read "
        "from (default: reports).",
    )
    pose_protocol.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare the bytes; write nothing. FULL 2/2 when both "
        "matches' bronze is whole, PARTIAL k/2 otherwise.",
    )
    pose_protocol.set_defaults(func=_cmd_pose_protocol)
    pose_probe = pose_sub.add_parser(
        "probe",
        help="Write reports/pose_calibration.json: task 60's probe on 1925299, first time (no "
        "cadence), and the rule of (W, cap) applied blind.",
    )
    pose_probe.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the Body Pose bronze of 1925299 is read from it (default: data).",
    )
    pose_probe.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where pose_calibration.json goes and pose_sweep.json is read from "
        "(default: reports).",
    )
    pose_probe.add_argument(
        "--clip",
        type=Path,
        default=POSE_CLIP,
        help="The versioned clip the sweep's noise twins are drawn from (default: "
        "../web/public/data/pose/1925299_phase406.json).",
    )
    pose_probe.add_argument(
        "--check",
        action="store_true",
        help="Recompute where 1925299's bronze is whole and compare the bytes (FULL 1/1); "
        "elsewhere check the seal, the protocol and the rule as written (PARTIAL 0/1).",
    )
    pose_probe.set_defaults(func=_cmd_pose_probe)
    pose_freeze = pose_sub.add_parser(
        "freeze",
        help="Turn reports/pose_protocol.json to stage frozen at the (W, cap) the rule chose, "
        "with the sha of the committed pose/ tree; refuses anything uncommitted.",
    )
    pose_freeze.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where pose_protocol.json, pose_calibration.json and pose_sweep.json live "
        "(default: reports).",
    )
    pose_freeze.add_argument("--date", required=True, help="The freeze's date, YYYY-MM-DD.")
    pose_freeze.set_defaults(func=_cmd_pose_freeze)
    for name, func, what in (
        (
            "verdict",
            _cmd_pose_verdict,
            "Write reports/pose_verdict.json: the probe's second time on 1925299 after the "
            "freeze, M1 and M2's verdict and M4's half IQR.",
        ),
        (
            "metric",
            _cmd_pose_metric,
            "Write reports/pose_metric.json (task 61): the metric per match, period and player, "
            "and the verdicts of M1, M2 and M4; 1996435 only past the guard.",
        ),
    ):
        sub = pose_sub.add_parser(name, help=what)
        sub.add_argument(
            "--data-dir",
            type=Path,
            default=data_root(),
            help="Data root; the Body Pose bronze is read from it (default: data).",
        )
        sub.add_argument(
            "--reports-dir",
            type=Path,
            default=Path("reports"),
            help="Where the reports are read and written (default: reports).",
        )
        sub.add_argument(
            "--check",
            action="store_true",
            help="Recompute where the bronze is whole and compare the bytes; elsewhere check the "
            "seal and what the file answered to (PARTIAL).",
        )
        sub.set_defaults(func=func)

    runs = subparsers.add_parser(
        "runs", help="P5: off-ball runs against the defence's displacement in the tracking."
    )
    runs_sub = runs.add_subparsers(dest="runs_command", required=True)
    runs_protocol = runs_sub.add_parser(
        "protocol",
        help="Write reports/runs_protocol.json: the split, the windows, the placebo, the "
        "instrument, the bar and the death criteria, as code, before any outcome.",
    )
    runs_protocol.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver/dim_match and the football bronze events are read from it "
        "(default: data).",
    )
    runs_protocol.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where runs_protocol.json goes and quality_partitions.csv is read from "
        "(default: reports).",
    )
    runs_protocol.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare with the versioned file; write nothing.",
    )
    runs_protocol.set_defaults(func=_cmd_runs_protocol)
    runs_coverage = runs_sub.add_parser(
        "coverage",
        help="Write reports/runs_coverage.csv: runs, windows, detection and placebos per match "
        "for the 20 matches, as counts and never an outcome.",
    )
    runs_coverage.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver frames and the football bronze events are read from it "
        "(default: data).",
    )
    runs_coverage.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where runs_coverage.csv goes (default: reports); the split is read from the "
        "protocol committed in HEAD, never from a file at hand.",
    )
    runs_coverage.add_argument(
        "--check",
        action="store_true",
        help="Recount the matches at hand and compare with the versioned file; write nothing.",
    )
    runs_coverage.set_defaults(func=_cmd_runs_coverage)
    runs_probe = runs_sub.add_parser(
        "probe",
        help="Write reports/runs_calibration.json, section probe: death probe 1 of P5 on the "
        "calibration half (cadence, instrument, real null, power); no effect per subtype.",
    )
    runs_probe.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver frames and the football bronze events are read from it "
        "(default: data).",
    )
    runs_probe.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where runs_calibration.json goes (default: reports); the split is read from the "
        "protocol committed in HEAD, never from a file at hand.",
    )
    runs_probe.add_argument(
        "--check",
        action="store_true",
        help="Regenerate where the warehouse holds the 20 matches and compare with the "
        "versioned file, else verify its seal and consistency; write nothing.",
    )
    runs_probe.set_defaults(func=_cmd_runs_probe)
    runs_effect = runs_sub.add_parser(
        "effect",
        help="Write reports/runs_calibration.json, section effect: death probe 2 of P5 on the "
        "calibration half (effect per probable subtype, pre-trend, fully detected, class at "
        "t_c), next to the probe's section.",
    )
    runs_effect.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; silver frames and the football bronze events are read from it "
        "(default: data).",
    )
    runs_effect.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where runs_calibration.json lives (default: reports); the split is read from "
        "the protocol committed in HEAD, never from a file at hand.",
    )
    runs_effect.add_argument(
        "--check",
        action="store_true",
        help="Regenerate the section where the warehouse holds the calibration matches and "
        "compare with the versioned file, else verify its seal and consistency; write nothing.",
    )
    runs_effect.set_defaults(func=_cmd_runs_effect)
    runs_freeze = runs_sub.add_parser(
        "freeze",
        help="Turn reports/runs_protocol.json to stage frozen with the candidates of the "
        "effect section and the sha of the committed runs/ tree; writes the file, commits "
        "nothing (the commit is the freeze).",
    )
    runs_freeze.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Where runs_protocol.json and runs_calibration.json live (default: reports).",
    )
    runs_freeze.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="The date of the frozen history entry (default: today).",
    )
    runs_freeze.set_defaults(func=_cmd_runs_freeze)

    learn = subparsers.add_parser("learn", help="P8: the checks behind the /learn lessons.")
    learn_sub = learn.add_subparsers(dest="learn_command", required=True)
    learn_gravity = learn_sub.add_parser(
        "gravity",
        help="Run learn/gravity.sql on the public basketball files of each match of quality.json "
        "and print its flights and median g next to the published ones.",
    )
    learn_gravity.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root; the basketball bundle is found through its ingest receipt "
        "(default: data).",
    )
    learn_gravity.add_argument(
        "--quality",
        type=Path,
        default=Path("../web/public/data/quality.json"),
        help="The published quality file (default: ../web/public/data/quality.json).",
    )
    learn_gravity.add_argument(
        "--check",
        action="store_true",
        help="Compare with quality.json and say how many matches were recomputed: FULL n/n, or "
        "PARTIAL k/n with what was checked instead; write nothing.",
    )
    learn_gravity.set_defaults(func=_cmd_learn_gravity)
    learn_speed = learn_sub.add_parser(
        "speed",
        help="Put the players' speed field next to finite differences of their positions, match "
        "by match, from bronze, and write learn/speed.json (lesson 2).",
    )
    learn_speed.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the figures, the raw bundle (through its ingest receipt) for "
        "the public SQL (default: data).",
    )
    learn_speed.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/speed.json"),
        help="The lesson's file (default: ../web/public/data/learn/speed.json).",
    )
    learn_speed.add_argument(
        "--possessions",
        type=Path,
        default=Path("../web/public/data/possessions"),
        help="The published possessions, which hold the example (default: "
        "../web/public/data/possessions).",
    )
    learn_speed.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/speed.sql on the raw "
        "files and compare it with the file: FULL n/n, or PARTIAL k/n with what was checked "
        "instead; write nothing.",
    )
    learn_speed.set_defaults(func=_cmd_learn_speed)
    learn_rebound = learn_sub.add_parser(
        "rebound",
        help="Freeze the ten players at the end of every rebounded shot and ask who reaches the "
        "rebound first, the nearest player or a time to arrive model, match by match, from "
        "bronze, and write learn/rebound.json (lesson 4).",
    )
    learn_rebound.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the figures, the raw bundle (through its ingest receipt) for "
        "the public SQL (default: data).",
    )
    learn_rebound.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/rebound.json"),
        help="The lesson's file (default: ../web/public/data/learn/rebound.json).",
    )
    learn_rebound.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/rebound.sql on the "
        "raw files and compare it with the file: FULL n/n, or PARTIAL k/n with what was checked "
        "instead; write nothing.",
    )
    learn_rebound.set_defaults(func=_cmd_learn_rebound)
    learn_hypotheses = learn_sub.add_parser(
        "hypotheses",
        help="Put the flights P3's gravity check keeps next to lesson 1's hypotheses (g by half "
        "window, g by frames from the shot's start), match by match, from silver and bronze, and "
        "write learn/gravity.json (task 87).",
    )
    learn_hypotheses.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: silver frames and bronze shots (default: data).",
    )
    learn_hypotheses.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/gravity.json"),
        help="The lesson's file (default: ../web/public/data/learn/gravity.json).",
    )
    learn_hypotheses.add_argument(
        "--quality",
        type=Path,
        default=Path("../web/public/data/quality.json"),
        help="The published quality file whose flights and g_median H 10 must give "
        "(default: ../web/public/data/quality.json).",
    )
    learn_hypotheses.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from silver and bronze and compare its bytes: FULL n/n, or "
        "PARTIAL k/n with what was checked instead; write nothing.",
    )
    learn_hypotheses.set_defaults(func=_cmd_learn_hypotheses)
    learn_clock = learn_sub.add_parser(
        "clock",
        help="Fit the game clock against the video's clock over every stretch where the provider "
        "says it runs, match by match, from bronze, and write learn/clock.json (lesson 6).",
    )
    learn_clock.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the figures, the raw bundle (through its ingest receipt) for "
        "the public SQL (default: data).",
    )
    learn_clock.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/clock.json"),
        help="The lesson's file (default: ../web/public/data/learn/clock.json).",
    )
    learn_clock.add_argument(
        "--possessions",
        type=Path,
        default=Path("../web/public/data/possessions"),
        help="The published possessions whose flag the file gives "
        "(default: ../web/public/data/possessions).",
    )
    learn_clock.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/clock.sql on the raw "
        "files and compare it with the file: FULL n/n, or PARTIAL k/n with what was checked "
        "instead; write nothing.",
    )
    learn_clock.set_defaults(func=_cmd_learn_clock)
    learn_pass = learn_sub.add_parser(
        "pass",
        help="Measure every complete pass by the ball's own chord and path, next to the "
        "provider's distance, match by match, from bronze, and write learn/pass.json (lesson 7).",
    )
    learn_pass.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the figures, the raw bundle (through its ingest receipt) for "
        "the public SQL (default: data).",
    )
    learn_pass.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/pass.json"),
        help="The lesson's file (default: ../web/public/data/learn/pass.json).",
    )
    learn_pass.add_argument(
        "--possessions",
        type=Path,
        default=Path("../web/public/data/possessions"),
        help="The published possessions the example's passes are read from "
        "(default: ../web/public/data/possessions).",
    )
    learn_pass.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/pass.sql on the raw "
        "files and compare it with the file: FULL n/n, or PARTIAL k/n with what was checked "
        "instead; write nothing.",
    )
    learn_pass.set_defaults(func=_cmd_learn_pass)
    learn_entry = learn_sub.add_parser(
        "entry",
        help="Write the example of lesson 8, the hook's flight to the rim with the entry-angle "
        "check's figures, to learn/entry.json; the table is quality.json's (lesson 8).",
    )
    learn_entry.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the example, the raw bundle (through its ingest receipt) for "
        "the public script (default: data).",
    )
    learn_entry.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/entry.json"),
        help="The lesson's file (default: ../web/public/data/learn/entry.json).",
    )
    learn_entry.add_argument(
        "--quality",
        type=Path,
        default=Path("../web/public/data/quality.json"),
        help="The published quality file: its hook is the example, its entry_angle rows the "
        "table (default: ../web/public/data/quality.json).",
    )
    learn_entry.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/entry.py on the raw "
        "files of every match and compare it with quality.json: FULL n/n, or PARTIAL k/n with "
        "what was checked instead; write nothing.",
    )
    learn_entry.set_defaults(func=_cmd_learn_entry)
    learn_dribble = learn_sub.add_parser(
        "dribble",
        help="Measure the intervals between the dribbles of a touch and the ball's lowest height "
        "near each dribble, match by match, from bronze, and write learn/dribble.json (lesson 9).",
    )
    learn_dribble.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the figures, the raw bundle (through its ingest receipt) for "
        "the public SQL (default: data).",
    )
    learn_dribble.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/dribble.json"),
        help="The lesson's file (default: ../web/public/data/learn/dribble.json).",
    )
    learn_dribble.add_argument(
        "--possessions",
        type=Path,
        default=Path("../web/public/data/possessions"),
        help="The published possessions the example's touch is read from "
        "(default: ../web/public/data/possessions).",
    )
    learn_dribble.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/dribble.sql on the "
        "raw files and compare it with the file: FULL n/n, or PARTIAL k/n with what was checked "
        "instead; write nothing.",
    )
    learn_dribble.set_defaults(func=_cmd_learn_dribble)
    learn_possession = learn_sub.add_parser(
        "possession",
        help="Measure how long a team keeps the ball: runs of same-team phases in the football "
        "matches outside the fence's held-out list, possessions in basketball, from bronze, and "
        "write learn/possession.json (lesson 10).",
    )
    learn_possession.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Data root: bronze for the figures, the raw bundles (through their ingest receipts) "
        "for the public SQL (default: data).",
    )
    learn_possession.add_argument(
        "--out",
        type=Path,
        default=Path("../web/public/data/learn/possession.json"),
        help="The lesson's file (default: ../web/public/data/learn/possession.json).",
    )
    learn_possession.add_argument(
        "--check",
        action="store_true",
        help="Rebuild the file from bronze and compare its bytes, run learn/possession.sql on the "
        "raw files of both sports and compare it with the file: FULL n/n, or PARTIAL k/n with "
        "what was checked instead; write nothing.",
    )
    learn_possession.set_defaults(func=_cmd_learn_possession)
    learn_browser = learn_sub.add_parser(
        "browser",
        help='Run each lesson\'s learn/<slug>.browser.sql (the query of "Run it here") on the '
        "published files and compare its rows with the figures the files carry (task 86).",
    )
    learn_browser.add_argument(
        "--public",
        type=Path,
        default=Path("../web/public"),
        help="The site's public folder, which holds data/ (default: ../web/public).",
    )
    learn_browser.add_argument(
        "--check",
        action="store_true",
        help="Say FULL k/k when every lesson's query agrees with its files; write nothing.",
    )
    learn_browser.set_defaults(func=_cmd_learn_browser)

    sql = subparsers.add_parser("sql", help="P11: the /sql course and its checked exercises.")
    sql_sub = sql.add_subparsers(dest="sql_command", required=True)
    sql_course = sql_sub.add_parser(
        "course",
        help="Run every reference query of sqlcourse/<slug>/ on the seven Parquet files of "
        "/warehouse, guard it and write web/public/data/sql/course.json (task 99).",
    )
    sql_course.add_argument(
        "--public",
        type=Path,
        default=Path("../web/public"),
        help="The site's public folder: data/warehouse.json and data/warehouse/ are read from "
        "it and data/sql/course.json goes into it (default: ../web/public).",
    )
    sql_course.add_argument(
        "--check",
        action="store_true",
        help="Rebuild course.json and compare its bytes; write nothing. FULL k/k when every "
        "lesson is written, PARTIAL k/n while some lesson has no folder yet.",
    )
    sql_course.set_defaults(func=_cmd_sql_course)

    build = subparsers.add_parser(
        "build",
        help="Run the Dagster `build` job (multiprocess, like `dagster job execute`) and "
        "record its steps, seconds and the disk after it. Needs `dbt parse` first.",
    )
    build.add_argument(
        "--select",
        default=None,
        help='Asset selection, e.g. "group:silver" (default: every asset of the job, then '
        "`tests/contracts`, which a partial build records as not run).",
    )
    build.add_argument(
        "--record-dir",
        type=Path,
        default=default_record_dir(),
        help="Where <utc>_<sha7>.json goes "
        "(default: $TRACKLAB_DATA_ROOT/build, else data/build; ignored by git).",
    )
    build.add_argument(
        "--full",
        action="store_true",
        help="Rebuild every silver partition and gold, whatever the state of the last run says "
        "(TRACKLAB_REQUIRE_FULL does the same).",
    )
    build.set_defaults(func=_cmd_build)

    euroleague = subparsers.add_parser(
        "euroleague", help="P14: EuroLeague game files (kept under the data root, never in git)."
    )
    euroleague_sub = euroleague.add_subparsers(dest="euroleague_command", required=True)
    euroleague_fetch = euroleague_sub.add_parser(
        "fetch",
        help="Download Points, PlaybyPlay and Boxscore of every played game, incrementally, "
        "at one request every 2 s; writes euroleague/raw/<season>/manifest.json.",
    )
    euroleague_fetch.add_argument(
        "--season",
        action="append",
        required=True,
        help="Season code, e.g. E2025; repeat the flag for several.",
    )
    euroleague_fetch.add_argument(
        "--data-dir", type=Path, default=data_root(), help="Data root (default: data)."
    )
    euroleague_fetch.set_defaults(func=_cmd_euroleague_fetch)

    euroleague_publish = euroleague_sub.add_parser(
        "publish",
        help="Write the aggregates of the downloaded games to <out>/euroleague/: league.json "
        "and teams/<CODE>.json (hexagons of 1.0 m with k = 5, players with 100 shots or more, "
        "the attempt mix by season), expected-points.json (lesson 12: counts by zone class) and "
        "runs.json (the biggest runs and comebacks, and a summary by team); never a shot.",
    )
    euroleague_publish.add_argument(
        "--season",
        action="append",
        default=None,
        help="Season code; repeat for several (default: E2025 and E2026).",
    )
    euroleague_publish.add_argument(
        "--data-dir", type=Path, default=data_root(), help="Data root (default: data)."
    )
    euroleague_publish.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../web/public/data"),
        help="Where euroleague/ goes (default: ../web/public/data).",
    )
    euroleague_publish.add_argument(
        "--check",
        action="store_true",
        help="Recompute in memory and compare with the files on disk; write nothing. PARTIAL "
        "without downloaded data.",
    )
    euroleague_publish.set_defaults(func=_cmd_euroleague_publish)

    euroleague_sweep = euroleague_sub.add_parser(
        "sweep",
        help="After `next build`: look for the UTC of 200 real shots (fixed seed) in web/.next, "
        "web/public and every *.map; one hit fails, and so do browser source maps in "
        "next.config.ts. PARTIAL without downloaded data or without web/.next.",
    )
    euroleague_sweep.add_argument(
        "--season",
        action="append",
        default=None,
        help="Season code; repeat for several (default: E2025 and E2026).",
    )
    euroleague_sweep.add_argument(
        "--data-dir", type=Path, default=data_root(), help="Data root (default: data)."
    )
    euroleague_sweep.add_argument(
        "--web-dir", type=Path, default=Path("../web"), help="The web app (default: ../web)."
    )
    # Always a check: under TRACKLAB_REQUIRE_FULL its PARTIAL fails, like every --check.
    euroleague_sweep.set_defaults(func=_cmd_euroleague_sweep, check=True)

    return parser


# full-build sets this: a `--check` that says PARTIAL there found data missing; green hides it.
REQUIRE_FULL = "TRACKLAB_REQUIRE_FULL"


def require_full() -> bool:
    """`TRACKLAB_REQUIRE_FULL` is on unless unset, empty, "0" or "false" (full-build sets it to ""
    for the pytest step, which is off)."""
    return os.environ.get(REQUIRE_FULL, "").strip().lower() not in {"", "0", "false"}


_PARTIAL = re.compile(r"\bPARTIAL(?: \d+/\d+|:)")


class _Tee:
    """Write through to a stream and keep what went by."""

    def __init__(self, stream: TextIO, seen: list[str]) -> None:
        self._stream = stream
        self._seen = seen

    def write(self, text: str) -> int:
        self._seen.append(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: _Handler = args.func
    if not (require_full() and getattr(args, "check", False)):
        return func(args)
    seen: list[str] = []
    with (
        contextlib.redirect_stdout(_Tee(sys.stdout, seen)),
        contextlib.redirect_stderr(_Tee(sys.stderr, seen)),
    ):
        code = func(args)
    if code == 0 and _PARTIAL.search("".join(seen)):
        print(
            f"{REQUIRE_FULL} is set and this check said PARTIAL: data is missing, so it fails.",
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
