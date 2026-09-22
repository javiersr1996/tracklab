"""Contract of the bronze basketball events against the built Parquet and the raw JSON.

Skipped when the bronze tables are not built (CI on fixtures). Everything here reads
the artefact on disk with DuckDB or pyarrow, never what the builder computed in
memory, and prints its evidence per family or per match, never an aggregate. The row
counter of 114243 walks the raw `dynamic_events.json` with `json.load` alone: no
pyarrow, no `tracklab` import, so it shares no line with the writer it checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from tracklab.bronze.common import raw_root_for
from tracklab.formats.basketball import FAMILY_ORDER, load_family, pa_schema
from tracklab.ingest.manifest import load_manifest

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze" / "basketball"
SCHEMAS = PIPELINE / "src" / "tracklab" / "bronze" / "schemas" / "basketball"
SOURCE_ID = "opendata-basketball"
COUNTED_MATCH = 114243

# The 20 counts task 6's brief pins for match 114243 (measured directly on the raw
# JSON by the planner before this module was built).
EXPECTED_114243 = {
    "chances": 216,
    "possessions": 157,
    "shots": 159,
    "rebounds": 95,
    "turnovers": 25,
    "free_throws": 36,
    "fouls": 40,
    "timeouts": 5,
    "passes": 525,
    "touches": 728,
    "dribbles": 1234,
    "picks": 135,
    "isolations": 11,
    "handoffs": 56,
    "drives": 58,
    "posts": 15,
    "off_ball_screens": 136,
    "closeouts": 58,
    "chance_players": 2160,
    "matchups": 1497,
}

pytestmark = pytest.mark.skipif(
    not (BRONZE / "events_chances").is_dir(),
    reason="run `tracklab bronze basketball --tables events` first",
)


@pytest.fixture(scope="module")
def match_ids() -> list[int]:
    source = load_manifest(PIPELINE / "manifest" / "sources.json").source(SOURCE_ID)
    ids = sorted(f.match_id for f in source.files if f.role == "events" and f.match_id)
    assert len(ids) == 10, f"expected 10 events files in the manifest, found {len(ids)}"
    return ids


def parquet(family: str, match_id: int) -> Path:
    path = BRONZE / f"events_{family}" / f"{match_id}.parquet"
    assert path.is_file(), f"{path} missing"
    return path


def test_row_counts_of_114243_match_the_raw_json_independently(match_ids: list[int]) -> None:
    """`json.load` on the raw file, no pyarrow, no tracklab.bronze import."""
    assert COUNTED_MATCH in match_ids
    raw_root = raw_root_for(DATA, SOURCE_ID)
    raw_path = (
        raw_root / "data" / "matches" / str(COUNTED_MATCH) / f"{COUNTED_MATCH}_dynamic_events.json"
    )
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    assert set(data.keys()) == set(FAMILY_ORDER)

    print(f"\n{'family':>18} {'raw_json':>9} {'parquet':>9}")
    mismatches = []
    for family in FAMILY_ORDER:
        expected = len(data[family])
        assert expected == EXPECTED_114243[family], (
            f"{family}: brief pins {EXPECTED_114243[family]}"
        )
        table = pq.read_table(parquet(family, COUNTED_MATCH))
        got = table.num_rows
        print(f"{family:>18} {expected:>9} {got:>9}")
        if got != expected:
            mismatches.append(family)
    assert mismatches == []


def test_touch_wall_clock_is_bigint_in_the_parquet(match_ids: list[int]) -> None:
    for match_id in match_ids:
        schema = pq.read_schema(parquet("closeouts", match_id))
        field = schema.field("touchWallClock")
        assert str(field.type) == "int64", f"{match_id}: touchWallClock is {field.type}"


def test_every_table_has_the_schema_frozen_at_freeze_time(match_ids: list[int]) -> None:
    """The 20 families x 10 matches = 200 per-match tables, schema derived from the
    frozen `.schema.json` via the same `pa_schema` the builder uses."""
    checked = 0
    mismatches = []
    for family in FAMILY_ORDER:
        frozen = load_family(SCHEMAS / f"events_{family}.schema.json")
        declared = pa_schema(frozen)
        for match_id in match_ids:
            written = pq.read_schema(parquet(family, match_id))
            checked += 1
            if not written.equals(declared, check_metadata=False):
                mismatches.append((family, match_id))
    print(f"\nchecked {checked} tables ({len(FAMILY_ORDER)} families x {len(match_ids)} matches)")
    assert mismatches == [], mismatches
