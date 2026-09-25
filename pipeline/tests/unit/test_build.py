"""`tracklab build` on fabricated events, Parquet and receipts (task 32).

What the record must get right and the real run cannot show on purpose: a step
that writes three assets is charged its duration once, a failed step is written
down and the command exits 1, rows come from the Parquet footers, a `.gz` is
counted decompressed, and the receipt's `source_path` never reaches the record.
Running the real job is the command's own acceptance in tasks/todo.md.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from dagster import AssetKey, AssetMaterialization, DagsterEvent
from dagster._core.events import StepMaterializationData
from dagster._core.execution.plan.objects import StepFailureData, StepSuccessData

from tracklab.build import (
    RECORD_DIR,
    StepPlan,
    bytes_read,
    measure_table,
    run_build,
    steps_from_events,
)

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


def _fake_execute(
    events: Sequence[DagsterEvent],
) -> Callable[
    [Sequence[AssetKey] | None, Path], tuple[dict[str, StepPlan], Sequence[DagsterEvent]]
]:
    return lambda keys, record_dir: (PLAN, events)


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

    (step,) = steps_from_events(events, PLAN)

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

    (step,) = steps_from_events(events, PLAN)

    assert step.duration_ms == 116200.0
    assert step.dbt_seconds == {"silver_events": 4.25, "silver_frames": 67.9}


def test_a_failed_step_is_written_down_and_the_command_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events = [
        _success("raw_x", 100.0),
        _event("STEP_START", "bronze_x"),
        _failure("bronze_x"),
        _event("STEP_SKIPPED", "silver"),
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
        ("silver", "skipped", None),
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
        execute=_fake_execute([_success("raw_x", 1.0)]),
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
    assert raw["files"] == 120 and raw["files_read"] == 0


@pytest.mark.skipif(
    not any(RECORD_DIR.glob("*.json")), reason="no record under data/build; run `tracklab build`"
)
def test_the_newest_real_record_names_no_machine(
    assert_no_local_traces: Callable[[object], None],
) -> None:
    newest = sorted(RECORD_DIR.glob("*.json"))[-1]
    record = json.loads(newest.read_text(encoding="utf-8"))
    print(f"{newest.name}: {len(record['steps'])} steps, wall {record['wall_seconds']} s")
    assert_no_local_traces(record)
