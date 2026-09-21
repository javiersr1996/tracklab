"""Contract of the frozen football schemas against the raw bundle on disk.

Skipped when the bundle is not ingested (CI on fixtures). With the bundle present it
checks, per match, that every dynamic_events.csv and phases_of_play.csv header is
identical to the frozen one, that the frozen types still impose on every file, and
that the report has exactly one row per match. Each check prints its evidence.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

import tracklab
from tracklab.formats.csvschema import header_sha256, impose, load_schema
from tracklab.formats.football import MatchBundle, discover

PIPELINE = Path(__file__).resolve().parents[2]
RAW = PIPELINE / "data" / "raw" / "opendata-football"
REPORT = PIPELINE / "reports" / "football_format.csv"
SCHEMAS = Path(tracklab.__file__).resolve().parent / "bronze" / "schemas" / "football"

pytestmark = pytest.mark.skipif(not RAW.is_dir(), reason="football bundle not ingested")


@pytest.fixture(scope="module")
def bundles() -> list[MatchBundle]:
    found = discover(RAW)
    assert len(found) == 20, f"expected 20 matches, found {len(found)}"
    return found


@pytest.mark.parametrize(
    ("table", "attr", "n_columns"),
    [("dynamic_events", "events", 322), ("phases_of_play", "phases", 44)],
)
def test_headers_identical_and_frozen(
    bundles: list[MatchBundle], table: str, attr: str, n_columns: int
) -> None:
    schema = load_schema(SCHEMAS / f"{table}.schema.json")
    assert len(schema.columns) == n_columns
    con = duckdb.connect()
    for bundle in bundles:
        path: Path = getattr(bundle, attr)
        digest = header_sha256(path)
        rows = impose(schema, path, con)
        print(f"{table} {bundle.match_id} header={digest[:8]} rows={rows}")
        assert digest == schema.header_sha256, f"{path.name} header differs from frozen {table}"
        assert rows > 0


def test_report_has_one_row_per_match(bundles: list[MatchBundle]) -> None:
    assert REPORT.is_file(), "run `tracklab freeze-schema football` first"
    with REPORT.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [int(r["match_id"]) for r in rows]
    print(f"report rows={len(rows)} columns={len(rows[0])} match_ids={ids}")
    assert ids == [b.match_id for b in bundles]
