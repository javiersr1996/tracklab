"""bronze basketball events on synthetic families and frozen schemas. No real data.

`FAMILY_ORDER` is monkeypatched, inside `tracklab.bronze.basketball.events`, to a
2-family universe (`shots`, `closeouts`) so the test does not need to fabricate all 20
real families: `build_events_match` reads `FAMILY_ORDER` from the module namespace at
call time, so the patch reaches every function that loops over it. The frozen schemas
themselves come from `freeze_family` (never hand-written JSON), so a change to the
freezer's output shape cannot silently drift from what the builder expects.

Covers: the POINT2D split into `_x`/`_y`, the `touchWallClock` cast landing as BIGINT
in the written Parquet, lineage columns and `source_row`, the `gameId` integrity
assert, a family set the frozen schemas do not expect failing the run, a cast the
builder does not know how to perform failing instead of being silently skipped, and a
row whose key set drifted from the frozen one (a key added or dropped by the provider)
failing with the file, the family, the row and the keys.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import tracklab.bronze.basketball.events as events_module
from tracklab.bronze.basketball.events import build_events_match, family_batch
from tracklab.bronze.common import bronze_path
from tracklab.formats.basketball import FrozenFamily, freeze_family, pa_schema
from tracklab.ingest.manifest import FileEntry

SPORT = "basketball"
SOURCE_ID = "opendata-basketball"
COMMIT = "deadbeef" * 5
MATCH_A = 900001


def events_path(match_id: int) -> str:
    return f"data/matches/{match_id}/{match_id}_dynamic_events.json"


SHOTS_ROWS: list[dict[str, Any]] = [
    {"id": "shot-1", "gameId": MATCH_A, "location": [1.0, 2.0], "made": True},
    {"id": "shot-2", "gameId": MATCH_A, "location": None, "made": False},
]
CLOSEOUTS_ROWS: list[dict[str, Any]] = [
    {"id": "co-1", "gameId": MATCH_A, "touchWallClock": "53080"},
    {"id": "co-2", "gameId": MATCH_A, "touchWallClock": None},
]


@pytest.fixture
def families(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[dict[str, FrozenFamily], dict[str, pa.Schema]]]:
    monkeypatch.setattr(events_module, "FAMILY_ORDER", ("shots", "closeouts"))
    rel = events_path(MATCH_A)
    frozen = {
        "shots": freeze_family("shots", [(rel, SHOTS_ROWS)], SPORT, SOURCE_ID, COMMIT),
        "closeouts": freeze_family("closeouts", [(rel, CLOSEOUTS_ROWS)], SPORT, SOURCE_ID, COMMIT),
    }
    schemas = {name: pa_schema(f) for name, f in frozen.items()}
    yield frozen, schemas


def entry_for(match_id: int) -> FileEntry:
    return FileEntry(
        path=events_path(match_id),
        bytes=0,
        sha256="00" * 32,
        lfs=False,
        role="events",
        match_id=match_id,
    )


def write_events_file(raw_root: Path, match_id: int, data: dict[str, Any]) -> None:
    path = raw_root / events_path(match_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


FamilyFixture = tuple[dict[str, FrozenFamily], dict[str, pa.Schema]]


def test_build_events_match_writes_point2d_cast_and_lineage(
    tmp_path: Path, families: FamilyFixture
) -> None:
    frozen, schemas = families
    raw_root, data_dir = tmp_path / "clone", tmp_path / "data"
    write_events_file(raw_root, MATCH_A, {"shots": SHOTS_ROWS, "closeouts": CLOSEOUTS_ROWS})

    stats = build_events_match(entry_for(MATCH_A), raw_root, data_dir, COMMIT, frozen, schemas)
    assert {s.family: s.rows for s in stats} == {"shots": 2, "closeouts": 2}

    shots_rows = rows(bronze_path(data_dir, SPORT, "events_shots", MATCH_A))
    assert [r["location_x"] for r in shots_rows] == [1.0, None]
    assert [r["location_y"] for r in shots_rows] == [2.0, None]
    assert [r["made"] for r in shots_rows] == [True, False]
    assert [r["sport"] for r in shots_rows] == [SPORT] * 2
    assert [r["match_id"] for r in shots_rows] == [MATCH_A] * 2
    assert [r["source_file"] for r in shots_rows] == [events_path(MATCH_A)] * 2
    assert [r["source_row"] for r in shots_rows] == [0, 1]

    closeouts_path = bronze_path(data_dir, SPORT, "events_closeouts", MATCH_A)
    assert [r["touchWallClock"] for r in rows(closeouts_path)] == [53080, None]
    assert pq.read_schema(closeouts_path).field("touchWallClock").type == pa.int64()


def test_game_id_mismatch_fails_naming_the_row(tmp_path: Path, families: FamilyFixture) -> None:
    frozen, schemas = families
    raw_root, data_dir = tmp_path / "clone", tmp_path / "data"
    bad_shots = [{"id": "shot-1", "gameId": 999999, "location": [1.0, 2.0], "made": True}]
    write_events_file(raw_root, MATCH_A, {"shots": bad_shots, "closeouts": CLOSEOUTS_ROWS})

    with pytest.raises(ValueError, match=r"gameId 999999 != 900001"):
        build_events_match(entry_for(MATCH_A), raw_root, data_dir, COMMIT, frozen, schemas)


def test_unexpected_family_set_in_the_file_fails(tmp_path: Path, families: FamilyFixture) -> None:
    frozen, schemas = families
    raw_root, data_dir = tmp_path / "clone", tmp_path / "data"
    write_events_file(raw_root, MATCH_A, {"shots": SHOTS_ROWS})  # missing 'closeouts'

    with pytest.raises(ValueError, match=r"families missing \['closeouts'\]"):
        build_events_match(entry_for(MATCH_A), raw_root, data_dir, COMMIT, frozen, schemas)


def test_family_batch_rejects_a_cast_it_does_not_know_how_to_perform(
    families: FamilyFixture,
) -> None:
    frozen, _ = families
    # Simulate a frozen schema declaring a cast events.py has no logic for.
    bogus = dataclasses.replace(
        frozen["shots"],
        columns=tuple(
            dataclasses.replace(c, source_type="DOUBLE", type="BIGINT") if c.name == "made" else c
            for c in frozen["shots"].columns
        ),
    )
    with pytest.raises(ValueError, match="no declared cast from DOUBLE to BIGINT"):
        family_batch(bogus, pa_schema(bogus), SHOTS_ROWS, MATCH_A, events_path(MATCH_A))


def test_load_frozen_families_reads_a_directory(tmp_path: Path, families: FamilyFixture) -> None:
    frozen, _ = families
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    for name, ff in frozen.items():
        (schemas_dir / f"events_{name}.schema.json").write_text(ff.to_json(), encoding="utf-8")

    loaded = events_module.load_frozen_families(schemas_dir)
    assert set(loaded) == {"shots", "closeouts"}
    assert loaded["shots"] == frozen["shots"]


def test_a_key_the_provider_added_fails_naming_it(families: FamilyFixture) -> None:
    """A key that appears after the freeze must stop the run, not be dropped in
    silence: a provider that publishes a new column is exactly what freezing and
    imposing exists to catch, and a silent drop makes the column vanish with the
    build still green."""
    frozen, schemas = families
    grown = [{**SHOTS_ROWS[0], "newKeyTheProviderAdded": 9}]

    with pytest.raises(
        ValueError, match=r"shots\[0\]: missing \[\], extra \['newKeyTheProviderAdded'\]"
    ):
        family_batch(frozen["shots"], schemas["shots"], grown, MATCH_A, events_path(MATCH_A))


def test_a_key_the_provider_dropped_fails_naming_it(families: FamilyFixture) -> None:
    frozen, schemas = families
    shrunk = [{k: v for k, v in SHOTS_ROWS[0].items() if k != "made"}]

    with pytest.raises(ValueError, match=r"shots\[0\]: missing \['made'\], extra \[\]"):
        family_batch(frozen["shots"], schemas["shots"], shrunk, MATCH_A, events_path(MATCH_A))


def test_a_value_that_does_not_cast_names_the_file_row_and_key(families: FamilyFixture) -> None:
    frozen, schemas = families
    bad = [{"id": "co-1", "gameId": MATCH_A, "touchWallClock": "not a number"}]

    with pytest.raises(
        ValueError, match=r"closeouts\[0\]\.touchWallClock: invalid literal for int"
    ):
        family_batch(frozen["closeouts"], schemas["closeouts"], bad, MATCH_A, events_path(MATCH_A))
