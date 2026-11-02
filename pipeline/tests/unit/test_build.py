"""`tracklab build` on fabricated events, Parquet and receipts (task 32).

What the record must get right and the real run cannot show on purpose: a step
that writes three assets is charged its duration once, a failed step is written
down and the command exits 1, a step the failure abandoned is written down too,
rows come from the Parquet footers, a `.gz` is counted decompressed, the
receipt's `source_path` never reaches the record, the files written from a
record are not counted in the next one, and a measurement that raises still
leaves a record.
Running the real job is the command's own acceptance in tasks/todo.md.
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from dagster import AssetKey, AssetMaterialization, AssetObservation, DagsterEvent, MetadataValue
from dagster._core.events import AssetObservationData, StepMaterializationData
from dagster._core.execution.plan.objects import StepFailureData, StepSuccessData

from tracklab.build import (
    RunResult,
    StepPlan,
    bytes_read,
    default_record_dir,
    measure_disk,
    measure_publish,
    measure_table,
    run_build,
    serves_query,
    step_times_from_logs,
    steps_from_events,
)
from tracklab.silver.incremental import FULL_ENV, PLAN_METADATA_KEY, Plan

PLAN = {
    "raw_x": StepPlan(("raw_x",), "ingest"),
    "bronze_x": StepPlan(("bronze_x_a", "bronze_x_b", "bronze_x_c"), "bronze"),
    "silver": StepPlan(("silver_frames",), "silver"),
}


def _event(kind: str, step_key: str, data: object = None) -> DagsterEvent:
    return DagsterEvent(kind, "build", step_key=step_key, event_specific_data=data)


def _materialized(step_key: str, asset: str, seconds: float | None = None) -> DagsterEvent:
    metadata = {"Execution Duration": seconds} if seconds is not None else {}
    materialization = AssetMaterialization(asset_key=AssetKey(asset), metadata=metadata)
    return _event("ASSET_MATERIALIZATION", step_key, StepMaterializationData(materialization))


def _success(step_key: str, duration_ms: float) -> DagsterEvent:
    return _event("STEP_SUCCESS", step_key, StepSuccessData(duration_ms=duration_ms))


def _failure(step_key: str) -> DagsterEvent:
    return _event("STEP_FAILURE", step_key, StepFailureData(error=None, user_failure_data=None))


RUN_ID = "abcdef0123456789"


def _fake_execute(
    events: Sequence[DagsterEvent],
    plan: dict[str, StepPlan] = PLAN,
    step_times: dict[str, tuple[float, float]] | None = None,
) -> Callable[[Sequence[AssetKey] | None, Path], RunResult]:
    return lambda keys, record_dir: RunResult(plan, events, RUN_ID, step_times or {})


RAW_ONLY = {"raw_x": PLAN["raw_x"]}


def _only_record(record_dir: Path) -> dict[str, object]:
    (path,) = record_dir.glob("*.json")
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def test_a_step_of_three_assets_is_charged_its_duration_once() -> None:
    events = [
        _event("STEP_START", "bronze_x"),
        _materialized("bronze_x", "bronze_x_a"),
        _materialized("bronze_x", "bronze_x_b"),
        _materialized("bronze_x", "bronze_x_c"),
        _success("bronze_x", 1500.0),
    ]

    (step,) = steps_from_events(events, {"bronze_x": PLAN["bronze_x"]})

    assert step.assets == ["bronze_x_a", "bronze_x_b", "bronze_x_c"]
    assert step.group == "bronze"
    assert step.status == "success"
    assert step.duration_ms == 1500.0
    assert step.dbt_seconds == {}


def test_dbt_seconds_ride_on_the_materialization_metadata() -> None:
    events = [
        _materialized("silver", "silver_frames", seconds=67.9),
        _materialized("silver", "silver_events", seconds=4.25),
        _success("silver", 116200.0),
    ]

    (step,) = steps_from_events(events, {"silver": PLAN["silver"]})

    assert step.duration_ms == 116200.0
    assert step.dbt_seconds == {"silver_events": 4.25, "silver_frames": 67.9}


def test_a_failed_step_is_written_down_and_the_command_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events = [
        _success("raw_x", 100.0),
        _event("STEP_START", "bronze_x"),
        _failure("bronze_x"),
        # No event for "silver": the multiprocess executor abandons a step whose
        # upstream failed without emitting STEP_SKIPPED.
    ]

    code = run_build(
        None,
        tmp_path / "build",
        tmp_path / "data",
        execute=_fake_execute(events),
        reports_dir=tmp_path / "reports",
        web_data_dir=tmp_path / "web",
    )

    assert code == 1
    record = _only_record(tmp_path / "build")
    steps = record["steps"]
    assert isinstance(steps, list)
    assert [(s["step_key"], s["status"], s["duration_ms"]) for s in steps] == [
        ("raw_x", "success", 100.0),
        ("bronze_x", "failure", None),
        ("silver", "not_run", None),
    ]
    out = capsys.readouterr().out
    assert "bronze_x  failure" in out
    assert "steps=3 success=1 failure=1 assets=1" in out


def test_measure_table_sums_the_rows_of_every_parquet_footer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = tmp_path / "t"
    (table / "sub").mkdir(parents=True)
    pq.write_table(pa.table({"x": [1, 2, 3]}), table / "a.parquet")
    pq.write_table(pa.table({"x": [1, 2, 3, 4]}), table / "sub" / "b.parquet")

    measure = measure_table(table)
    print(f"rows={measure.rows}")

    assert "rows=7" in capsys.readouterr().out
    assert measure.rows == 7
    assert [f.path for f in measure.files] == ["a.parquet", "sub/b.parquet"]
    assert [f.rows for f in measure.files] == [3, 4]
    assert measure.bytes == sum(p.stat().st_size for p in table.rglob("*.parquet"))


def test_bytes_read_counts_a_gz_decompressed_and_the_rest_on_disk(tmp_path: Path) -> None:
    payload = b"0123456789" * 10_000
    packed = tmp_path / "tracking.jsonl.gz"
    with gzip.open(packed, "wb") as handle:
        handle.write(payload)
    plain = tmp_path / "tracking.jsonl"
    plain.write_bytes(payload[:12_345])

    assert packed.stat().st_size < len(payload)
    assert bytes_read(packed) == len(payload)
    assert bytes_read(plain) == 12_345


def test_the_record_reads_the_receipt_but_never_writes_source_path(
    tmp_path: Path, assert_no_local_traces: Callable[[object], None]
) -> None:
    data = tmp_path / "data"
    receipt_dir = data / "raw" / "opendata-basketball"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "_receipt.json").write_text(
        json.dumps(
            {
                "source_id": "opendata-basketball",
                "commit": "abc",
                "verified": 35,
                "downloaded": 0,
                "failed": [],
                "finished_at": "2026-09-24T00:00:00+00:00",
                "source_path": str(tmp_path / "clone"),
            }
        ),
        encoding="utf-8",
    )

    code = run_build(
        None,
        tmp_path / "build",
        data,
        execute=_fake_execute([_success("raw_x", 1.0)], RAW_ONLY),
        reports_dir=tmp_path / "reports",
        web_data_dir=tmp_path / "web",
    )

    assert code == 0
    record = _only_record(tmp_path / "build")
    assert_no_local_traces(record)
    disk = record["disk"]
    assert isinstance(disk, dict)
    raw = disk["raw"]
    assert (raw["receipts"], raw["verified"], raw["downloaded"]) == (1, 35, 0)
    assert raw["files"] == 122 and raw["files_read"] == 0


def test_publish_leaves_out_the_files_written_from_a_record(tmp_path: Path) -> None:
    for name, size in (("stats.json", 10), ("lineage.json", 200), ("platform.json", 300)):
        (tmp_path / name).write_bytes(b"x" * size)
    (tmp_path / "possessions").mkdir()
    (tmp_path / "possessions" / "platform.json").write_bytes(b"x" * 7)

    publish = measure_publish(tmp_path)

    assert [f["path"] for f in publish["watch"]] == ["stats.json"]
    assert (publish["files"], publish["bytes"]) == (1, 10)


def test_publish_leaves_out_the_euroleague_aggregates(tmp_path: Path) -> None:
    """P14: /platform's "out" is what the SkillCorner pipeline publishes; the EuroLeague folder
    comes from another source, so none of it counts. Without the folder rule this counts 3 files."""
    (tmp_path / "stats.json").write_bytes(b"x" * 10)
    (tmp_path / "euroleague" / "teams").mkdir(parents=True)
    (tmp_path / "euroleague" / "league.json").write_bytes(b"x" * 400)
    (tmp_path / "euroleague" / "teams" / "MAD.json").write_bytes(b"x" * 90)
    (tmp_path / "learn").mkdir()
    (tmp_path / "learn" / "euroleague.json").write_bytes(b"x" * 5)

    publish = measure_publish(tmp_path)

    assert [f["path"] for f in publish["watch"]] == ["learn/euroleague.json", "stats.json"]
    assert (publish["files"], publish["bytes"]) == (2, 15)


def test_publish_counts_the_parquet_the_browser_queries(tmp_path: Path) -> None:
    """Decision 10, option C: "out" is what the site watches plus what /warehouse queries.
    Without the `*.parquet` pass the 4,000 bytes below are not counted and this fails."""
    (tmp_path / "stats.json").write_bytes(b"x" * 10)
    (tmp_path / "platform.json").write_bytes(b"x" * 300)
    (tmp_path / "warehouse").mkdir()
    (tmp_path / "warehouse" / "fact.abcd1234.parquet").write_bytes(b"x" * 3000)
    (tmp_path / "warehouse" / "bb_picks.ef567890.parquet").write_bytes(b"x" * 1000)

    publish = measure_publish(tmp_path)

    assert [f["path"] for f in publish["query"]] == [
        "warehouse/bb_picks.ef567890.parquet",
        "warehouse/fact.abcd1234.parquet",
    ]
    assert (publish["watch_bytes"], publish["query_bytes"]) == (10, 4000)
    assert (publish["files"], publish["bytes"]) == (3, 4010)


def test_the_warehouse_json_is_to_query_not_to_watch(tmp_path: Path) -> None:
    """The split is by use, not by format (review V of P4, A1): the JSON that only /warehouse
    reads count with the Parquet. Split by extension, the three below land in "to watch"."""
    (tmp_path / "stats.json").write_bytes(b"x" * 10)
    (tmp_path / "possessions").mkdir()
    (tmp_path / "possessions" / "bb_possession_1.json").write_bytes(b"x" * 5)
    (tmp_path / "warehouse").mkdir()
    (tmp_path / "warehouse" / "fact.abcd1234.parquet").write_bytes(b"x" * 3000)
    for name, size in (
        ("warehouse.json", 20),
        ("warehouse_examples.json", 40),
        ("warehouse_pg.json", 80),
    ):
        (tmp_path / name).write_bytes(b"x" * size)

    publish = measure_publish(tmp_path)

    assert [f["path"] for f in publish["watch"]] == [
        "possessions/bb_possession_1.json",
        "stats.json",
    ]
    assert [f["path"] for f in publish["query"]] == [
        "warehouse/fact.abcd1234.parquet",
        "warehouse.json",
        "warehouse_examples.json",
        "warehouse_pg.json",
    ]
    assert (publish["watch_bytes"], publish["query_bytes"]) == (15, 3140)
    assert serves_query("warehouse_anything.json") and not serves_query("stats.json")


def test_the_disk_measure_has_a_gold_layer(tmp_path: Path) -> None:
    table = tmp_path / "gold" / "dim_player"
    table.mkdir(parents=True)
    pq.write_table(pa.table({"x": [1, 2, 3]}), table / "data.parquet")

    disk = measure_disk(tmp_path, Path("manifest/sources.json"), tmp_path / "r", tmp_path / "w")

    assert [(t["layer"], t["table"], t["rows"]) for t in disk["gold"]["tables"]] == [
        ("gold", "dim_player", 3)
    ]
    assert (disk["gold"]["files"], disk["gold"]["rows"]) == (1, 3)


def test_a_truncated_parquet_still_leaves_a_record_and_exits_1(tmp_path: Path) -> None:
    table = tmp_path / "data" / "silver" / "frames"
    table.mkdir(parents=True)
    pq.write_table(pa.table({"x": [1, 2, 3]}), table / "a.parquet")
    (table / "a.parquet").write_bytes((table / "a.parquet").read_bytes()[:20])

    code = run_build(
        None,
        tmp_path / "build",
        tmp_path / "data",
        execute=_fake_execute([_success("raw_x", 1.0)], RAW_ONLY),
        reports_dir=tmp_path / "reports",
        web_data_dir=tmp_path / "web",
    )

    assert code == 1
    record = _only_record(tmp_path / "build")
    steps = record["steps"]
    assert isinstance(steps, list) and steps[0]["status"] == "success"
    disk = record["disk"]
    assert isinstance(disk, dict) and list(disk) == ["error"]
    assert disk["error"] == "ArrowInvalid", "the type only: a message can carry a local path"


def test_the_record_dir_follows_the_data_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACKLAB_DATA_ROOT", "tests/fixtures/data")
    assert default_record_dir() == Path("tests/fixtures/data/build")
    monkeypatch.delenv("TRACKLAB_DATA_ROOT")
    assert default_record_dir() == Path("data/build")


@pytest.mark.skipif(
    not any(default_record_dir().glob("*.json")), reason="no build record; run `tracklab build`"
)
def test_the_newest_real_record_names_no_machine(
    assert_no_local_traces: Callable[[object], None],
) -> None:
    newest = sorted(default_record_dir().glob("*.json"))[-1]
    record = json.loads(newest.read_text(encoding="utf-8"))
    print(f"{newest.name}: {len(record['steps'])} steps, wall {record['wall_seconds']} s")
    assert_no_local_traces(record)


# --- schema 2 (task 125) ---------------------------------------------------------------


def _run_results(
    target: Path, step: str, run_id: str, statuses: dict[str, str], elapsed: float
) -> None:
    folder = target / f"{step}-{run_id[:7]}-1a2b3c4"
    folder.mkdir(parents=True)
    results = [{"unique_id": uid, "status": status} for uid, status in statuses.items()]
    (folder / "run_results.json").write_text(
        json.dumps({"elapsed_time": elapsed, "results": results}), encoding="utf-8"
    )


def _v2_record(tmp_path: Path, step_times: dict[str, tuple[float, float]]) -> dict[str, object]:
    target = tmp_path / "target"
    _run_results(
        target,
        "silver",
        RUN_ID,
        {
            "model.t.frames": "success",
            "seed.t.surface": "success",
            "model.t.events": "error",
            "test.t.not_null_a": "pass",
            "test.t.not_null_b": "pass",
            "test.t.unique_a": "fail",
            "test.t.range_a": "warn",
            "test.t.rel_a": "skipped",
        },
        66.84,
    )
    # A run of another id in the same folder must not be read as this one's.
    _run_results(target, "silver", "ffffffff", {"test.t.other": "pass"}, 1.0)
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    for name in ("test_a.py", "test_b.py", "helpers.py"):
        (contracts / name).write_text("", encoding="utf-8")
    code = run_build(
        None,
        tmp_path / "build",
        tmp_path / "data",
        execute=_fake_execute(
            [_success("raw_x", 100.0), _success("silver", 200.0)], PLAN, step_times
        ),
        reports_dir=tmp_path / "reports",
        web_data_dir=tmp_path / "web",
        dbt_target=target,
        contracts_dir=contracts,
    )
    assert code == 1  # bronze_x is in the plan and no event names it: not_run
    return _only_record(tmp_path / "build")


def test_the_v2_record_carries_run_id_step_times_and_dbt_counts(tmp_path: Path) -> None:
    record = _v2_record(
        tmp_path,
        {
            "raw_x": (1_700_000_000.0, 1_700_000_000.1),
            "silver": (1_700_000_001.5, 1_700_000_068.25),
        },
    )

    assert record["schema_version"] == 2
    assert record["run_id"] == RUN_ID
    steps = {s["step_key"]: s for s in record["steps"]}  # type: ignore[attr-defined]
    silver = steps["silver"]
    assert silver["started_utc"] == "2023-11-14T22:13:21.500+00:00"
    assert silver["finished_utc"] == "2023-11-14T22:14:28.250+00:00"
    assert silver["dbt"] == {
        "tests": {"pass": 2, "fail": 1, "warn": 1, "error": 0, "skipped": 1},
        "nodes": {"success": 2, "error": 1, "skipped": 0},
        "elapsed_seconds": 66.84,
    }
    assert steps["raw_x"]["dbt"] is None  # no run_results.json for this step
    not_run = steps["bronze_x"]
    assert (not_run["started_utc"], not_run["finished_utc"], not_run["dbt"]) == (None, None, None)
    # Only the incremental silver step's observation fills these (task 127).
    empty = {"written": [], "skipped": [], "deleted": []}
    assert all(s["partitions"] == empty and s["incremental"] is None for s in steps.values())


def test_contracts_are_the_counted_files_and_say_they_were_not_run(tmp_path: Path) -> None:
    record = _v2_record(tmp_path, {})

    assert record["contracts"] == {"files": 2, "executed": False}


def test_step_times_span_the_dagster_events_of_each_step() -> None:
    def entry(step: str | None, at: float, *, event: bool = True) -> SimpleNamespace:
        dagster_event = _event("STEP_START", step) if (event and step) else None
        return SimpleNamespace(dagster_event=dagster_event, timestamp=at)

    logs = [
        entry("a", 10.0),
        entry(None, 5.0),
        entry("b", 11.0),
        entry("a", 14.5),
        entry("a", 3.0, event=False),  # a plain log line carries no Dagster event
    ]

    assert step_times_from_logs(logs) == {"a": (10.0, 14.5), "b": (11.0, 11.0)}


# --- the incremental silver step (task 127) ----------------------------------------------


def _observed(step_key: str, plan: Plan) -> DagsterEvent:
    observation = AssetObservation(
        asset_key=AssetKey("silver_frames"),
        metadata={PLAN_METADATA_KEY: MetadataValue.json(plan.record())},
    )
    return _event("ASSET_OBSERVATION", step_key, AssetObservationData(observation))


def test_the_silver_plan_reaches_the_step_record() -> None:
    plan = Plan("incremental", "1 of 2 matches changed", ["bb/1"], ["fb/2"], ["fb/3"])
    events = [_observed("silver", plan), _success("silver", 900.0)]

    (step,) = steps_from_events(events, {"silver": PLAN["silver"]})

    assert step.partitions == {"written": ["bb/1"], "skipped": ["fb/2"], "deleted": ["fb/3"]}
    assert step.incremental == {"mode": "incremental", "reason": "1 of 2 matches changed"}


def test_a_skipped_silver_step_records_no_dbt_and_says_why(tmp_path: Path) -> None:
    """dbt was not launched: no run_results.json, so `dbt` is None and never zero tests."""
    plan = Plan("skip", "no input changed since run r0", [], ["bb/1", "fb/2"], [])
    code = run_build(
        None,
        tmp_path / "build",
        tmp_path / "data",
        execute=_fake_execute(
            [_observed("silver", plan), _success("silver", 900.0)],
            {"silver": PLAN["silver"]},
            {"silver": (1_700_000_000.0, 1_700_000_001.0)},
        ),
        reports_dir=tmp_path / "reports",
        web_data_dir=tmp_path / "web",
        dbt_target=tmp_path / "target",
        contracts_dir=tmp_path / "contracts",
    )

    assert code == 0
    (silver,) = _only_record(tmp_path / "build")["steps"]  # type: ignore[misc]
    assert silver["dbt"] is None
    assert silver["incremental"] == {"mode": "skip", "reason": "no input changed since run r0"}
    assert silver["partitions"]["skipped"] == ["bb/1", "fb/2"]


@pytest.mark.parametrize("full", [True, False])
def test_full_reaches_the_steps_only_while_the_job_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, full: bool
) -> None:
    monkeypatch.delenv(FULL_ENV, raising=False)
    seen: list[str | None] = []

    def execute(keys: Sequence[AssetKey] | None, record_dir: Path) -> RunResult:
        seen.append(os.environ.get(FULL_ENV))
        return RunResult(RAW_ONLY, [_success("raw_x", 1.0)], RUN_ID, {})

    run_build(
        None,
        tmp_path / "build",
        tmp_path / "data",
        execute=execute,
        reports_dir=tmp_path / "reports",
        web_data_dir=tmp_path / "web",
        full=full,
    )

    assert seen == (["1"] if full else [None])
    assert FULL_ENV not in os.environ
