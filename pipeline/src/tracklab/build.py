"""`tracklab build`: the `build` job, run the way `dagster job execute` runs it, and
a record of what the run cost and what it left on disk (task 32).

The job runs through `dagster.execute_job` with the same multiprocess executor
the CLI uses (`reconstructable` + `spawn`, one process per step), against a
temporary instance like the one `dagster job execute` creates when
`DAGSTER_HOME` is unset. The plan said `DagsterInstance.ephemeral()`; the
installed Dagster refuses that with a multiprocess executor (the child
processes need storage they can open), so the instance is `local_temp` under
the record directory instead, gone when the command exits.

The record (`<data root>/build/<utc>_<sha7>.json`, ignored by git) holds what only the
run itself can know: the duration of each step from `StepSuccessData`, the
seconds per dbt model from dagster-dbt's `Execution Duration`, and a measure
of the disk after the run (raw, bronze, silver, gold, quality, publish). Steps run in
parallel, so their durations are reported per step and never summed. A step
the plan holds but no event names (downstream of a failure, the multiprocess
executor abandons it without a `STEP_SKIPPED`) is recorded as `not_run`. Row
counts come from the Parquet footers (`num_rows`), never from a scan. Nothing
in the record names this machine: no host name, no path outside the data
root, and the receipt's `source_path` is read to find the raw bytes but never
written. `tracklab publish platform` (task 34) turns a record into
`platform.json`; this command writes nothing under `web/`, and it measures
`web/public/data` (JSON and Parquet) without `lineage.json` and `platform.json`: the job does not
write them, they describe the platform (its graph, its measure) rather than
the data it publishes, and `platform.json` counted would make the next title
depend on the previous one. A measurement that fails (a truncated Parquet) is
written into the record as `disk.error`, the exception's type only (its message
can carry a local path), and the command exits 1.

Schema 2 (task 125, P16) adds what only the run can know about itself, and keeps every
v1 key: `run_id` (Dagster's), per step its start and end (`started_utc`, `finished_utc`,
UTC with milliseconds, from the temporary instance's event log read before it closes) and
`dbt` (that step's `run_results.json`, found by `<step>-<run_id[:7]>-*` under `dbt/target`:
`tests` counted as pass, fail, warn, error and skipped, `nodes` (models and seeds) as
success, error and skipped, and `elapsed_seconds`; None where the step ran no dbt or left
no file), and per step `partitions` (`written`, `skipped` and `deleted`, lists of
`<sport>/<native_match_id>`) and `incremental` (`mode` and `reason`), both from the observation
the incremental silver step leaves (task 127; empty lists and None on every other step). A silver
step that found nothing changed did not launch dbt: its `dbt` is None and `incremental` says
`skip` and why, never a count of zero tests.
`contracts` is what the repo has for contracts, the pytest files of `tests/contracts` (nothing
in dbt is an enforced model contract). A full build (no `--select`) whose steps all succeeded
runs them once the job is over, after silver and gold, with `TRACKLAB_REQUIRE_FULL=1` (decided
by Javier on 2026-11-02, task 129): `executed: true`, `status` (`passed` or `failed`), `passed`,
`failed`, `skipped` and `errors` read from pytest's own junit XML (never from its prose), the
start, end and duration of the run, and pytest's exit code. A failing contract fails the build
(exit 1) and the record is still written. A partial build, or a full one with a failed step,
records `executed: false` and a `status` that says why ("not run (partial build)"); it never
records zeros. `wall_seconds` covers the contracts too.
"""

from __future__ import annotations

import gzip
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET  # noqa: S405 (pytest's own junit file, written a moment ago)
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow.parquet as pq

from tracklab.ingest.fetch import RECEIPT_NAME
from tracklab.ingest.manifest import load_manifest
from tracklab.paths import data_root
from tracklab.publish.lineage import LINEAGE_JSON
from tracklab.publish.platform import PLATFORM_JSON
from tracklab.silver.incremental import FULL_ENV, PLAN_METADATA_KEY

if TYPE_CHECKING:
    from dagster import AssetKey, DagsterEvent, JobDefinition

MANIFEST = Path("manifest/sources.json")
REPORTS_DIR = Path("reports")
WEB_DATA_DIR = Path("../web/public/data")
DBT_MANIFEST = Path("dbt/target/manifest.json")
DBT_DURATION_KEY = "Execution Duration"
SCHEMA_VERSION = 2
CONTRACTS_DIR = Path("tests/contracts")
DBT_TARGET = Path("dbt/target")
DBT_TEST_STATUSES = ("pass", "fail", "warn", "error", "skipped")
DBT_NODE_STATUSES = ("success", "error", "skipped")
# Not written by the job: they describe the platform, not its data (module docstring).
ABOUT_PLATFORM = frozenset({LINEAGE_JSON, PLATFORM_JSON})
# Not SkillCorner's: `tracklab euroleague publish` writes this folder from another source that the
# pipeline's "in" never reads, so its aggregates are not part of what the pipeline publishes (P14).
NOT_THE_PIPELINE = frozenset({"euroleague"})


def default_record_dir() -> Path:
    """`build/` under the data root: follows `TRACKLAB_DATA_ROOT` like raw and silver."""
    return data_root() / "build"


@dataclass(frozen=True)
class StepPlan:
    """What a step of the job writes: its asset keys and their group."""

    assets: tuple[str, ...]
    group: str


@dataclass(frozen=True)
class StepRecord:
    step_key: str
    assets: list[str]
    group: str | None
    status: str  # success, failure, skipped or not_run
    duration_ms: float | None  # StepSuccessData; None unless the step succeeded
    dbt_seconds: dict[str, float]  # per model, dagster-dbt's "Execution Duration"
    # Schema 2 (task 125): None / empty where the run could not know.
    started_utc: str | None = None
    finished_utc: str | None = None
    dbt: dict[str, Any] | None = None
    partitions: dict[str, list[str]] = field(
        default_factory=lambda: {"written": [], "skipped": [], "deleted": []}
    )
    incremental: dict[str, str] | None = None  # task 127: the silver step's mode and reason


@dataclass(frozen=True)
class ParquetFile:
    path: str  # relative to the table directory, posix
    rows: int
    bytes: int


@dataclass(frozen=True)
class TableMeasure:
    files: list[ParquetFile]

    @property
    def rows(self) -> int:
        return sum(f.rows for f in self.files)

    @property
    def bytes(self) -> int:
        return sum(f.bytes for f in self.files)


@dataclass(frozen=True)
class RunResult:
    """What `execute` hands back: the plan, the events, Dagster's run id and each step's
    first and last event time (epoch seconds), read while the instance is still open."""

    plan: dict[str, StepPlan]
    events: Sequence[DagsterEvent]
    run_id: str
    step_times: Mapping[str, tuple[float, float]]


Execute = Callable[["Sequence[AssetKey] | None", Path], RunResult]
# (contracts dir, data dir, junit XML path) -> pytest's exit code; writes the XML.
RunContracts = Callable[[Path, Path, Path], int]


# --- the run ---------------------------------------------------------------------


def build_job() -> JobDefinition:
    """What `reconstructable` re-imports in every child process: the `build` job."""
    from tracklab.dagster_defs import defs

    return defs.resolve_job_def("build")


def resolve_selection(select: str) -> Sequence[AssetKey]:
    from dagster import AssetSelection

    from tracklab.dagster_defs import defs

    return sorted(AssetSelection.from_string(select).resolve(defs.resolve_asset_graph()))


def plan_from_job(job: JobDefinition) -> dict[str, StepPlan]:
    """Step key -> the assets it writes and their group, read off the (possibly
    subset) job the run executed, so a `multi_asset` is one step with many keys."""
    layer = job.asset_layer
    by_step: dict[str, dict[str, str]] = {}
    for key in layer.executable_asset_keys:
        step = layer.get_op_output_handle(key).node_handle.name
        by_step.setdefault(step, {})[key.to_user_string()] = layer.get(key).group_name
    return {
        step: StepPlan(tuple(sorted(assets)), ",".join(sorted(set(assets.values()))))
        for step, assets in sorted(by_step.items())
    }


def step_times_from_logs(logs: Iterable[Any]) -> dict[str, tuple[float, float]]:
    """Step key -> (first, last) timestamp of the Dagster events that name it. `logs` are the
    instance's event log entries; plain log lines (no Dagster event) are not the step's."""
    span: dict[str, tuple[float, float]] = {}
    for entry in logs:
        key = entry.dagster_event.step_key if entry.dagster_event is not None else None
        if key is None:
            continue
        first, last = span.get(key, (entry.timestamp, entry.timestamp))
        span[key] = (min(first, entry.timestamp), max(last, entry.timestamp))
    return span


def execute_build(keys: Sequence[AssetKey] | None, record_dir: Path) -> RunResult:
    from dagster import DagsterInstance, execute_job, reconstructable

    record_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".tmp_dagster_home_", dir=record_dir, ignore_cleanup_errors=True
    ) as tempdir:
        with DagsterInstance.local_temp(tempdir) as instance:
            result = execute_job(
                reconstructable(build_job),
                instance=instance,
                asset_selection=keys,
                raise_on_error=False,
            )
            return RunResult(
                plan_from_job(result.job_def),
                list(result.all_events),
                result.run_id,
                step_times_from_logs(instance.all_logs(result.run_id)),
            )


def steps_from_events(
    events: Iterable[DagsterEvent], plan: Mapping[str, StepPlan]
) -> list[StepRecord]:
    """One record per step that ran, in the order the steps were first seen, then
    every planned step no event named, as `not_run`. The
    duration is the step's own (`StepSuccessData`), counted once however many
    assets the step wrote; dbt's per-model seconds ride on the materializations."""
    order: list[str] = []
    status: dict[str, str] = {}
    duration: dict[str, float] = {}
    dbt_seconds: dict[str, dict[str, float]] = {}
    plans: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event.step_key
        if key is None:
            continue
        if key not in status:
            order.append(key)
            status[key] = "unknown"
        if event.is_step_success:
            status[key] = "success"
            duration[key] = float(event.step_success_data.duration_ms)
        elif event.is_step_failure:
            status[key] = "failure"
        elif event.is_step_skipped:
            status[key] = "skipped"
        elif event.is_step_materialization:
            materialization = event.step_materialization_data.materialization
            value = materialization.metadata.get(DBT_DURATION_KEY)
            if value is not None and isinstance(value.value, int | float):
                asset = materialization.asset_key.to_user_string()
                dbt_seconds.setdefault(key, {})[asset] = float(value.value)
        elif event.is_asset_observation:
            found = event.asset_observation_data.asset_observation.metadata.get(PLAN_METADATA_KEY)
            if found is not None and isinstance(found.value, dict):
                plans[key] = found.value
    records = []
    for key in order:
        step = plan.get(key)
        record = StepRecord(
            step_key=key,
            assets=list(step.assets) if step else [],
            group=step.group if step else None,
            status=status[key],
            duration_ms=duration.get(key),
            dbt_seconds=dict(sorted(dbt_seconds.get(key, {}).items())),
        )
        if key in plans:
            found_plan = plans[key]
            partitions = {k: list(found_plan[k]) for k in ("written", "skipped", "deleted")}
            mode = {"mode": found_plan["mode"], "reason": found_plan["reason"]}
            record = replace(record, partitions=partitions, incremental=mode)
        records.append(record)
    for key, step in plan.items():
        if key not in status:
            records.append(StepRecord(key, list(step.assets), step.group, "not_run", None, {}))
    return records


def dbt_results(target: Path, step_key: str, run_id: str) -> dict[str, Any] | None:
    """The step's dbt outcome from the `run_results.json` that dagster-dbt left in
    `<target>/<step>-<run id[:7]>-<uuid[:7]>/`; None when the step ran no dbt."""
    found = sorted(
        target.glob(f"{step_key}-{run_id[:7]}-*/run_results.json"), key=lambda p: p.stat().st_mtime
    )
    if not found:
        return None
    return dbt_summary(json.loads(found[-1].read_text(encoding="utf-8")))


def dbt_summary(run: Mapping[str, Any]) -> dict[str, Any]:
    """Tests by status, nodes by status and dbt's own elapsed time, from a parsed `run_results.json`
    (`publish history` reads the same file for the v1 records, which kept none of this)."""
    tests = dict.fromkeys(DBT_TEST_STATUSES, 0)
    nodes = dict.fromkeys(DBT_NODE_STATUSES, 0)
    for result in run["results"]:
        counts = tests if result["unique_id"].startswith("test.") else nodes
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {"tests": tests, "nodes": nodes, "elapsed_seconds": round(run["elapsed_time"], 3)}


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="milliseconds")


def with_run_facts(
    steps: Sequence[StepRecord], run: RunResult, dbt_target: Path
) -> list[StepRecord]:
    """Schema 2: each step gets its start and end and its dbt outcome; a step no event
    named (`not_run`) has neither."""
    out = []
    for step in steps:
        span = run.step_times.get(step.step_key)
        out.append(
            replace(
                step,
                started_utc=_iso(span[0]) if span else None,
                finished_utc=_iso(span[1]) if span else None,
                dbt=dbt_results(dbt_target, step.step_key, run.run_id) if span else None,
            )
        )
    return out


def pytest_contracts(contracts_dir: Path, data_dir: Path, junit: Path) -> int:
    """`pytest tests/contracts` over the data root, in full mode (a skip would hide a missing
    bundle), in the foreground; its exit code. The result is in the junit XML."""
    env = {**os.environ, "TRACKLAB_DATA_ROOT": str(data_dir), "TRACKLAB_REQUIRE_FULL": "1"}
    command = [sys.executable, "-m", "pytest", str(contracts_dir), f"--junitxml={junit}"]
    return subprocess.run(
        [*command, "-q", "-p", "no:cacheprovider"], env=env, check=False
    ).returncode


def junit_counts(junit: Path) -> dict[str, int] | None:
    """passed, failed, skipped and errors from pytest's junit XML; None when it is missing or
    not a result (pytest died before writing it)."""
    try:
        root = ET.parse(junit).getroot()  # noqa: S314
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return None
    total = {
        k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "skipped", "errors")
    }
    return {
        "passed": total["tests"] - total["failures"] - total["skipped"] - total["errors"],
        "failed": total["failures"],
        "skipped": total["skipped"],
        "errors": total["errors"],
    }


def not_run_contracts(contracts_dir: Path, why: str) -> dict[str, Any]:
    return {"files": len(list(contracts_dir.glob("test_*.py"))), "executed": False, "status": why}


def run_contracts_step(
    contracts_dir: Path, data_dir: Path, runner: RunContracts, record_dir: Path
) -> dict[str, Any]:
    """Run the contracts and say what came of it; `status` is `passed` only for exit 0 with
    nothing failed and no error."""
    record_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    clock = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=".tmp_contracts_", dir=record_dir) as tempdir:
        junit = Path(tempdir) / "junit.xml"
        exit_code = runner(contracts_dir, data_dir, junit)
        counts = junit_counts(junit)
    record: dict[str, Any] = {
        **not_run_contracts(contracts_dir, ""),
        "executed": True,
        "started_utc": started.isoformat(timespec="milliseconds"),
        "finished_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "duration_seconds": round(time.perf_counter() - clock, 3),
        "pytest_exit_code": exit_code,
        **(counts or dict.fromkeys(("passed", "failed", "skipped", "errors"))),
    }
    ok = exit_code == 0 and counts is not None and not counts["failed"] and not counts["errors"]
    record["status"] = "passed" if ok else "failed"
    return record


# --- the disk after the run --------------------------------------------------------


def bytes_read(path: Path) -> int:
    """What a reader of `path` gets: the decompressed bytes of a `.gz` or a `.zip`
    (the zip's from its central directory, nothing inflated), the size on disk of
    anything else."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return sum(member.file_size for member in archive.infolist())
    if path.suffix != ".gz":
        return path.stat().st_size
    total = 0
    with gzip.open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            total += len(chunk)
    return total


def measure_table(directory: Path) -> TableMeasure:
    """Every Parquet under `directory` (a partition tree or a single file): rows
    from the footer, bytes from `stat`, paths relative to the directory."""
    files = []
    for path in sorted(directory.rglob("*.parquet")):
        files.append(
            ParquetFile(
                path=path.relative_to(directory).as_posix(),
                rows=int(pq.read_metadata(path).num_rows),
                bytes=path.stat().st_size,
            )
        )
    return TableMeasure(files)


def _table_entry(
    layer: str, sport: str | None, table: str, measure: TableMeasure
) -> dict[str, Any]:
    return {
        "layer": layer,
        "sport": sport,
        "table": table,
        "files": len(measure.files),
        "rows": measure.rows,
        "bytes": measure.bytes,
        "parquet": [asdict(f) for f in measure.files],
    }


def _subdirs(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir()) if path.is_dir() else []


def measure_bronze(data_dir: Path) -> list[dict[str, Any]]:
    """`bronze/<sport>/<table>/`, `common` included."""
    return [
        _table_entry("bronze", sport.name, table.name, measure_table(table))
        for sport in _subdirs(data_dir / "bronze")
        for table in _subdirs(sport)
    ]


def measure_silver(data_dir: Path) -> list[dict[str, Any]]:
    """`silver/<table>/`; a partitioned table's sport is in each file's path."""
    return [
        _table_entry("silver", None, table.name, measure_table(table))
        for table in _subdirs(data_dir / "silver")
    ]


def _layer_totals(tables: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "files": sum(t["files"] for t in tables),
        "rows": sum(t["rows"] for t in tables),
        "bytes": sum(t["bytes"] for t in tables),
    }


def measure_gold(data_dir: Path) -> list[dict[str, Any]]:
    """`gold/<model>/`: the season aggregates and the dimensional model of task 40."""
    return [
        _table_entry("gold", None, table.name, measure_table(table))
        for table in _subdirs(data_dir / "gold")
    ]


def measure_raw(data_dir: Path, manifest_path: Path) -> dict[str, Any]:
    """The manifest's files and bytes, the receipts' `downloaded` and `verified`,
    and the bytes a reader gets from each file that is on disk (a `.gz` counted
    decompressed). The receipt's `source_path` locates the bytes and is not kept."""
    sources: list[dict[str, Any]] = []
    for source in load_manifest(manifest_path).sources:
        receipt_dir = data_dir / "raw" / source.source_id
        receipt_path = receipt_dir / RECEIPT_NAME
        receipt: dict[str, Any] | None = None
        root = receipt_dir
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt is not None and receipt.get("source_path"):
                root = Path(receipt["source_path"])
        files: list[dict[str, Any]] = []
        for entry in source.files:
            on_disk = root / entry.path
            files.append(
                {
                    "path": entry.path,
                    "role": entry.role,
                    "match_id": entry.match_id,
                    "bytes": entry.bytes,
                    "bytes_read": bytes_read(on_disk) if on_disk.is_file() else None,
                }
            )
        read = [f for f in files if f["bytes_read"] is not None]
        sources.append(
            {
                "source_id": source.source_id,
                "sport": source.sport,
                "files": len(files),
                "bytes_pinned": sum(f["bytes"] for f in files),
                "receipt": receipt is not None,
                "downloaded": receipt["downloaded"] if receipt else 0,
                "verified": receipt["verified"] if receipt else 0,
                "files_read": len(read),
                "bytes_read": sum(f["bytes_read"] for f in read),
                "manifest": files,
            }
        )
    totals = {
        key: sum(s[key] for s in sources)
        for key in ("files", "bytes_pinned", "downloaded", "verified", "files_read", "bytes_read")
    }
    return {**totals, "receipts": sum(1 for s in sources if s["receipt"]), "sources": sources}


def measure_quality(reports_dir: Path) -> dict[str, Any]:
    csvs = []
    for path in sorted(reports_dir.glob("quality_*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows = max(sum(1 for _ in handle) - 1, 0)
        csvs.append({"path": path.name, "rows": rows, "bytes": path.stat().st_size})
    return {
        "files": len(csvs),
        "rows": sum(c["rows"] for c in csvs),
        "bytes": sum(c["bytes"] for c in csvs),
        "csv": csvs,
    }


def serves_query(name: str) -> bool:
    """The one rule of the split behind "out" (decision 10, option C, by use): a published file
    that only `/warehouse` uses is "to query", the Parquet and the `warehouse*.json` that
    describe them, their example answers and the Postgres snapshot; anything else is "to watch"."""
    return name.endswith(".parquet") or (name.startswith("warehouse") and name.endswith(".json"))


def measure_publish(web_data_dir: Path) -> dict[str, Any]:
    """What `web/public/data` publishes, split by use (task 41; decision 10, option C): what the
    site watches and what `/warehouse` queries (`serves_query`). `lineage.json` and
    `platform.json` are left out by name at any depth, the Parquet are not, and so is the
    top-level `euroleague/` folder (`NOT_THE_PIPELINE`), whose source is not in the "in"."""
    paths = sorted(
        path
        for pattern in ("*.json", "*.parquet")
        for path in web_data_dir.rglob(pattern)
        if path.name not in ABOUT_PLATFORM
        and path.relative_to(web_data_dir).parts[0] not in NOT_THE_PIPELINE
    )

    def listing(to_query: bool) -> list[dict[str, Any]]:
        return [
            {"path": path.relative_to(web_data_dir).as_posix(), "bytes": path.stat().st_size}
            for path in paths
            if serves_query(path.name) == to_query
        ]

    watch, query = listing(False), listing(True)
    watch_bytes = sum(f["bytes"] for f in watch)
    query_bytes = sum(f["bytes"] for f in query)
    return {
        "files": len(paths),
        "bytes": watch_bytes + query_bytes,
        "watch_bytes": watch_bytes,
        "query_bytes": query_bytes,
        "watch": watch,
        "query": query,
    }


def measure_disk(
    data_dir: Path, manifest_path: Path, reports_dir: Path, web_data_dir: Path
) -> dict[str, Any]:
    bronze, silver, gold = (
        measure_bronze(data_dir),
        measure_silver(data_dir),
        measure_gold(data_dir),
    )
    return {
        "raw": measure_raw(data_dir, manifest_path),
        "bronze": {**_layer_totals(bronze), "tables": bronze},
        "silver": {**_layer_totals(silver), "tables": silver},
        "gold": {**_layer_totals(gold), "tables": gold},
        "quality": measure_quality(reports_dir),
        "publish": measure_publish(web_data_dir),
    }


# --- the record --------------------------------------------------------------------


def git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return out or None


def ram_gb() -> float | None:
    """Physical memory in GiB, one decimal; None where it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            total = int(status.ullTotalPhys)
        else:
            total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        return None
    return round(total / 2**30, 1)


def host_info() -> dict[str, Any]:
    """The machine, without its name: what a reader needs to weigh the seconds."""
    return {"system": platform.system(), "cpus": os.cpu_count(), "ram_gb": ram_gb()}


def versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        **{name: version(name) for name in ("dagster", "dagster-dbt", "dbt-core", "duckdb")},
    }


def record_path(record_dir: Path, started: datetime, sha: str | None) -> Path:
    return record_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{(sha or 'nogit')[:7]}.json"


def write_record(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _print_steps(steps: Sequence[StepRecord]) -> None:
    width = max((len(s.step_key) for s in steps), default=8)
    print(f"{'step':<{width}}  {'status':<8}  {'seconds':>8}  assets")
    for step in steps:
        seconds = f"{step.duration_ms / 1000:.1f}" if step.duration_ms is not None else "-"
        print(f"{step.step_key:<{width}}  {step.status:<8}  {seconds:>8}  {len(step.assets)}")
        for model, secs in step.dbt_seconds.items():
            print(f"{'':<{width}}  {'':<8}  {secs:>8.1f}  {model}")


def run_build(
    select: str | None,
    record_dir: Path,
    data_dir: Path,
    *,
    execute: Execute = execute_build,
    manifest_path: Path = MANIFEST,
    reports_dir: Path = REPORTS_DIR,
    web_data_dir: Path = WEB_DATA_DIR,
    dbt_target: Path = DBT_TARGET,
    contracts_dir: Path = CONTRACTS_DIR,
    full: bool = False,
    run_contracts: RunContracts | None = None,
) -> int:
    """Run the job, write the record whatever happened, exit 1 if any step did not
    succeed. `execute` is what runs the job; the tests hand in a fake. `full` makes the
    incremental silver step rebuild every match (`FULL_ENV`, inherited by the step's process).
    `run_contracts` is what runs `tests/contracts` after a full build (the tests hand in a fake)."""
    keys: Sequence[AssetKey] | None = None
    if select is not None:
        if not DBT_MANIFEST.is_file():
            print(f"build: {DBT_MANIFEST} missing; run `dbt parse` first")
            return 1
        keys = resolve_selection(select)
        if not keys:
            print(f"build: --select {select!r} selects no asset; nothing to run")
            return 1
        print(f"build: --select {select!r} resolves to {len(keys)} assets")

    sha = git_sha()
    started = datetime.now(UTC)
    clock = time.perf_counter()
    previous = os.environ.get(FULL_ENV)
    if full:
        os.environ[FULL_ENV] = "1"
    try:
        run = execute(keys, record_dir)
    finally:
        if full and previous is None:
            del os.environ[FULL_ENV]
    steps = with_run_facts(steps_from_events(run.events, run.plan), run, dbt_target)
    steps_ok = bool(steps) and all(step.status == "success" for step in steps)
    if select is not None:
        contracts = not_run_contracts(contracts_dir, "not run (partial build)")
    elif not steps_ok:
        contracts = not_run_contracts(contracts_dir, "not run (a step failed)")
    else:
        contracts = run_contracts_step(
            contracts_dir, data_dir, run_contracts or pytest_contracts, record_dir
        )
    wall_seconds = round(time.perf_counter() - clock, 3)
    finished = datetime.now(UTC)
    # Whatever the measurement raises, the run still gets its record: the steps
    # above are the part only this run knows.
    try:
        disk: dict[str, Any] = measure_disk(data_dir, manifest_path, reports_dir, web_data_dir)
    except Exception as exc:  # noqa: BLE001
        disk = {"error": type(exc).__name__}
        print(f"build: measuring the disk failed: {type(exc).__name__}: {exc}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "git_sha": sha,
        "select": select,
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": finished.isoformat(timespec="seconds"),
        "wall_seconds": wall_seconds,
        "host": host_info(),
        "versions": versions(),
        "steps": [asdict(step) for step in steps],
        "contracts": contracts,
        "disk": disk,
    }
    path = record_path(record_dir, started, sha)
    write_record(payload, path)

    _print_steps(steps)
    counts = {s: sum(1 for step in steps if step.status == s) for s in ("success", "failure")}
    print(
        f"wall_seconds={wall_seconds} steps={len(steps)} "
        f"success={counts['success']} failure={counts['failure']} "
        f"assets={sum(len(s.assets) for s in steps if s.status == 'success')}"
    )
    print(f"record: {path} ({path.stat().st_size} bytes)")
    if contracts["executed"]:
        print(
            f"contracts: {contracts['status']} passed={contracts['passed']} "
            f"failed={contracts['failed']} skipped={contracts['skipped']} "
            f"errors={contracts['errors']} in {contracts['duration_seconds']}s"
        )
    contracts_ok = not contracts["executed"] or contracts["status"] == "passed"
    return 0 if steps_ok and contracts_ok and "error" not in disk else 1
