"""Contract of the bronze basketball tracking against the built Parquet and the raw gz.

Skipped when the bronze tables are not built (CI on fixtures). Everything here reads
the artefact on disk with DuckDB or pyarrow, never what the builder computed, and
prints its evidence per match, never an aggregate. The independent counter of the
last test walks the gz with gzip and json alone: no pyarrow, no tracklab import, so
it shares no line with the writer it checks.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from tracklab.bronze.basketball.tracking import TABLES
from tracklab.bronze.common import raw_root_for
from tracklab.ingest.manifest import load_manifest

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze" / "basketball"
SOURCE_ID = "opendata-basketball"
COUNTED_MATCH = 114243
PLAYERS_PER_SIDE = 5

pytestmark = pytest.mark.skipif(
    not (BRONZE / "tracking_frames").is_dir(),
    reason="run `tracklab bronze basketball --tables tracking` first",
)


@pytest.fixture(scope="module")
def match_ids() -> list[int]:
    source = load_manifest(PIPELINE / "manifest" / "sources.json").source(SOURCE_ID)
    ids = sorted(f.match_id for f in source.files if f.role == "tracking" and f.match_id)
    assert len(ids) == 10, f"expected 10 tracking files in the manifest, found {len(ids)}"
    return ids


def parquet(table: str, match_id: int) -> str:
    path = BRONZE / table / f"{match_id}.parquet"
    assert path.is_file(), f"{path} missing"
    return path.as_posix()


def test_every_file_has_the_declared_schema(match_ids: list[int]) -> None:
    for table, declared in TABLES.items():
        for match_id in match_ids:
            written = pq.read_schema(parquet(table, match_id))
            print(f"{table} {match_id} columns={len(written)}")
            assert written.equals(declared, check_metadata=False), f"{table} {match_id}: {written}"


def test_wall_clock_is_frame_idx_times_40_in_every_match(match_ids: list[int]) -> None:
    con = duckdb.connect()
    print(f"\n{'match_id':>8} {'frames':>8} {'rule_ok':>8} {'pct':>7}")
    failures = []
    for match_id in match_ids:
        n, ok = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE wallClock = frameIdx * 40) "
            "FROM read_parquet(?)",
            [parquet("tracking_frames", match_id)],
        ).fetchone()
        pct = 100.0 * ok / n
        print(f"{match_id:>8} {n:>8} {ok:>8} {pct:>7.2f}")
        if ok != n:
            failures.append(match_id)
    assert failures == []


def test_frames_are_full_or_empty_and_gaps_stay_gaps(match_ids: list[int]) -> None:
    """Per match: full (5+5+ball), empty (0+0, no ball), partial (anything else, must be
    0) and the frames the file never delivered (max frameIdx + 1 minus lines), which is
    reported as a number, never filled."""
    con = duckdb.connect()
    print(f"\n{'match_id':>8} {'frames':>8} {'full':>8} {'empty':>8} {'partial':>8} {'absent':>8}")
    partials = []
    for match_id in match_ids:
        n, full, empty, absent = con.execute(
            "SELECT count(*), "
            "count(*) FILTER (WHERE n_home = ? AND n_away = ? AND has_ball), "
            "count(*) FILTER (WHERE n_home = 0 AND n_away = 0 AND NOT has_ball), "
            "max(frameIdx) + 1 - count(*) "
            "FROM read_parquet(?)",
            [PLAYERS_PER_SIDE, PLAYERS_PER_SIDE, parquet("tracking_frames", match_id)],
        ).fetchone()
        partial = n - full - empty
        print(f"{match_id:>8} {n:>8} {full:>8} {empty:>8} {partial:>8} {absent:>8}")
        if partial:
            partials.append(match_id)
    assert partials == []


def test_independent_count_of_lines_and_objects(match_ids: list[int]) -> None:
    """gzip + json walk of the raw file of 114243, no pyarrow and no tracklab code:
    lines must equal the rows of tracking_frames, and the sum of
    len(homePlayers) + len(awayPlayers) + (1 if ball) the rows of tracking_objects."""
    assert COUNTED_MATCH in match_ids
    raw_root = raw_root_for(DATA, SOURCE_ID)
    gz = (
        raw_root
        / "data"
        / "matches"
        / str(COUNTED_MATCH)
        / f"{COUNTED_MATCH}_tracking_data.jsonl.gz"
    )

    lines = 0
    objects = 0
    with gzip.open(gz, "rb") as fh:
        for line in fh:
            d = json.loads(line)
            lines += 1
            objects += len(d["homePlayers"]) + len(d["awayPlayers"]) + (1 if d["ball"] else 0)

    con = duckdb.connect()
    (frame_rows,) = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [parquet("tracking_frames", COUNTED_MATCH)]
    ).fetchone()
    (object_rows,) = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [parquet("tracking_objects", COUNTED_MATCH)]
    ).fetchone()
    print(f"\n{COUNTED_MATCH}: gz lines={lines} tracking_frames rows={frame_rows}")
    print(f"{COUNTED_MATCH}: gz objects={objects} tracking_objects rows={object_rows}")
    assert frame_rows == lines
    assert object_rows == objects
