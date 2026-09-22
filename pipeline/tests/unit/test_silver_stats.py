"""`tracklab stats` on fabricated silver tables.

The point of every case here is a shape the built repository cannot show: a
sport missing from a table, a table with no sport at all, a (match, period)
group with the wrong number of teams, and a silver directory that is not there.
Counting the real tables is the contract test's job.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from tracklab.silver.stats import run_stats, stats_report_path


def _table(data_dir: Path, name: str, sql: str) -> None:
    path = data_dir / "silver" / name
    path.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(
        f"COPY ({sql}) TO '{(path / 'data.parquet').as_posix()}' (FORMAT PARQUET)"
    )


def _report(reports: Path) -> list[list[str]]:
    with stats_report_path(reports).open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_counts_by_the_sport_column_when_there_is_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _table(
        tmp_path,
        "dim_match",
        "SELECT 'basketball' AS sport UNION ALL SELECT 'football' UNION ALL SELECT 'football'",
    )

    assert run_stats(tmp_path, tmp_path / "reports") == 0

    assert "silver dim_match: 3 rows (basketball 1, football 2)" in capsys.readouterr().out
    assert _report(tmp_path / "reports") == [
        ["table", "sport", "rows"],
        ["dim_match", "basketball", "1"],
        ["dim_match", "football", "2"],
    ]


def test_counts_by_the_id_prefix_when_there_is_no_sport_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """dim_period and dim_entity carry no `sport`; the prefix of a silver id is
    what says which sport it belongs to (decision 4)."""
    _table(tmp_path, "dim_period", "SELECT 'bb:114086' AS match_id UNION ALL SELECT 'fb:1874553'")

    run_stats(tmp_path, tmp_path / "reports")

    assert "silver dim_period: 2 rows (basketball 1, football 1)" in capsys.readouterr().out


def test_a_table_with_neither_is_counted_whole(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _table(tmp_path, "event_type_map", "SELECT 'pass' AS event_type UNION ALL SELECT 'shot'")

    run_stats(tmp_path, tmp_path / "reports")

    assert "silver event_type_map: 2 rows (all 2)" in capsys.readouterr().out


def test_prints_the_team_per_group_range_even_when_it_is_wrong(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A group with three teams is a broken probe, and stats says so by printing
    the range rather than by passing judgement: the verdict belongs to the dbt
    test that asserts exactly two."""
    _table(
        tmp_path,
        "dim_team_period",
        "SELECT 'bb:1' AS match_id, 1 AS period, 'bb:10' AS team_id "
        "UNION ALL SELECT 'bb:1', 1, 'bb:11' "
        "UNION ALL SELECT 'bb:1', 1, 'bb:12' "
        "UNION ALL SELECT 'bb:1', 2, 'bb:10'",
    )

    run_stats(tmp_path, tmp_path / "reports")

    out = capsys.readouterr().out
    assert "silver dim_team_period: 2 (match, period) groups, teams per group min=1 max=3" in out


def test_no_silver_at_all_fails_and_says_what_to_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_stats(tmp_path, tmp_path / "reports") == 1

    assert "run dbt build first" in capsys.readouterr().out
    assert not stats_report_path(tmp_path / "reports").exists()
