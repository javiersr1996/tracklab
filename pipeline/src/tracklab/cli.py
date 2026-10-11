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
from tracklab.build import default_record_dir, run_build
from tracklab.fixtures import run_fixtures
from tracklab.formats.basketball import freeze_basketball
from tracklab.formats.football_report import freeze_football
from tracklab.ingest.fetch import freeze_source, ingest_source, make_client
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import Source, load_manifest, save_manifest
from tracklab.load.postgres import run_load_postgres
from tracklab.paths import data_root
from tracklab.publish.examples import run_publish_examples
from tracklab.publish.lineage import run_publish_lineage
from tracklab.publish.platform import run_publish_platform
from tracklab.publish.possessions import run_publish_possessions
from tracklab.publish.quality import run_publish_quality
from tracklab.publish.stats import run_publish_stats
from tracklab.publish.warehouse import run_publish_warehouse
from tracklab.publish.warehouse_pg import WHERE, run_publish_warehouse_pg
from tracklab.quality.run import CHECKS, run_quality
from tracklab.runs.coverage import run_runs_coverage
from tracklab.runs.probe import run_runs_probe
from tracklab.runs.protocol import run_runs_protocol
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


def _cmd_publish_possessions(args: argparse.Namespace) -> int:
    return run_publish_possessions(data_dir=args.data_dir, out_dir=args.out_dir)


def _cmd_publish_lineage(args: argparse.Namespace) -> int:
    return run_publish_lineage(args.out_dir, check=args.check)


def _cmd_publish_stats(args: argparse.Namespace) -> int:
    return run_publish_stats(data_dir=args.data_dir, out_dir=args.out_dir)


def _cmd_publish_platform(args: argparse.Namespace) -> int:
    return run_publish_platform(
        record_path=args.run,
        record_dir=args.record_dir,
        out_dir=args.out_dir,
        check=args.check,
    )


def _cmd_publish_warehouse(args: argparse.Namespace) -> int:
    return run_publish_warehouse(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


def _cmd_publish_examples(args: argparse.Namespace) -> int:
    return run_publish_examples(data_dir=args.data_dir, out_dir=args.out_dir, check=args.check)


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


def _cmd_build(args: argparse.Namespace) -> int:
    return run_build(select=args.select, record_dir=args.record_dir, data_dir=data_root())


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
        help="Write nothing; compare rows per table and per match against the record and "
        "stats.json, exit 1 if they differ.",
    )
    publish_platform.set_defaults(func=_cmd_publish_platform)

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

    build = subparsers.add_parser(
        "build",
        help="Run the Dagster `build` job (multiprocess, like `dagster job execute`) and "
        "record its steps, seconds and the disk after it. Needs `dbt parse` first.",
    )
    build.add_argument(
        "--select",
        default=None,
        help='Asset selection, e.g. "group:silver" (default: every asset of the job).',
    )
    build.add_argument(
        "--record-dir",
        type=Path,
        default=default_record_dir(),
        help="Where <utc>_<sha7>.json goes "
        "(default: $TRACKLAB_DATA_ROOT/build, else data/build; ignored by git).",
    )
    build.set_defaults(func=_cmd_build)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: _Handler = args.func
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
