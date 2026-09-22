"""`tracklab stats`: count what silver actually holds, print it, write it down.

Every figure the web or a document quotes has to come from an artefact rather
than from the code that built it, so this command reads the Parquet that dbt
wrote and writes `reports/stats_silver.csv`. It counts what is on disk and never
rebuilds anything: if a model was not built, its row is simply absent, and a
count that surprises someone is a fact about the data and not about this file.

Task 10 covers the dimensions. `stats.json` for the web is task 17's, and it
reads these same counts rather than computing its own.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import duckdb

# The prefix of a silver id says the sport (decision 4), which is how the tables
# with no `sport` column of their own are split.
SPORT_BY_PREFIX = {"bb": "basketball", "fb": "football"}


def silver_dir(data_dir: Path) -> Path:
    return data_dir / "silver"


def table_path(data_dir: Path, table: str) -> Path:
    return silver_dir(data_dir) / table / "data.parquet"


def stats_report_path(reports_dir: Path) -> Path:
    return reports_dir / "stats_silver.csv"


@dataclass(frozen=True)
class TableCount:
    table: str
    sport: str
    rows: int


def _sport_expression(columns: set[str]) -> str:
    if "sport" in columns:
        return "sport"
    if "match_id" in columns:
        return "substring(match_id, 1, 2)"
    return "'all'"


def count_table(con: duckdb.DuckDBPyConnection, table: str, path: Path) -> list[TableCount]:
    """Rows of one silver table, split by sport when the table knows its sport."""
    source = path.as_posix()
    columns = {
        str(row[0])
        for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{source}')").fetchall()
    }
    expression = _sport_expression(columns)
    rows = con.execute(
        f"SELECT {expression} AS sport, count(*) FROM read_parquet('{source}') "
        "GROUP BY ALL ORDER BY 1"
    ).fetchall()
    return [
        TableCount(table, SPORT_BY_PREFIX.get(str(sport), str(sport)), int(n)) for sport, n in rows
    ]


def team_period_groups(con: duckdb.DuckDBPyConnection, path: Path) -> tuple[int, int, int]:
    """(groups, min teams in a group, max teams in a group) for dim_team_period."""
    row = con.execute(
        "SELECT count(*), min(n), max(n) FROM ("
        f"  SELECT count(*) AS n FROM read_parquet('{path.as_posix()}') GROUP BY match_id, period)"
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def silver_tables(data_dir: Path) -> list[tuple[str, Path]]:
    """Every silver table on disk, found by the layout convention and not by a list
    this file would have to keep in step with dbt's models."""
    root = silver_dir(data_dir)
    if not root.is_dir():
        return []
    return [
        (d.name, d / "data.parquet")
        for d in sorted(root.iterdir())
        if (d / "data.parquet").is_file()
    ]


def run_stats(data_dir: Path, reports_dir: Path) -> int:
    present = silver_tables(data_dir)
    if not present:
        print(f"stats: no silver table under {silver_dir(data_dir)}; run dbt build first")
        return 1

    con = duckdb.connect()
    counts: list[TableCount] = []
    for table, path in present:
        by_sport = count_table(con, table, path)
        counts.extend(by_sport)
        total = sum(c.rows for c in by_sport)
        split = ", ".join(f"{c.sport} {c.rows}" for c in by_sport)
        print(f"silver {table}: {total} rows ({split})")
        if table == "dim_team_period":
            groups, lo, hi = team_period_groups(con, path)
            print(
                f"silver {table}: {groups} (match, period) groups, "
                f"teams per group min={lo} max={hi}"
            )

    report = stats_report_path(reports_dir)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["table", "sport", "rows"])
        writer.writerows([[c.table, c.sport, c.rows] for c in counts])
    print(f"report: {report} ({len(counts)} rows)")
    return 0
