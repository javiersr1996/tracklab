"""`tracklab publish warehouse` (task 41): reproducible Parquet, a `--check` that can fail,
and a delete of old-hash files that cannot touch anything else.

The writer tests run on a small synthetic gold written into `tmp_path`, so they hold on any
data root. The tests of the committed files and of `warehouse.json` use the real files. The
comparison against gold also runs on the CI fixtures: they carry the six aggregates whole,
which is all gold reads, so the committed bytes must come out of them too (and out of the
Linux runner, which is the one proof that pyarrow writes the same bytes there).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from tracklab.paths import data_root
from tracklab.publish import warehouse
from tracklab.publish.warehouse import (
    HASHED_FILE,
    TABLES,
    run_publish_warehouse,
    stale_files,
    warehouse_dir,
    warehouse_path,
)

PIPELINE = Path(__file__).resolve().parents[2]
WEB_DATA = PIPELINE.parent / "web" / "public" / "data"


def _write_gold(root: Path) -> Path:
    """Seven gold tables: the grain columns plus one metric, rows in scrambled order."""
    con = duckdb.connect()
    for table, model, sport in TABLES:
        directory = root / "gold" / model
        directory.mkdir(parents=True)
        football = table.startswith("fb_")
        if table == "fact":
            select = (
                "SELECT 'basketball' AS sport, 'shots' AS family, i AS player_id, "
                "10 + i % 3 AS team_id, NULL::VARCHAR AS position_group, "
                "false AS is_season_total, "
                "'m' || lpad(((i * 7) % 40)::VARCHAR, 2, '0') AS metric, i * 0.5 AS value "
                "FROM range(200) t(i)"
            )
        else:
            position = "'Forward'" if football else "NULL::VARCHAR"
            select = (
                f"SELECT '{sport}' AS sport, ((i * 37) % 60) AS player_id, "
                f"10 + i % 3 AS team_id, {position} AS position_group, i AS attempts "
                "FROM range(60) t(i)"
            )
        path = (directory / "data.parquet").as_posix()
        con.execute(f"COPY ({select}) TO '{path}' (FORMAT parquet)")
    return root


@pytest.fixture
def gold_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(warehouse, "FACT_ROW_GROUP_ROWS", 64)
    return _write_gold(tmp_path / "root")


def _hashes(directory: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.parquet")}


def test_two_runs_give_the_same_bytes(gold_root: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    assert run_publish_warehouse(gold_root, first) == 0
    assert run_publish_warehouse(gold_root, second) == 0
    hashes = _hashes(warehouse_dir(first))
    print(hashes)
    assert hashes == _hashes(warehouse_dir(second))
    assert len(hashes) == len(TABLES)
    assert warehouse_path(first).read_bytes() == warehouse_path(second).read_bytes()
    assert b"\r" not in warehouse_path(first).read_bytes()


def test_the_footer_says_it_was_written_by_the_pinned_pyarrow(
    gold_root: Path, tmp_path: Path
) -> None:
    run_publish_warehouse(gold_root, tmp_path)
    manifest = json.loads(warehouse_path(tmp_path).read_text(encoding="utf-8"))
    for entry in manifest["tables"]:
        created_by = pq.read_metadata(warehouse_dir(tmp_path) / entry["file"]).created_by
        assert manifest["writer"]["version"] in created_by
        assert entry["file"] == f"{entry['table']}.{entry['sha256'][:8]}.parquet"


def test_an_interrupted_delete_leaves_the_new_manifest_pointing_at_files_that_exist(
    gold_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_publish_warehouse(gold_root, tmp_path)
    old = warehouse_path(tmp_path).read_bytes()
    path = (gold_root / "gold" / "agg_fb_obr" / "data.parquet").as_posix()
    duckdb.connect().execute(
        f"COPY (SELECT * FROM '{path}' WHERE player_id <> 0) TO '{path}.new' (FORMAT parquet)"
    )
    Path(f"{path}.new").replace(path)

    def interrupted(self: Path, *args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "unlink", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_publish_warehouse(gold_root, tmp_path)
    monkeypatch.undo()

    manifest = json.loads(warehouse_path(tmp_path).read_text(encoding="utf-8"))
    assert warehouse_path(tmp_path).read_bytes() != old
    assert all((warehouse_dir(tmp_path) / t["file"]).is_file() for t in manifest["tables"])


def test_check_passes_then_fails_after_one_byte_changes(gold_root: Path, tmp_path: Path) -> None:
    run_publish_warehouse(gold_root, tmp_path)
    assert run_publish_warehouse(gold_root, tmp_path, check=True) == 0

    target = next(warehouse_dir(tmp_path).glob("bb_shots.*.parquet"))
    original = target.read_bytes()
    target.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    assert run_publish_warehouse(gold_root, tmp_path, check=True) == 1
    target.write_bytes(original)
    assert run_publish_warehouse(gold_root, tmp_path, check=True) == 0

    manifest = warehouse_path(tmp_path)
    text = manifest.read_text(encoding="utf-8")
    assert '"rows": 60' in text
    manifest.write_text(text.replace('"rows": 60', '"rows": 61', 1), encoding="utf-8", newline="\n")
    assert run_publish_warehouse(gold_root, tmp_path, check=True) == 1


def test_check_fails_when_gold_changes_underneath(gold_root: Path, tmp_path: Path) -> None:
    run_publish_warehouse(gold_root, tmp_path)
    path = (gold_root / "gold" / "agg_fb_obr" / "data.parquet").as_posix()
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM '{path}' WHERE player_id <> 0) TO '{path}.new' (FORMAT parquet)"
    )
    Path(f"{path}.new").replace(path)
    assert run_publish_warehouse(gold_root, tmp_path, check=True) == 1


def test_the_fact_has_several_row_groups_with_footer_min_and_max(
    gold_root: Path, tmp_path: Path
) -> None:
    run_publish_warehouse(gold_root, tmp_path)
    manifest = json.loads(warehouse_path(tmp_path).read_text(encoding="utf-8"))
    fact = next(t for t in manifest["tables"] if t["table"] == "fact")
    groups = fact["row_groups"]
    assert fact["order_by"][0] == "metric"
    assert [g["rows"] for g in groups] == [64, 64, 64, 8]

    # Same ranges by another road: sort in DuckDB, cut into 64-row chunks, min/max per chunk.
    con = duckdb.connect()
    gold = (gold_root / "gold" / "fact_player_season_metric" / "data.parquet").as_posix()
    ordering = ", ".join(f"{c} NULLS LAST" for c in fact["order_by"])
    expected = con.execute(
        "SELECT min(metric), max(metric) FROM (SELECT metric, "
        f"(row_number() OVER (ORDER BY {ordering}) - 1) // 64 AS g FROM '{gold}') "
        "GROUP BY g ORDER BY g"
    ).fetchall()
    assert [(g["min"], g["max"]) for g in groups] == expected


def test_old_hash_files_go_and_nothing_else_does(gold_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    directory = warehouse_dir(out)
    directory.mkdir(parents=True)
    old = directory / "bb_shots.deadbeef.parquet"
    old.write_bytes(b"old")
    look_alikes = [
        directory / "notes.txt",
        directory / "bb_shots.parquet",  # no hash
        directory / "bb_shots.deadbeeg.parquet",  # not hex
        directory / "bb_shots.deadbeef0.parquet",  # nine digits
        directory / "other.deadbeef.parquet",  # not a table of this module
        directory / "x_bb_shots.deadbeef.parquet",  # prefix
        directory / "bb_shots.deadbeef.parquet.bak",  # suffix
    ]
    for path in look_alikes:
        path.write_bytes(b"mine")
    outside = out / "bb_shots.deadbeef.parquet"  # right name, wrong directory
    outside.write_bytes(b"outside")

    assert run_publish_warehouse(gold_root, out) == 0
    assert not old.exists()
    assert all(p.read_bytes() == b"mine" for p in look_alikes)
    assert outside.read_bytes() == b"outside"
    # Publishing again removes nothing it just wrote, and still sees nothing stale.
    assert run_publish_warehouse(gold_root, out) == 0
    assert stale_files(directory, {t["file"] for t in _manifest(out)}) == []
    assert run_publish_warehouse(gold_root, out, check=True) == 0

    # An old hash left behind next to a good publish is what `--check` reports.
    (directory / "fact.00000000.parquet").write_bytes(b"old")
    assert run_publish_warehouse(gold_root, out, check=True) == 1


def _manifest(out: Path) -> list[dict[str, object]]:
    return json.loads(warehouse_path(out).read_text(encoding="utf-8"))["tables"]  # type: ignore[no-any-return]


def test_hashed_file_pattern_is_exact() -> None:
    assert HASHED_FILE.fullmatch("fact.0123abcd.parquet")
    assert not HASHED_FILE.fullmatch("fact.0123abcd.parquet.bak")
    assert not HASHED_FILE.fullmatch("../fact.0123abcd.parquet")


def test_no_gold_is_an_error_not_a_crash(tmp_path: Path) -> None:
    assert run_publish_warehouse(tmp_path, tmp_path / "out") == 1
    assert not (tmp_path / "out").exists()


def test_the_manifest_names_no_machine(
    gold_root: Path, tmp_path: Path, assert_no_local_traces: Callable[[object], None]
) -> None:
    run_publish_warehouse(gold_root, tmp_path)
    assert_no_local_traces(json.loads(warehouse_path(tmp_path).read_text(encoding="utf-8")))


# --- the files in the repository -------------------------------------------------------

committed = pytest.mark.skipif(
    not warehouse_path(WEB_DATA).is_file(), reason="warehouse.json not published yet"
)


@committed
def test_committed_files_match_their_names_and_the_manifest() -> None:
    manifest = json.loads(warehouse_path(WEB_DATA).read_text(encoding="utf-8"))
    directory = warehouse_dir(WEB_DATA)
    assert sorted(p.name for p in directory.glob("*.parquet")) == sorted(
        t["file"] for t in manifest["tables"]
    )
    for entry in manifest["tables"]:
        data = (directory / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["bytes"]
        assert re.fullmatch(rf"{entry['table']}\.{entry['sha256'][:8]}\.parquet", entry["file"])
    fact = next(t for t in manifest["tables"] if t["table"] == "fact")
    print(f"fact: {fact['rows']} rows in {len(fact['row_groups'])} row groups")
    assert len(fact["row_groups"]) > 1


@committed
def test_committed_row_groups_equal_the_footers_read_by_duckdb() -> None:
    manifest = json.loads(warehouse_path(WEB_DATA).read_text(encoding="utf-8"))
    con = duckdb.connect()
    for entry in manifest["tables"]:
        path = (warehouse_dir(WEB_DATA) / entry["file"]).as_posix()
        key = entry["order_by"][0]
        footer = con.execute(
            "SELECT row_group_id, any_value(row_group_num_rows), "
            "any_value(stats_min_value), any_value(stats_max_value) "
            f"FROM parquet_metadata('{path}') WHERE path_in_schema = '{key}' "
            "GROUP BY row_group_id ORDER BY row_group_id"
        ).fetchall()
        published = [(g["rows"], str(g["min"]), str(g["max"])) for g in entry["row_groups"]]
        assert [(r, str(lo), str(hi)) for _, r, lo, hi in footer] == published
        assert entry["columns"] == pq.read_metadata(path).num_columns


@committed
@pytest.mark.skipif(
    not (data_root() / "gold").is_dir(),
    reason="needs a gold build; run dbt build --select gold",
)
def test_rows_in_the_manifest_equal_the_gold_rows_counted_by_duckdb() -> None:
    manifest = json.loads(warehouse_path(WEB_DATA).read_text(encoding="utf-8"))
    con = duckdb.connect()
    for table, model, _ in TABLES:
        gold = (data_root() / "gold" / model / "data.parquet").as_posix()
        counted = con.execute(f"SELECT count(*) FROM read_parquet('{gold}')").fetchone()
        assert counted is not None
        rows = next(t["rows"] for t in manifest["tables"] if t["table"] == table)
        print(f"{table}: manifest {rows}, gold {counted[0]}")
        assert rows == counted[0]


@committed
@pytest.mark.skipif(
    not (data_root() / "gold").is_dir(),
    reason="needs a gold build; run dbt build --select gold",
)
def test_gold_rebuilt_from_scratch_regenerates_the_committed_bytes() -> None:
    """What the clean clone runs after `tracklab build`: the files in git are what gold gives."""
    assert run_publish_warehouse(data_root(), WEB_DATA, check=True) == 0
