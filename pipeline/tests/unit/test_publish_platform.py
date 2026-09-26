"""`tracklab publish platform` (task 34) on a fabricated build record: the two
decisions the real data cannot exercise by itself -- the title's "out" must
come from the record's own pre-lineage, pre-platform snapshot of
`web/public/data` (decision 1), and a manifest entry with no `match_id` is a
season file, never folded into a match's `raw_bytes` (decision 2) -- plus
`--check` against a hand-edited `platform.json`.

Against the real graph and record: `tests/publish/test_platform.py`, skipped
without a built bundle, same as `tests/publish/test_stats.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tracklab.publish.platform import (
    latest_record,
    layers_from_record,
    matches_from_record,
    platform_from_record,
    run_publish_platform,
    season_files_from_record,
    tables_from_record,
    title_from_record,
)


def _raw_entry(
    path: str, role: str, match_id: int | None, bytes_: int, bytes_read: int | None = None
) -> dict[str, Any]:
    return {
        "path": path,
        "role": role,
        "match_id": match_id,
        "bytes": bytes_,
        "bytes_read": bytes_ if bytes_read is None else bytes_read,
    }


def _source(sport: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"sport": sport, "manifest": entries}


def _parquet(path: str, rows: int, bytes_: int) -> dict[str, Any]:
    return {"path": path, "rows": rows, "bytes": bytes_}


def _table(
    layer: str, sport: str | None, table: str, files: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "layer": layer,
        "sport": sport,
        "table": table,
        "files": len(files),
        "rows": sum(f["rows"] for f in files),
        "bytes": sum(f["bytes"] for f in files),
        "parquet": files,
    }


def _step(
    step_key: str, group: str, duration_ms: float | None, status: str = "success"
) -> dict[str, Any]:
    return {
        "step_key": step_key,
        "assets": [step_key],
        "group": group,
        "status": status,
        "duration_ms": duration_ms,
        "dbt_seconds": {},
    }


def _record() -> dict[str, Any]:
    """Two matches (basketball 1, football 2001), one season file per sport plus
    a season bronze table (`matches`) and a season silver table (`dim_match`),
    neither of which names a match anywhere a match-shaped path would."""
    raw_bb = _source(
        "basketball",
        [
            _raw_entry("data/matches/1/1_tracking.jsonl.gz", "tracking", 1, 1000),
            _raw_entry("data/matches/1/1_game_data.json", "game_data", 1, 200),
            _raw_entry("data/aggregates/acb_shots.csv", "aggregate", None, 50),
            _raw_entry("data/matches.json", "matches", None, 30),
        ],
    )
    raw_fb = _source(
        "football",
        [
            _raw_entry("data/matches/2001/2001_tracking.jsonl.gz", "tracking", 2001, 500, 800),
            _raw_entry("data/matches/2001/2001_match.json", "match", 2001, 100),
            _raw_entry("data/matches.json", "matches", None, 40),
        ],
    )
    bronze_tables = [
        _table("bronze", "basketball", "tracking_frames", [_parquet("1.parquet", 10, 100)]),
        _table("bronze", "football", "tracking_frames", [_parquet("2001.parquet", 20, 200)]),
        _table("bronze", "basketball", "matches", [_parquet("data.parquet", 5, 50)]),
    ]
    silver_tables = [
        _table(
            "silver",
            None,
            "frames",
            [
                _parquet("sport=basketball/native_match_id=1/data_0.parquet", 7, 70),
                _parquet("sport=football/native_match_id=2001/data_0.parquet", 9, 90),
            ],
        ),
        _table(
            "silver",
            None,
            "events",
            [
                _parquet("sport=basketball/native_match_id=1/data_0.parquet", 3, 30),
                _parquet("sport=football/native_match_id=2001/data_0.parquet", 4, 40),
            ],
        ),
        _table("silver", None, "dim_match", [_parquet("data.parquet", 2, 20)]),
    ]
    return {
        "schema_version": 1,
        "git_sha": "abc1234",
        "select": None,
        "started_utc": "2026-09-24T17:00:00+00:00",
        "finished_utc": "2026-09-24T17:10:00+00:00",
        "wall_seconds": 600.0,
        "host": {"system": "Linux", "cpus": 8, "ram_gb": 32.0},
        "versions": {"python": "3.13.0"},
        "steps": [
            _step("raw_basketball", "ingest", 2000.0),
            _step("raw_football", "ingest", 3000.0),
            _step("bronze_basketball", "bronze", 5000.0),
            _step("bronze_football", "bronze", 8000.0),
            _step("silver", "silver", 4000.0),
            _step("quality_x", "quality", 1000.0),
            _step("publish_stats", "publish", 500.0),
            _step("bronze_skipped", "bronze", None, status="skipped"),
        ],
        "disk": {
            "raw": {
                "files": 7,
                "bytes_pinned": 1920,
                "downloaded": 0,
                "verified": 2,
                "files_read": 7,
                "bytes_read": 2220,
                "receipts": 2,
                "sources": [raw_bb, raw_fb],
            },
            "bronze": {
                "files": sum(t["files"] for t in bronze_tables),
                "rows": sum(t["rows"] for t in bronze_tables),
                "bytes": sum(t["bytes"] for t in bronze_tables),
                "tables": bronze_tables,
            },
            "silver": {
                "files": sum(t["files"] for t in silver_tables),
                "rows": sum(t["rows"] for t in silver_tables),
                "bytes": sum(t["bytes"] for t in silver_tables),
                "tables": silver_tables,
            },
            "quality": {
                "files": 1,
                "rows": 6,
                "bytes": 60,
                "csv": [{"path": "quality_x.csv", "rows": 6, "bytes": 60}],
            },
            "publish": {
                "files": 2,
                "bytes": 300,
                "json": [
                    {"path": "stats.json", "bytes": 150},
                    {"path": "index.json", "bytes": 150},
                ],
            },
        },
    }


def _index() -> dict[str, Any]:
    return {
        "possessions": [
            {"sport": "basketball", "match_id": "bb:1", "bytes": 123},
            {"sport": "football", "match_id": "fb:2001", "bytes": 456},
            {"sport": "football", "match_id": "fb:2001", "bytes": 789},
        ]
    }


# --- decision 1: the title's "out" is the record's pre-lineage, pre-platform snapshot --


def test_title_uses_bytes_pinned_and_the_records_own_publish_snapshot() -> None:
    assert title_from_record(_record()) == "1.9 KB in, 300 B out"


def test_publish_layer_carries_a_note_explaining_why_it_is_not_a_live_rescan() -> None:
    layers = layers_from_record(_record())
    publish_layer = next(entry for entry in layers if entry["layer"] == "publish")
    assert publish_layer["bytes"] == 300
    assert "lineage.json" in publish_layer["note"] and "platform.json" in publish_layer["note"]


def test_raw_layer_has_no_row_count_but_bronze_and_quality_do() -> None:
    layers = {entry["layer"]: entry for entry in layers_from_record(_record())}
    assert layers["raw"]["rows"] is None
    assert layers["publish"]["rows"] is None
    assert layers["bronze"]["rows"] == 35
    assert layers["quality"]["rows"] == 6


def test_layer_seconds_is_the_slowest_step_the_sum_is_separate_and_informative() -> None:
    layers = {entry["layer"]: entry for entry in layers_from_record(_record())}
    assert layers["raw"]["seconds"] == 3.0
    assert layers["raw"]["seconds_sum"] == 5.0
    assert layers["bronze"]["seconds"] == 8.0
    assert layers["bronze"]["seconds_sum"] == 13.0


# --- decision 2: files with no match id are season files, never a match's --------------


def test_season_files_exclude_aggregates_and_matches_json_from_every_match() -> None:
    record = _record()
    season = season_files_from_record(record)
    matches = matches_from_record(record, {"possessions": []})

    assert season["files"] == 3
    assert season["bytes"] == 50 + 30 + 40
    assert {item["path"] for item in season["items"]} == {
        "data/aggregates/acb_shots.csv",
        "data/matches.json",
    }
    # data/matches.json appears once per source (one per sport), never merged.
    assert sum(1 for item in season["items"] if item["path"] == "data/matches.json") == 2

    by_match = {(m["sport"], m["match_id"]): m for m in matches}
    assert by_match[("basketball", 1)]["raw_bytes"] == 1200  # tracking + game_data only
    assert by_match[("football", 2001)]["raw_bytes"] == 600  # tracking + match only


def test_raw_bytes_plus_season_files_reconciles_to_bytes_pinned() -> None:
    record = _record()
    matches = matches_from_record(record, {"possessions": []})
    season = season_files_from_record(record)
    reconciled = sum(m["raw_bytes"] for m in matches) + season["bytes"]
    assert reconciled == record["disk"]["raw"]["bytes_pinned"]


def test_raw_bytes_read_plus_season_files_reconciles_to_the_raw_bytes_read() -> None:
    record = _record()
    matches = matches_from_record(record, {"possessions": []})
    season = season_files_from_record(record)
    assert season["bytes_read"] == 120
    reconciled = sum(m["raw_bytes_read"] for m in matches) + season["bytes_read"]
    assert reconciled == record["disk"]["raw"]["bytes_read"]


def test_a_record_whose_disk_measure_failed_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = {**_record(), "disk": {"error": "ArrowInvalid: truncated"}}
    path = tmp_path / "20260924T170000Z_abc1234.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    code = run_publish_platform(record_path=path, record_dir=tmp_path, out_dir=tmp_path / "out")

    assert code == 1
    assert "ArrowInvalid: truncated" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_a_season_bronze_and_silver_table_never_shows_up_in_any_match() -> None:
    """`bronze.matches` (`data.parquet`, no per-match filename) and
    `silver.dim_match` (`data.parquet`, no `native_match_id=` partition) are
    season tables; only their totals appear in `tables_from_record`, and
    `matches_from_record` never attributes their rows to match 1 or 2001."""
    record = _record()
    matches = matches_from_record(record, {"possessions": []})
    by_match = {(m["sport"], m["match_id"]): m for m in matches}
    assert by_match[("basketball", 1)]["bronze_tracking_rows"] == 10  # not 10 + 5
    tables = {(t["layer"], t["sport"], t["table"]): t for t in tables_from_record(record)}
    assert tables[("bronze", "basketball", "matches")]["rows"] == 5
    assert tables[("silver", None, "dim_match")]["rows"] == 2


def test_mutation_giving_matches_json_a_match_id_moves_its_bytes_out_of_season_files() -> None:
    """The mutation tasks/todo.md asks for: attribute `data/matches.json` to a
    match instead of leaving its manifest `match_id` `None` (a manifest bug
    task 34 does not own -- `ingest/manifest.py`'s patterns give season files
    no match group to capture -- but reproduced here on fabricated input,
    since the real manifest never has it). `season_files_from_record` then
    silently drops those bytes, and `matches_from_record` silently gains
    them: proof the split has exactly one signal, `match_id is None`, and no
    fallback that would catch a wrongly tagged entry."""
    record = _record()
    record["disk"]["raw"]["sources"][0]["manifest"][3]["match_id"] = 1  # was None

    season = season_files_from_record(record)
    matches = matches_from_record(record, {"possessions": []})
    by_match = {(m["sport"], m["match_id"]): m for m in matches}

    assert season["bytes"] == 50 + 40  # basketball's matches.json (30) no longer counted
    assert by_match[("basketball", 1)]["raw_bytes"] == 1230  # 1200 + the misattributed 30


# --- matches_from_record: raw, bronze, silver and published possessions together ------


def test_matches_from_record_reads_every_source_by_its_own_convention() -> None:
    matches = matches_from_record(_record(), _index())
    by_match = {(m["sport"], m["match_id"]): m for m in matches}

    assert len(matches) == 2
    bb = by_match[("basketball", 1)]
    assert (bb["raw_bytes"], bb["raw_bytes_read"]) == (1200, 1200)
    bb_rows = (bb["bronze_tracking_rows"], bb["silver_frames_rows"], bb["silver_events_rows"])
    assert bb_rows == (10, 7, 3)
    assert (bb["published_possessions"], bb["published_bytes"]) == (1, 123)

    fb = by_match[("football", 2001)]
    assert (fb["raw_bytes"], fb["raw_bytes_read"]) == (600, 900)  # the .gz reads larger than pinned
    fb_rows = (fb["bronze_tracking_rows"], fb["silver_frames_rows"], fb["silver_events_rows"])
    assert fb_rows == (20, 9, 4)
    assert (fb["published_possessions"], fb["published_bytes"]) == (2, 1245)


def test_a_match_with_no_published_possession_is_zero_not_absent() -> None:
    matches = matches_from_record(_record(), {"possessions": []})
    assert all(m["published_possessions"] == 0 and m["published_bytes"] == 0 for m in matches)


def test_no_local_traces(assert_no_local_traces: Any) -> None:
    payload = platform_from_record(_record(), _index())
    assert_no_local_traces(payload)


def test_platform_from_record_assembles_every_section() -> None:
    payload = platform_from_record(_record(), _index())
    assert payload["schema_version"] == 1
    assert payload["title"] == "1.9 KB in, 300 B out"
    assert {entry["layer"] for entry in payload["layers"]} == {
        "raw",
        "bronze",
        "silver",
        "quality",
        "publish",
    }
    assert len(payload["matches"]) == 2
    assert payload["run"]["git_sha"] == "abc1234"
    assert "host" not in payload  # only inside run, not duplicated at the top level


# --- --check: rows by table and by match, against the record and stats.json -----------


def _write_record(record_dir: Path, record: dict[str, Any]) -> Path:
    record_dir.mkdir(parents=True, exist_ok=True)
    path = record_dir / "20260924T170000Z_abc1234.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_check_is_0_against_a_freshly_written_platform_json_and_1_after_a_hand_edit(
    tmp_path: Path,
) -> None:
    record_dir = tmp_path / "build"
    out_dir = tmp_path / "web"
    out_dir.mkdir(parents=True)
    _write_record(record_dir, _record())
    (out_dir / "index.json").write_text(json.dumps(_index()), encoding="utf-8")

    written = run_publish_platform(record_path=None, record_dir=record_dir, out_dir=out_dir)
    assert written == 0
    assert (out_dir / "platform.json").is_file()

    ok = run_publish_platform(record_path=None, record_dir=record_dir, out_dir=out_dir, check=True)
    assert ok == 0

    payload = json.loads((out_dir / "platform.json").read_text(encoding="utf-8"))
    for match in payload["matches"]:
        if match["sport"] == "basketball":
            match["silver_frames_rows"] = 999  # a hand edit
    (out_dir / "platform.json").write_text(json.dumps(payload), encoding="utf-8")

    broken = run_publish_platform(
        record_path=None, record_dir=record_dir, out_dir=out_dir, check=True
    )
    assert broken == 1


def test_check_cross_validates_silver_rows_against_an_independent_stats_json(
    tmp_path: Path,
) -> None:
    """`stats.json`'s rows are not read by `matches_from_record` at all (they
    come from the record's Parquet footers); `--check` reads them
    separately, so a record that disagrees with a present `stats.json` is
    caught even when `platform.json` itself agrees with the record it was
    built from."""
    record_dir = tmp_path / "build"
    out_dir = tmp_path / "web"
    out_dir.mkdir(parents=True)
    _write_record(record_dir, _record())
    (out_dir / "index.json").write_text(json.dumps(_index()), encoding="utf-8")
    run_publish_platform(record_path=None, record_dir=record_dir, out_dir=out_dir)

    stats = {
        "tables": [
            {"table": "frames", "sport": "basketball", "match_id": "bb:1", "rows": 7},
            {"table": "frames", "sport": "football", "match_id": "fb:2001", "rows": 9},
            {"table": "events", "sport": "basketball", "match_id": "bb:1", "rows": 3},
            # the record says 4, not 999: the mismatch this test is for.
            {"table": "events", "sport": "football", "match_id": "fb:2001", "rows": 999},
        ]
    }
    (out_dir / "stats.json").write_text(json.dumps(stats), encoding="utf-8")

    code = run_publish_platform(
        record_path=None, record_dir=record_dir, out_dir=out_dir, check=True
    )
    assert code == 1


def test_check_fails_when_platform_json_is_missing(tmp_path: Path) -> None:
    record_dir = tmp_path / "build"
    out_dir = tmp_path / "web"
    out_dir.mkdir(parents=True)
    _write_record(record_dir, _record())

    code = run_publish_platform(
        record_path=None, record_dir=record_dir, out_dir=out_dir, check=True
    )
    assert code == 1


def test_latest_record_picks_the_newest_by_name(tmp_path: Path) -> None:
    record_dir = tmp_path / "build"
    record_dir.mkdir()
    (record_dir / "20260101T000000Z_aaaaaaa.json").write_text("{}", encoding="utf-8")
    newest = record_dir / "20260924T170000Z_abc1234.json"
    newest.write_text("{}", encoding="utf-8")

    assert latest_record(record_dir) == newest


def test_latest_record_raises_without_any_record(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        latest_record(tmp_path / "build")
