"""Task 128: the incremental silver step through `tracklab build`, on a copy of the fixtures.

Every run here is the real job (`run_build` with Dagster's multiprocess executor and dbt) on a
temporary copy of the fixtures' bronze (114243 and 1874553), staged in chained module fixtures
so that each stage runs once:

1. no state: a full build;
2. one value of `tracking_objects/114243` changed and a stale football partition planted: only
   the basketball partitions are rewritten (the football ones keep their bytes and `mtime_ns`),
   the stale one is deleted, and the content equals a full build of the same bronze in another
   copy (`EXCEPT ALL` both ways per partition, not bytes: DuckDB's row order is not a contract);
3. nothing changed: dbt is not launched and the record says so;
4. `TRACKLAB_REQUIRE_FULL=1`: never a skip;
5. a run whose dbt tests fail, then the old bronze put back: the match is rebuilt, not skipped.

`OVERWRITE` back in `frames.sql` makes stage 2 fail (tasks/todo.md, task 128).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.build import run_build
from tracklab.silver.incremental import FULL_ENV, read_state

PIPELINE = Path(__file__).resolve().parents[2]
FIXTURES = PIPELINE / "tests" / "fixtures" / "data"
DBT_TARGET = PIPELINE / "dbt" / "target"
BB, FB, STALE = "basketball/114243", "football/1874553", "football/999"
OBJECTS = Path("bronze/basketball/tracking_objects/114243.parquet")
PARTITIONED = ("frames", "events")
DIMS = ("dim_entity", "dim_match", "dim_period", "dim_sport", "dim_team", "dim_team_period")


def _build(root: Path, **env: str) -> dict[str, Any]:
    """One `tracklab build --select group:silver` on `root`; its record, its exit code and how
    many dbt target folders its run left (then removed)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(PIPELINE)
        patch.setenv("TRACKLAB_DATA_ROOT", str(root))
        patch.delenv("TRACKLAB_REQUIRE_FULL", raising=False)
        patch.delenv(FULL_ENV, raising=False)
        for name, value in env.items():
            patch.setenv(name, value)
        before = set((root / "build").glob("*.json"))
        code = run_build("group:silver", root / "build", root, web_data_dir=root / "web")
    (path,) = set((root / "build").glob("*.json")) - before
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()  # two runs in the same second would share a name
    (silver,) = record["steps"]
    targets = sorted(DBT_TARGET.glob(f"silver-{record['run_id'][:7]}-*"))
    for target in targets:
        shutil.rmtree(target, ignore_errors=True)
    return {"code": code, "silver": silver, "dbt_target_folders": len(targets)}


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """Every file of the partitioned tables: (mtime_ns, sha256)."""
    files = sorted(p for m in PARTITIONED for p in (root / "silver" / m).rglob("*") if p.is_file())
    return {
        p.relative_to(root).as_posix(): (
            p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in files
    }


def _rewrite(path: Path, change: Any) -> None:
    table = pq.read_table(path)
    pq.write_table(change(table), path, compression="zstd")


def _shift_first_x(table: pa.Table) -> pa.Table:
    x = table.column("x").to_pylist()
    x[0] = x[0] + 1.0
    return table.set_column(table.schema.get_field_index("x"), "x", pa.array(x, pa.float64()))


def _partition(key: str) -> str:
    sport, native = key.split("/")
    return f"sport={sport}/native_match_id={native}"


@pytest.fixture(scope="module")
def first(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("incremental") / "data"
    shutil.copytree(FIXTURES / "bronze", root / "bronze")
    run = _build(root)
    kept = root.parent / "first_frames_bb"
    shutil.copytree(root / "silver" / "frames" / _partition(BB), kept)
    return {"root": root, "run": run, "snapshot": _snapshot(root), "frames_bb": kept}


@pytest.fixture(scope="module")
def touched(first: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root: Path = first["root"]
    _rewrite(root / OBJECTS, _shift_first_x)
    for model in PARTITIONED:  # a match no bronze has any more
        shutil.copytree(
            root / "silver" / model / _partition(FB), root / "silver" / model / _partition(STALE)
        )
    run = _build(root)
    reference = tmp_path_factory.mktemp("reference") / "data"
    shutil.copytree(root / "bronze", reference / "bronze")
    return {
        "run": run,
        "snapshot": _snapshot(root),
        "reference": reference,
        "full": _build(reference),
    }


@pytest.fixture(scope="module")
def unchanged(first: dict[str, Any], touched: dict[str, Any]) -> dict[str, Any]:
    return {"run": _build(first["root"]), "snapshot": _snapshot(first["root"])}


@pytest.fixture(scope="module")
def required(first: dict[str, Any], unchanged: dict[str, Any]) -> dict[str, Any]:
    return {"run": _build(first["root"], TRACKLAB_REQUIRE_FULL="1")}


@pytest.fixture(scope="module")
def failed(first: dict[str, Any], required: dict[str, Any]) -> Iterator[dict[str, Any]]:
    root: Path = first["root"]
    good = (root / OBJECTS).read_bytes()
    # The same rows twice: `frames` is written, then its unique_combination test fails.
    _rewrite(root / OBJECTS, lambda t: pa.concat_tables([t, t.slice(0, 5)]))
    failure = _build(root)
    remembered = read_state(root)
    (root / OBJECTS).write_bytes(good)
    yield {"failure": failure, "remembered": remembered, "after": _build(root), "root": root}


def test_a_first_run_without_state_builds_everything(first: dict[str, Any]) -> None:
    silver = first["run"]["silver"]
    assert first["run"]["code"] == 0
    assert silver["incremental"] == {
        "mode": "full",
        "reason": "no state left by a successful run of the whole step",
    }
    assert silver["partitions"] == {"written": [BB, FB], "skipped": [], "deleted": []}
    assert silver["dbt"]["tests"]["pass"] > 0 and silver["dbt"]["tests"]["fail"] == 0


def test_touching_one_match_rewrites_only_its_partitions(
    first: dict[str, Any], touched: dict[str, Any]
) -> None:
    silver = touched["run"]["silver"]
    assert touched["run"]["code"] == 0
    assert silver["incremental"] == {"mode": "incremental", "reason": "1 of 2 matches changed"}
    assert silver["partitions"] == {"written": [BB], "skipped": [FB], "deleted": [STALE]}
    before, after = first["snapshot"], touched["snapshot"]
    football = {p for p in before if _partition(FB) in p}
    basketball = {p for p in before if _partition(BB) in p}
    assert len(football) == len(basketball) == 2
    assert {p: after.get(p) for p in football} == {p: before[p] for p in football}
    assert all(after[p][0] != before[p][0] for p in basketball), "rewritten"
    assert set(after) == football | basketball, "the stale partition is gone, nothing else came"


def _rows(con: duckdb.DuckDBPyConnection, glob: str) -> str:
    return f"(SELECT * FROM read_parquet('{glob}', hive_partitioning = false))"


def test_the_incremental_build_equals_a_full_one(
    first: dict[str, Any], touched: dict[str, Any]
) -> None:
    root, reference = first["root"], touched["reference"]
    assert touched["full"]["code"] == 0
    assert touched["full"]["silver"]["incremental"]["mode"] == "full"
    con = duckdb.connect()
    tables = [(m, f"{m}/{_partition(k)}/*.parquet") for m in PARTITIONED for k in (BB, FB)]
    tables += [(d, f"{d}/data.parquet") for d in DIMS]
    for name, relative in tables:
        a = _rows(con, (root / "silver" / relative).as_posix())
        b = _rows(con, (reference / "silver" / relative).as_posix())
        counts = con.sql(
            f"SELECT (SELECT count(*) FROM {a}), (SELECT count(*) FROM {b})"
        ).fetchone()
        assert counts is not None and counts[0] == counts[1] > 0, name
        for left, right in ((a, b), (b, a)):
            extra = con.sql(f"SELECT count(*) FROM ({left} EXCEPT ALL {right})").fetchone()
            assert extra == (0,), f"{name}: rows of one build missing from the other"


def test_the_changed_value_reached_silver(first: dict[str, Any], touched: dict[str, Any]) -> None:
    """The comparison above would also pass on two builds that both missed the change: the
    rewritten partition must differ from the first build's by the one shifted position."""
    con = duckdb.connect()
    old = _rows(con, (first["frames_bb"] / "*.parquet").as_posix())
    new = _rows(
        con, (first["root"] / "silver" / "frames" / _partition(BB) / "*.parquet").as_posix()
    )
    for left, right in ((old, new), (new, old)):
        assert con.sql(f"SELECT count(*) FROM ({left} EXCEPT ALL {right})").fetchone() == (1,)


def test_nothing_changed_launches_no_dbt(
    touched: dict[str, Any], unchanged: dict[str, Any]
) -> None:
    run = unchanged["run"]
    silver = run["silver"]
    assert run["code"] == 0 and silver["status"] == "success"
    assert silver["incremental"]["mode"] == "skip"
    assert silver["incremental"]["reason"].startswith("no input changed since run ")
    assert silver["dbt"] is None and run["dbt_target_folders"] == 0
    assert silver["partitions"] == {"written": [], "skipped": [BB, FB], "deleted": []}
    assert unchanged["snapshot"] == touched["snapshot"]


def test_require_full_never_skips(required: dict[str, Any]) -> None:
    silver = required["run"]["silver"]
    assert required["run"]["code"] == 0
    assert silver["incremental"] == {"mode": "full", "reason": "TRACKLAB_REQUIRE_FULL is set"}
    assert silver["partitions"]["written"] == [BB, FB]
    assert silver["dbt"]["tests"]["pass"] > 0


def test_a_failed_run_is_rebuilt_even_with_the_old_bronze_back(failed: dict[str, Any]) -> None:
    failure, after = failed["failure"], failed["after"]
    assert failure["code"] == 1 and failure["silver"]["status"] == "failure"
    assert failure["silver"]["dbt"]["tests"]["fail"] > 0, "the models ran, a test failed"
    # Same bronze as the last success, partitions on disk: only the state can tell.
    assert after["code"] == 0
    assert after["silver"]["incremental"]["mode"] == "incremental"
    assert after["silver"]["partitions"]["written"] == [BB]
    remembered = failed["remembered"]
    assert remembered is not None and set(remembered["matches"]) == {FB}
