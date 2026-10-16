"""Contract of the bronze football body pose against the built Parquet, the raw zips and the README.

Skipped when the bronze tables are not built (CI on fixtures): `tracklab bronze football --tables
bodypose` builds them. Everything here reads the artefact on disk with DuckDB and prints its
evidence per match, never an aggregate. The independent counter walks the zip member with
`zipfile` and `json.loads` alone, no pyarrow and none of the builder's parsing code. The README
numbers are parsed from the versioned copy of the HuggingFace README, not typed here.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from tracklab.bronze.football.bodypose import TABLES
from tracklab.pose.coverage import COVERAGE_NAME, match_ids, run_pose_coverage

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze" / "football"
README = PIPELINE / "tests" / "fixtures" / "bodypose" / "README.hf.md"
README_MATCH = 1925299
N_JOINTS = 29

pytestmark = pytest.mark.skipif(
    not (BRONZE / "bodypose_frames").is_dir(),
    reason="run `tracklab bronze football --tables bodypose` first",
)


@pytest.fixture(scope="module")
def ids() -> list[int]:
    found = match_ids(PIPELINE / "manifest" / "sources.json")
    assert len(found) == 2, f"expected 2 body pose zips in the manifest, found {found}"
    return found


def parquet(table: str, match_id: int) -> str:
    path = BRONZE / table / f"{match_id}.parquet"
    assert path.is_file(), f"{path} missing"
    return path.as_posix()


def one(sql: str, *params: str) -> tuple[int, ...]:
    row = duckdb.connect().execute(sql, list(params)).fetchone()
    assert row is not None
    return tuple(row)


def readme_numbers() -> dict[str, int]:
    """The coverage table of the README, by row label: every integer in the row."""
    out = {}
    for label, value in re.findall(
        r"^\| ([^|]+?) \| ([^|]+?) \|$", README.read_text("utf-8"), re.M
    ):
        if label.startswith(("Frames in file", "Player-frames", "Total joint")):
            out[label] = int(re.search(r"[\d,]+", value).group().replace(",", ""))  # type: ignore[union-attr]
    return out


def test_every_file_has_the_declared_schema(ids: list[int]) -> None:
    for table, declared in TABLES.items():
        for match_id in ids:
            written = pq.read_schema(parquet(table, match_id))
            print(f"{table} {match_id} columns={len(written)}")
            assert written.equals(declared, check_metadata=False), f"{table} {match_id}"


def test_the_readme_numbers_for_1925299_are_reproduced_from_the_bronze() -> None:
    expected = readme_numbers()
    print(expected)
    frames, with_any, player_frames, with_pose = one(
        "select count(*), count(*) filter (where n_with_pose > 0), sum(n_players), "
        "sum(n_with_pose) from read_parquet(?)",
        parquet("bodypose_frames", README_MATCH),
    )
    (rows, observations) = one(
        "select count(*), sum(len(mae)) from read_parquet(?)",
        parquet("bodypose_players", README_MATCH),
    )
    print(f"frames={frames} with_pose={with_any} player_frames={player_frames} rows={rows}")
    assert frames == expected["Frames in file"] == 153_252
    assert player_frames == expected["Player-frames total"] == 4_902_560
    assert rows == with_pose == expected["Player-frames with pose"] == 1_540_715
    assert observations == expected["Total joint observations"] == 44_680_735
    assert with_any == 106_757  # "Frames with at least one pose": the row of the README has 69.7%
    assert round(rows / with_any, 1) == 14.4


def test_the_period_is_the_field_not_the_clock() -> None:
    """Frame 124487 is in period 2 with the match clock at 01:17; period 1 runs past 45:00."""
    path = parquet("bodypose_frames", README_MATCH)
    assert one("select period from read_parquet(?) where frame = 124487", path) == (2,)
    (clock,) = duckdb.connect().execute(
        "select timestamp from read_parquet(?) where frame = 124487", [path]
    ).fetchone() or ("",)
    assert clock == "01:17:34.48"
    (late_in_first,) = one(
        "select count(*) from read_parquet(?) where period = 1 and timestamp > '00:45:00.00'", path
    )
    print(f"period 1 frames with the clock past 45:00: {late_in_first}")
    assert late_in_first > 0


def test_frame_equals_source_row_and_is_contiguous(ids: list[int]) -> None:
    for match_id in ids:
        n, lo, hi, differing = one(
            "select count(*), min(frame), max(frame), count(*) filter (where frame != source_row) "
            "from read_parquet(?)",
            parquet("bodypose_frames", match_id),
        )
        print(f"{match_id}: frames={n} first={lo} last={hi} frame!=source_row={differing}")
        assert (lo, n, differing) == (0, hi + 1, 0)


def test_the_bronze_equals_an_independent_count_of_the_zip(ids: list[int]) -> None:
    """json.loads over the zip member, no code of the builder: frames, frame-players, poses."""
    for match_id in ids:
        frames = listed = posed = 0
        with zipfile.ZipFile(
            DATA / "raw" / "opendata-bodypose" / "raw" / f"{match_id}.jsonl.zip"
        ) as z:
            member = f"{match_id}.jsonl"
            with z.open(member) as binary:
                for text in io.TextIOWrapper(binary, encoding="utf-8"):
                    record = json.loads(text)
                    frames += 1
                    listed += len(record["player_data"])
                    posed += sum(p["joints"] is not None for p in record["player_data"])
        got = one(
            "select count(*), sum(n_players), sum(n_with_pose) from read_parquet(?)",
            parquet("bodypose_frames", match_id),
        )
        rows = one("select count(*) from read_parquet(?)", parquet("bodypose_players", match_id))
        print(f"{match_id}: zip {frames}/{listed}/{posed}; bronze {got} rows={rows}")
        assert got == (frames, listed, posed)
        assert rows == (posed,)


def test_the_versioned_coverage_is_what_the_bronze_gives(
    ids: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert (PIPELINE / "reports" / COVERAGE_NAME).is_file()
    assert run_pose_coverage(DATA, PIPELINE / "reports", check=True) == 0
    out = capsys.readouterr().out
    print(out)
    assert f"FULL {len(ids)}/{len(ids)}" in out
