"""`web/public/data/platform.json` (task 34) against the real build record and
`stats.json`, independently -- `matches[].silver_frames_rows` is read off the
build record's Parquet footers (`tracklab.build.measure_table`), `stats.json`
off a `duckdb` `count(*)` query (`tracklab.silver.stats.count_table`); the two
code paths never share a line, so agreeing here is not by construction.
Skipped without a built and published bundle, same as `tests/publish/
test_stats.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tracklab.build import RECORD_DIR
from tracklab.publish.format import fmt
from tracklab.publish.platform import latest_record, run_publish_platform

PIPELINE = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE.parent
DATA = PIPELINE / "data"
PLATFORM_JSON = REPO_ROOT / "web" / "public" / "data" / "platform.json"
STATS_JSON = REPO_ROOT / "web" / "public" / "data" / "stats.json"
MAX_BYTES = 60_000

pytestmark = pytest.mark.skipif(
    not DATA.is_dir() or not PLATFORM_JSON.is_file() or not STATS_JSON.is_file(),
    reason="pipeline/data or web/public/data/platform.json missing; "
    "run `tracklab build` then `tracklab publish stats` and `tracklab publish platform`",
)


def _payload() -> dict[str, Any]:
    return json.loads(PLATFORM_JSON.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _stats() -> dict[str, Any]:
    return json.loads(STATS_JSON.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_platform_json_is_below_60kb() -> None:
    size = PLATFORM_JSON.stat().st_size
    print(f"platform.json: {size} bytes")
    assert size < MAX_BYTES


def test_title_is_fmt_of_bytes_pinned_and_the_publish_layers_bytes() -> None:
    payload = _payload()
    raw_layer = next(layer for layer in payload["layers"] if layer["layer"] == "raw")
    publish_layer = next(layer for layer in payload["layers"] if layer["layer"] == "publish")
    print(f"title: {payload['title']}")
    expected = f"{fmt(raw_layer['bytes_pinned'])} in, {fmt(publish_layer['bytes'])} out"
    assert payload["title"] == expected


def test_raw_bytes_over_matches_plus_season_files_is_bytes_pinned() -> None:
    payload = _payload()
    total = sum(m["raw_bytes"] for m in payload["matches"]) + payload["season_files"]["bytes"]
    raw_layer = next(layer for layer in payload["layers"] if layer["layer"] == "raw")
    print(f"matches+season_files={total} bytes_pinned={raw_layer['bytes_pinned']}")
    assert total == raw_layer["bytes_pinned"]


def test_thirty_matches_each_with_a_sport_and_a_match_id() -> None:
    payload = _payload()
    assert len(payload["matches"]) == 30
    assert {m["sport"] for m in payload["matches"]} == {"basketball", "football"}


def test_silver_rows_per_match_agree_with_stats_json_independently() -> None:
    """The lesson task 32 and 33 both left behind: a test that would pass by
    construction (the same function computing both sides) proves nothing.
    `stats.json`'s rows come from `tracklab.silver.stats.count_table`
    (`duckdb`); `platform.json`'s come from `tracklab.build.measure_table`
    (`pyarrow.parquet.read_metadata`). Comparing the two files, not the two
    functions, is what this test is for."""
    payload = _payload()
    stats = _stats()
    stats_rows = {
        (row["sport"], row["table"], row["match_id"]): row["rows"]
        for row in stats["tables"]
        if row["table"] in ("frames", "events") and row["match_id"]
    }
    mismatches = []
    for m in payload["matches"]:
        prefix = "bb" if m["sport"] == "basketball" else "fb"
        composite = f"{prefix}:{m['match_id']}"
        for field, table in (("silver_frames_rows", "frames"), ("silver_events_rows", "events")):
            expected = stats_rows.get((m["sport"], table, composite))
            if expected is not None and expected != m[field]:
                mismatches.append((m["sport"], m["match_id"], field, m[field], expected))
    print(
        f"checked {len(payload['matches'])} matches against stats.json, "
        f"{len(mismatches)} mismatch(es)"
    )
    assert mismatches == []


def test_no_local_traces(assert_no_local_traces: Any) -> None:
    assert_no_local_traces(_payload())


def test_check_passes_against_the_versioned_file_and_the_newest_record() -> None:
    out_dir = PLATFORM_JSON.parent
    record = latest_record(RECORD_DIR)
    code = run_publish_platform(
        record_path=record, record_dir=RECORD_DIR, out_dir=out_dir, check=True
    )
    assert code == 0
