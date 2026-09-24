"""`tracklab quality detection` on a fabricated, partitioned `frames`.

The real bundles only show the extremes (a ball never marked as seen, players
seen most of the time); the counts here are chosen so every share is exact.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb

from tracklab.quality.common import report_path
from tracklab.quality.run import run_quality


def _frames(data_dir: Path) -> None:
    path = data_dir / "silver" / "frames"
    path.mkdir(parents=True)
    # bb:1: player seen 3 of 4 rows, ball never; fb:9: player seen 1 of 2, ball 2 of 2.
    duckdb.connect().execute(
        f"""
        COPY (
            SELECT * FROM (VALUES
                ('basketball', 'bb:1', 1, 'player', true),
                ('basketball', 'bb:1', 1, 'player', true),
                ('basketball', 'bb:1', 1, 'player', true),
                ('basketball', 'bb:1', 1, 'player', false),
                ('basketball', 'bb:1', 1, 'ball', false),
                ('basketball', 'bb:1', 1, 'ball', false),
                ('football', 'fb:9', 9, 'player', true),
                ('football', 'fb:9', 9, 'player', false),
                ('football', 'fb:9', 9, 'ball', true),
                ('football', 'fb:9', 9, 'ball', true)
            ) t(sport, match_id, native_match_id, entity_kind, is_detected)
        ) TO '{path.as_posix()}' (FORMAT PARQUET, PARTITION_BY (sport, native_match_id))
        """
    )


def test_detection_shares_per_sport_match_and_kind(tmp_path: Path) -> None:
    _frames(tmp_path / "data")
    reports = tmp_path / "reports"

    assert run_quality(["detection"], data_dir=tmp_path / "data", reports_dir=reports) == 0

    with report_path(reports, "detection").open(encoding="utf-8", newline="") as handle:
        rows = {(r["sport"], r["match_id"], r["metric"]): r for r in csv.DictReader(handle)}
    got = {key: (float(r["value"]), int(r["n"])) for key, r in rows.items()}
    assert got == {
        ("basketball", "bb:1", "player_detected_pct"): (75.0, 4),
        ("basketball", "bb:1", "ball_detected_pct"): (0.0, 2),
        ("football", "fb:9", "player_detected_pct"): (50.0, 2),
        ("football", "fb:9", "ball_detected_pct"): (100.0, 2),
    }


def test_an_unknown_check_fails(tmp_path: Path) -> None:
    assert run_quality(["gravity?"], data_dir=tmp_path, reports_dir=tmp_path) == 1
