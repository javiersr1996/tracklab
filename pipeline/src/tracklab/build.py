"""`tracklab build`: the `build` job, run the way `dagster job execute` runs it, and
a record of what the run cost and what it left on disk (task 32).

The job runs through `dagster.execute_job` with the same multiprocess executor
the CLI uses (`reconstructable` + `spawn`, one process per step), against a
temporary instance like the one `dagster job execute` creates when
`DAGSTER_HOME` is unset. The plan said `DagsterInstance.ephemeral()`; the
installed Dagster refuses that with a multiprocess executor (the child
processes need storage they can open), so the instance is `local_temp` under
the record directory instead, gone when the command exits.

The record (`data/build/<utc>_<sha7>.json`, ignored by git) holds what only the
run itself can know: the duration of each step from `StepSuccessData`, the
seconds per dbt model from dagster-dbt's `Execution Duration`, and a measure
of the disk after the run (raw, bronze, silver, quality, publish). Steps run in
parallel, so their durations are reported per step and never summed. Row
counts come from the Parquet footers (`num_rows`), never from a scan. Nothing
in the record names this machine: no host name, no path outside the data
root, and the receipt's `source_path` is read to find the raw bytes but never
written. `tracklab publish platform` (task 34) turns a record into
`platform.json`; this command writes nothing under `web/`.
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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow.parquet as pq

from tracklab.ingest.fetch import RECEIPT_NAME
from tracklab.ingest.manifest import load_manifest

if TYPE_CHECKING:
    from dagster import AssetKey, DagsterEvent, JobDefinition

RECORD_DIR = Path("data/build")
MANIFEST = Path("manifest/sources.json")
REPORTS_DIR = Path("reports")
WEB_DATA_DIR = Path("../web/public/data")
DBT_MANIFEST = Path("dbt/target/manifest.json")
DBT_DURATION_KEY = "Execution Duration"
SCHEMA_VERSION = 1


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
    status: str  # success, failure or skipped
    duration_ms: float | None  # StepSuccessData; None unless the step succeeded
    dbt_seconds: dict[str, float]  # per model, dagster-dbt's "Execution Duration"


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


Execute = Callable[
    ["Sequence[AssetKey] | None"], tuple[dict[str, StepPlan], "Sequence[DagsterEvent]"]
]


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


def execute_build(
    keys: Sequence[AssetKey] | None, record_dir: Path = RECORD_DIR
) -> tuple[dict[str, StepPlan], Sequence[DagsterEvent]]:
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
            return plan_from_job(result.job_def), list(result.all_events)


def steps_from_events(
    events: Iterable[DagsterEvent], plan: Mapping[str, StepPlan]
) -> list[StepRecord]:
    """One record per step that ran, in the order the steps were first seen. The
    duration is the step's own (`StepSuccessData`), counted once however many
    assets the step wrote; dbt's per-model seconds ride on the materializations."""
    order: list[str] = []
    status: dict[str, str] = {}
    duration: dict[str, float] = {}
    dbt_seconds: dict[str, dict[str, float]] = {}
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
    records = []
    for key in order:
        step = plan.get(key)
        records.append(
            StepRecord(
                step_key=key,
                assets=list(step.assets) if step else [],
                group=step.group if step else None,
                status=status[key],
                duration_ms=duration.get(key),
                dbt_seconds=dict(sorted(dbt_seconds.get(key, {}).items())),
            )
        )
    return records


# --- the disk after the run --------------------------------------------------------


def bytes_read(path: Path) -> int:
    """What a reader of `path` gets: the decompressed bytes of a `.gz`, the size
    on disk of anything else."""
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


def measure_publish(web_data_dir: Path) -> dict[str, Any]:
    files = [
        {"path": path.relative_to(web_data_dir).as_posix(), "bytes": path.stat().st_size}
        for path in sorted(web_data_dir.rglob("*.json"))
    ]
    return {"files": len(files), "bytes": sum(f["bytes"] for f in files), "json": files}


def measure_disk(
    data_dir: Path, manifest_path: Path, reports_dir: Path, web_data_dir: Path
) -> dict[str, Any]:
    bronze, silver = measure_bronze(data_dir), measure_silver(data_dir)
    return {
        "raw": measure_raw(data_dir, manifest_path),
        "bronze": {**_layer_totals(bronze), "tables": bronze},
        "silver": {**_layer_totals(silver), "tables": silver},
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
) -> int:
    """Run the job, write the record whatever happened, exit 1 if any step did not
    succeed. `execute` is what runs the job; the tests hand in a fake."""
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
    plan, events = execute(keys)
    wall_seconds = round(time.perf_counter() - clock, 3)
    finished = datetime.now(UTC)

    steps = steps_from_events(events, plan)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "git_sha": sha,
        "select": select,
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": finished.isoformat(timespec="seconds"),
        "wall_seconds": wall_seconds,
        "host": host_info(),
        "versions": versions(),
        "steps": [asdict(step) for step in steps],
        "disk": measure_disk(data_dir, manifest_path, reports_dir, web_data_dir),
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
    return 0 if steps and all(step.status == "success" for step in steps) else 1
