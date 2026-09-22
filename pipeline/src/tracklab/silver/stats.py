"""`tracklab stats`: count what silver actually holds, print it, write it down.

Every figure the web or a document quotes has to come from an artefact rather
than from the code that built it, so this command reads the Parquet that dbt
wrote and writes `reports/stats_silver.csv`. It counts what is on disk and never
rebuilds anything: if a model was not built, its row is simply absent, and a
count that surprises someone is a fact about the data and not about this file.

A table partitioned per match is also counted per match, because that is the
grain someone loading one match cares about, and because task 11's acceptance
compares those counts against bronze one match at a time. Which tables those are
is read off the layout (a directory with partitions inside) rather than from a
list that would have to be kept in step with dbt's models.

Tasks 10 and 11 cover the dimensions and `frames`. `stats.json` for the web is
task 17's, and it reads these same counts rather than computing its own.
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
    """The single file of an unpartitioned table. `table_glob` reads either shape."""
    return silver_dir(data_dir) / table / "data.parquet"


def table_glob(data_dir: Path, table: str) -> str:
    """One read for both layouts: `<table>/data.parquet` and the partition tree of
    `frames`. DuckDB's `**` matches zero directories as well as many."""
    return (silver_dir(data_dir) / table / "**" / "*.parquet").as_posix()


def stats_report_path(reports_dir: Path) -> Path:
    return reports_dir / "stats_silver.csv"


@dataclass(frozen=True)
class TableCount:
    table: str
    sport: str
    match_id: str
    rows: int


def _sport_expression(columns: set[str]) -> str:
    if "sport" in columns:
        return "sport"
    if "match_id" in columns:
        return "substring(match_id, 1, 2)"
    return "'all'"


def _named(sport: object) -> str:
    return SPORT_BY_PREFIX.get(str(sport), str(sport))


def count_table(
    con: duckdb.DuckDBPyConnection, table: str, source: str, per_match: bool
) -> list[TableCount]:
    """Rows of one silver table, split by sport, and by match when it is partitioned
    that way. A table that knows neither is counted whole."""
    columns = {
        str(row[0])
        for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{source}')").fetchall()
    }
    sport = _sport_expression(columns)
    match = "match_id" if per_match and "match_id" in columns else "''"
    rows = con.execute(
        f"SELECT {sport} AS sport, {match} AS match_id, count(*) "
        f"FROM read_parquet('{source}') GROUP BY ALL ORDER BY 1, 2"
    ).fetchall()
    return [TableCount(table, _named(s), str(m), int(n)) for s, m, n in rows]


def team_period_groups(con: duckdb.DuckDBPyConnection, source: str) -> tuple[int, int, int]:
    """(groups, min teams in a group, max teams in a group) for dim_team_period."""
    row = con.execute(
        "SELECT count(*), min(n), max(n) FROM ("
        f"  SELECT count(*) AS n FROM read_parquet('{source}') GROUP BY match_id, period)"
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def silver_tables(data_dir: Path) -> list[tuple[str, bool]]:
    """Every silver table on disk with whether it is partitioned, found by the layout
    convention and not by a list this file would have to keep in step with dbt."""
    root = silver_dir(data_dir)
    if not root.is_dir():
        return []
    tables = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        partitioned = any(child.is_dir() for child in directory.iterdir())
        if partitioned or (directory / "data.parquet").is_file():
            tables.append((directory.name, partitioned))
    return tables


def run_stats(data_dir: Path, reports_dir: Path) -> int:
    present = silver_tables(data_dir)
    if not present:
        print(f"stats: no silver table under {silver_dir(data_dir)}; run dbt build first")
        return 1

    con = duckdb.connect()
    counts: list[TableCount] = []
    for table, partitioned in present:
        source = table_glob(data_dir, table)
        per_match = count_table(con, table, source, per_match=partitioned)
        counts.extend(per_match)

        by_sport: dict[str, int] = {}
        for count in per_match:
            by_sport[count.sport] = by_sport.get(count.sport, 0) + count.rows
        total = sum(by_sport.values())
        split = ", ".join(f"{sport} {n}" for sport, n in sorted(by_sport.items()))
        print(f"silver {table}: {total} rows ({split})")
        if partitioned:
            for count in per_match:
                print(f"silver {table} {count.match_id}: {count.rows} rows")
        if table == "dim_team_period":
            groups, lo, hi = team_period_groups(con, source)
            print(
                f"silver {table}: {groups} (match, period) groups, "
                f"teams per group min={lo} max={hi}"
            )

    report = stats_report_path(reports_dir)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["table", "sport", "match_id", "rows"])
        writer.writerows([[c.table, c.sport, c.match_id, c.rows] for c in counts])
    print(f"report: {report} ({len(counts)} rows)")
    return 0
