"""bronze football season aggregates (`aggregates_{physical,obr,passing}`).

The synthetic CSV includes `player_birthdate`, a column DuckDB sniffs as DATE: the
real bundle's 3 aggregate files all carry it, basketball's 3 never do (all
BOOLEAN/BIGINT/DOUBLE/VARCHAR), so this is the exact case that used to raise
`KeyError: 'DATE'` out of `formats.csvschema.pa_schema` before
`bronze.common._season_csv_schema` added the missing mapping. No hand-written
schema JSON: frozen with `formats.csvschema.freeze_csv_family`, the same tactic
`test_bronze_football_events.py` and the basketball events test use.

`build_aggregates` is exercised through the CLI by monkeypatching `SCHEMAS_DIR` in
the module namespace (a bare name looked up fresh at call time, unlike
`load_schema`'s own default argument), so no real 65/130/48-column schema files are
needed.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

import tracklab.bronze.football.aggregates as aggregates_module
from tracklab.bronze.common import bronze_season_path, build_season_csv_table
from tracklab.bronze.football.aggregates import aggregate_table
from tracklab.cli import main
from tracklab.formats.csvschema import freeze_csv_family
from tracklab.ingest.fetch import RECEIPT_NAME
from tracklab.ingest.manifest import FileEntry, Manifest, Source, save_manifest

SPORT = "football"
SOURCE_ID = "opendata-football"
COMMIT = "abc123" * 6 + "abcd"

HEADER = "player_id,player_birthdate,minutes"
ROWS: list[tuple[int, str, float | None]] = [
    (1, "1993-06-02", 812.5),
    (2, "1998-11-20", 640.0),
    (3, "2001-01-15", None),
]


def csv_text(rows: list[tuple[int, str, float | None]]) -> str:
    lines = [HEADER]
    for pid, bdate, minutes in rows:
        m = "" if minutes is None else str(minutes)
        lines.append(f"{pid},{bdate},{m}")
    return "\n".join(lines) + "\n"


def aggregate_path(family: str) -> str:
    return f"data/aggregates/aus1league_{family}aggregates_20242025.csv"


def write(path: Path, content: str) -> bytes:
    blob = content.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return blob


def entry_for(path: str, blob: bytes) -> FileEntry:
    return FileEntry(
        path=path,
        bytes=len(blob),
        sha256=hashlib.sha256(blob).hexdigest(),
        lfs=True,
        role="aggregate",
        match_id=None,
    )


# --- aggregate_table: raw filename -> table name --------------------------------------


@pytest.mark.parametrize(
    ("filename", "table"),
    [
        ("aus1league_physicalaggregates_20242025.csv", "aggregates_physical"),
        ("aus1league_obraggregates_20242025.csv", "aggregates_obr"),
        ("aus1league_passingaggregates_20242025.csv", "aggregates_passing"),
    ],
)
def test_aggregate_table_maps_known_families(filename: str, table: str) -> None:
    assert aggregate_table(Path(filename)) == table


def test_aggregate_table_rejects_unknown_file() -> None:
    with pytest.raises(ValueError, match="unrecognised football aggregate file"):
        aggregate_table(Path("aus1league_shootingaggregates_20242025.csv"))


# --- build_season_csv_table: the DATE column that used to break pa_schema ------------


def test_build_season_csv_table_handles_date_column(tmp_path: Path) -> None:
    con = duckdb.connect()
    clone = tmp_path / "clone"
    path = clone / aggregate_path("physical")
    write(path, csv_text(ROWS))
    frozen = freeze_csv_family("aggregates_physical", [path], clone, con)
    types = {c.name: c.type for c in frozen.columns}
    assert types["player_birthdate"] == "DATE"

    entry = entry_for(aggregate_path("physical"), path.read_bytes())
    data_dir = tmp_path / "data"
    s = build_season_csv_table(
        SPORT, "aggregates_physical", frozen, entry, clone, COMMIT, data_dir, con
    )
    assert (s.table, s.rows) == ("aggregates_physical", 3)

    out_path = bronze_season_path(data_dir, SPORT, "aggregates_physical")
    table = pq.read_table(out_path)
    assert "match_id" not in table.column_names, "season grain: no match dimension"
    assert table.column("player_birthdate").to_pylist() == [
        datetime.date(1993, 6, 2),
        datetime.date(1998, 11, 20),
        datetime.date(2001, 1, 15),
    ]
    assert table.column("minutes").to_pylist() == [812.5, 640.0, None]
    assert table.column("source_row").to_pylist() == [0, 1, 2]
    assert set(table.column("sport").to_pylist()) == {SPORT}
    assert set(table.column("source_file").to_pylist()) == {aggregate_path("physical")}


# --- build_aggregates: the 3 tables, through the CLI ----------------------------------


def frozen_source(files: list[FileEntry]) -> Source:
    repo = "SkillCorner/opendata"
    return Source(
        source_id=SOURCE_ID,
        sport=SPORT,
        kind="github",
        repo=repo,
        ref="master",
        commit=COMMIT,
        license="MIT",
        raw_url=f"https://raw.githubusercontent.com/{repo}/{{commit}}/",
        lfs_url=f"https://media.githubusercontent.com/media/{repo}/{{commit}}/",
        files=files,
    )


def write_receipt(data_dir: Path, source_path: Path) -> None:
    receipt_dir = data_dir / "raw" / SOURCE_ID
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "source_id": SOURCE_ID,
        "commit": COMMIT,
        "verified": 3,
        "downloaded": 0,
        "failed": [],
        "finished_at": "2026-09-22T10:00:00+00:00",
        "source_path": str(source_path),
    }
    (receipt_dir / RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    clone = tmp_path / "clone"
    data_dir = tmp_path / "data"
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    con = duckdb.connect()
    entries = []
    for family in ("physical", "obr", "passing"):
        path = clone / aggregate_path(family)
        blob = write(path, csv_text(ROWS))
        entries.append(entry_for(aggregate_path(family), blob))
        table = f"aggregates_{family}"
        frozen = freeze_csv_family(table, [path], clone, con)
        (schemas_dir / f"{table}.schema.json").write_text(frozen.to_json(), encoding="utf-8")
    manifest_path = tmp_path / "sources.json"
    save_manifest(Manifest(schema_version=1, sources=[frozen_source(entries)]), manifest_path)
    write_receipt(data_dir, clone)
    # SCHEMAS_DIR is a bare name looked up fresh from the module namespace when
    # build_aggregates runs, so patching it here reaches the CLI path without a
    # real 65/130/48-column schemas directory (mirrors load_frozen_tables in the
    # events test).
    monkeypatch.setattr(aggregates_module, "SCHEMAS_DIR", schemas_dir)
    return manifest_path, data_dir


def test_cli_builds_all_three_aggregates(
    bundle: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path, data_dir = bundle
    rc = main(
        [
            "bronze",
            "football",
            "--tables",
            "aggregates",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("bronze football aggregates: ")
    assert out[1].split() == ["table", "rows", "seconds", "MB"]
    body = {line.split()[0]: line.split()[1] for line in out[2:-1]}
    assert body == {"aggregates_obr": "3", "aggregates_passing": "3", "aggregates_physical": "3"}
    assert out[-1].startswith("total seconds=")

    for family in ("physical", "obr", "passing"):
        path = bronze_season_path(data_dir, SPORT, f"aggregates_{family}")
        assert path.is_file()
        assert pq.read_table(path).num_rows == 3
