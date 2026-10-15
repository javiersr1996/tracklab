"""`tracklab fixtures`: cut one possession per sport out of bronze, for CI.

CI cannot download 2.3 GB on every push, so it builds silver from a slice of
bronze that is versioned with the code. The slice is a frame window per sport,
one team possession each, and every bronze table silver reads is cut to it with
one rule, so nothing in the slice is chosen by hand:

- a table with a match column keeps that match only;
- a table with a frame column keeps the rows that start inside the window
  (`frameIdx`, `frame`, `startFrame` or `frame_start`, the first one it has);
- `events_chance_players` has no frame and follows the chances it belongs to;
- a table with no match column (the aliases) is small and goes whole.

Season aggregates have no match column, so they go whole like the aliases. The
rows keep the exact bronze schema because they are copied with `SELECT *`, which is what
lets dbt build on the slice with the same sources it uses on the full bundle. DuckDB
writes every column as nullable, so a table whose bronze schema has NOT NULL columns is
rewritten with the schema of its source file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow.parquet as pq


@dataclass(frozen=True)
class Cut:
    sport: str
    native_match_id: int
    frame_lo: int
    frame_hi: int


# Two possessions measured in silver when the fixtures were cut (task 14): each
# ends in a shot and holds several passes, 12.8 s and 15.9 s long.
CUTS = (
    Cut("basketball", 114243, 3642, 3962),  # bb:possessions:possession-114243-1-2
    Cut("football", 1874553, 14055, 14214),  # fb:possession:1874553:51
)
FRAME_COLUMNS = ("frameIdx", "frame", "startFrame", "frame_start")
MATCH_COLUMNS = ("match_id", "native_match_id")


@dataclass(frozen=True)
class CutTable:
    path: Path
    rows: int


def _columns(con: duckdb.DuckDBPyConnection, glob: str) -> list[str]:
    return [
        str(r[0]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob}')").fetchall()
    ]


def _where(columns: list[str], cut: Cut, bronze: Path) -> str:
    clauses = []
    match = next((c for c in MATCH_COLUMNS if c in columns), None)
    if match is not None:
        clauses.append(f"{match} = {cut.native_match_id}")
    if "sport" in columns:
        clauses.append(f"sport = '{cut.sport}'")
    frame = next((c for c in FRAME_COLUMNS if c in columns), None)
    if frame is not None:
        clauses.append(f'"{frame}" BETWEEN {cut.frame_lo} AND {cut.frame_hi}')
    elif "chanceId" in columns:
        chances = (bronze / cut.sport / "events_chances" / "*.parquet").as_posix()
        clauses.append(
            f"chanceId IN (SELECT id FROM read_parquet('{chances}') "
            f"WHERE match_id = {cut.native_match_id} "
            f"AND startFrame BETWEEN {cut.frame_lo} AND {cut.frame_hi})"
        )
    return " AND ".join(clauses) or "true"


def _copy(con: duckdb.DuckDBPyConnection, glob: str, where: str, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    query = f"SELECT * FROM read_parquet('{glob}') WHERE {where}"
    con.execute(f"COPY ({query}) TO '{target.as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)")
    source = pq.read_schema(sorted(Path(glob).parent.glob(Path(glob).name))[0])
    if not pq.read_schema(target).equals(source, check_metadata=False):
        pq.write_table(pq.read_table(target).cast(source), target, compression="zstd")
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{target.as_posix()}')").fetchall()
    return int(rows[0][0])


def cut_fixtures(data_dir: Path, out_dir: Path, cuts: tuple[Cut, ...] = CUTS) -> list[CutTable]:
    """Write `out_dir/bronze/...` with the layout of `data_dir/bronze/...`, cut to `cuts`."""
    bronze = data_dir / "bronze"
    con = duckdb.connect()
    written: list[CutTable] = []
    for cut in cuts:
        for table in sorted(p for p in (bronze / cut.sport).iterdir() if p.is_dir()):
            glob = (table / "*.parquet").as_posix()
            columns = _columns(con, glob)
            per_match = (table / f"{cut.native_match_id}.parquet").is_file()
            name = f"{cut.native_match_id}.parquet" if per_match else "data.parquet"
            target = out_dir / "bronze" / cut.sport / table.name / name
            written.append(CutTable(target, _copy(con, glob, _where(columns, cut, bronze), target)))
    # The orientation table holds both sports in one file, so it is cut once for all.
    orientation = (bronze / "common" / "orientation" / "data.parquet").as_posix()
    matches = ", ".join(str(c.native_match_id) for c in cuts)
    target = out_dir / "bronze" / "common" / "orientation" / "data.parquet"
    written.append(
        CutTable(target, _copy(con, orientation, f"native_match_id IN ({matches})", target))
    )
    return written


def run_fixtures(data_dir: Path, out_dir: Path) -> int:
    written = cut_fixtures(data_dir, out_dir)
    total = 0
    for table in written:
        size = table.path.stat().st_size
        total += size
        print(f"{table.path.relative_to(out_dir).as_posix()}: {table.rows} rows, {size} bytes")
    print(f"{len(written)} tables, {total} bytes")
    return 0
