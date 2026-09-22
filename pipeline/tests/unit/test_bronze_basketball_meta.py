"""bronze basketball meta (games, game_players, matches, player_id_aliases) on a
synthetic bundle. No real data, no network.

One match's `game_data.json` (2 home players, 1 away player, so roster flattening and
`side`/`teamId` are visible), a `matches.json` of 2 matches with nested `home_team`/
`away_team` that bronze must flatten, and an `player_id_aliases.csv` of 2 rows. Run
through the CLI exactly as a user would (`tracklab bronze basketball --tables meta`),
then every table is read back from Parquet and checked against the planted values,
including the two path conventions: per-match files for `games`/`game_players`, one
season file for `matches` (still carrying its own `match_id` per row) and for
`player_id_aliases` (no `match_id` at all).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from tracklab.bronze.basketball.meta import build_games_and_players
from tracklab.bronze.common import bronze_path, bronze_season_path
from tracklab.cli import main
from tracklab.ingest.fetch import RECEIPT_NAME
from tracklab.ingest.manifest import FileEntry, Manifest, Source, save_manifest

SOURCE_ID = "opendata-basketball"
COMMIT = "4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66"
MATCH_A, MATCH_B = 900001, 900002
HOME_TEAM_ID, AWAY_TEAM_ID = 1330, 1319


def game_data_path(match_id: int) -> str:
    return f"data/matches/{match_id}/{match_id}_game_data.json"


def game_data(match_id: int) -> dict[str, Any]:
    return {
        "gameId": match_id,
        "date": "2025-10-11T19:00:00Z",
        "competitionEditionId": 211,
        "competitionId": 8,
        "competitionName": "Liga ACB",
        "seasonId": 51,
        "seasonName": "2025-2026",
        "dynamicEventsLastProcessingDate": "2026-07-17T12:38:51Z",
        "trackingLastProcessingDate": "2026-07-17T12:39:01Z",
        "physicalLastProcessingDate": "2026-07-17T12:38:51Z",
        "homeTeam": {
            "teamId": HOME_TEAM_ID,
            "teamName": "Home FC",
            "players": [
                {"playerId": 1, "firstName": "A", "lastName": "One", "jersey": "4"},
                {"playerId": 2, "firstName": "B", "lastName": "Two", "jersey": "5"},
            ],
        },
        "awayTeam": {
            "teamId": AWAY_TEAM_ID,
            "teamName": "Away FC",
            "players": [{"playerId": 3, "firstName": "C", "lastName": "Three", "jersey": "6"}],
        },
    }


MATCHES_JSON = [
    {
        "id": MATCH_A,
        "date_time": "2025-10-11T19:00:00Z",
        "home_team": {"id": HOME_TEAM_ID, "name": "Home FC"},
        "away_team": {"id": AWAY_TEAM_ID, "name": "Away FC"},
        "home_score": 83,
        "away_score": 68,
        "competition_id": 8,
        "competition_name": "Liga ACB",
        "season_id": 51,
        "competition_edition_id": 211,
        "season": "2025-2026",
        "status": "closed",
    },
    {
        "id": MATCH_B,
        "date_time": "2025-10-12T19:00:00Z",
        "home_team": {"id": AWAY_TEAM_ID, "name": "Away FC"},
        "away_team": {"id": HOME_TEAM_ID, "name": "Home FC"},
        "home_score": 70,
        "away_score": 72,
        "competition_id": 8,
        "competition_name": "Liga ACB",
        "season_id": 51,
        "competition_edition_id": 211,
        "season": "2025-2026",
        "status": "closed",
    },
]

ALIASES_ROWS = [
    {
        "player_id": "59129",
        "player_name": "Nihad Djedovic",
        "canonical_player_id": "59129",
        "canonical_player_name": "Nihad Djedovic",
        "acb_player_id": "20202039",
    },
    {
        "player_id": "59237",
        "player_name": "Nihad Dedovic",
        "canonical_player_id": "59129",
        "canonical_player_name": "Nihad Djedovic",
        "acb_player_id": "20202039",
    },
]


def write_json(path: Path, data: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(data).encode("utf-8")
    path.write_bytes(blob)
    return blob


def write_aliases_csv(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ALIASES_ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(ALIASES_ROWS)
    return path.read_bytes()


def entry(path: str, blob: bytes, role: str, match_id: int | None) -> FileEntry:
    return FileEntry(
        path=path,
        bytes=len(blob),
        sha256=hashlib.sha256(blob).hexdigest(),
        lfs=False,
        role=role,
        match_id=match_id,
    )


def frozen_source(files: list[FileEntry]) -> Source:
    repo = "SkillCorner/opendata-basketball"
    return Source(
        source_id=SOURCE_ID,
        sport="basketball",
        kind="github",
        repo=repo,
        ref="main",
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
        "verified": 4,
        "downloaded": 0,
        "failed": [],
        "finished_at": "2026-09-21T15:47:27+00:00",
        "source_path": str(source_path),
    }
    (receipt_dir / RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, Path]:
    """(manifest path, data dir): 2 matches' game_data, matches.json and aliases CSV."""
    clone = tmp_path / "clone"
    data_dir = tmp_path / "data"
    entries = []
    for match_id in (MATCH_A, MATCH_B):
        blob = write_json(clone / game_data_path(match_id), game_data(match_id))
        entries.append(entry(game_data_path(match_id), blob, "game_data", match_id))
    matches_blob = write_json(clone / "data" / "matches.json", MATCHES_JSON)
    entries.append(entry("data/matches.json", matches_blob, "matches", None))
    aliases_blob = write_aliases_csv(clone / "data" / "player_id_aliases.csv")
    entries.append(entry("data/player_id_aliases.csv", aliases_blob, "player_aliases", None))

    manifest_path = tmp_path / "sources.json"
    save_manifest(Manifest(schema_version=1, sources=[frozen_source(entries)]), manifest_path)
    write_receipt(data_dir, clone)
    return manifest_path, data_dir


def rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


def run_meta(manifest_path: Path, data_dir: Path) -> int:
    return main(
        [
            "bronze",
            "basketball",
            "--tables",
            "meta",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(data_dir),
        ]
    )


def test_games_one_row_per_match_with_flattened_header(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    assert run_meta(manifest_path, data_dir) == 0

    for match_id in (MATCH_A, MATCH_B):
        games = rows(bronze_path(data_dir, "basketball", "games", match_id))
        assert len(games) == 1
        row = games[0]
        assert row["gameId"] == match_id
        assert row["homeTeamId"] == HOME_TEAM_ID
        assert row["awayTeamId"] == AWAY_TEAM_ID
        assert row["seasonName"] == "2025-2026"
        assert (row["sport"], row["match_id"], row["source_row"]) == ("basketball", match_id, 0)


def test_game_players_flattens_roster_with_side_and_team_id(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    run_meta(manifest_path, data_dir)

    players = rows(bronze_path(data_dir, "basketball", "game_players", MATCH_A))
    assert len(players) == 3, "2 home + 1 away"
    assert [p["side"] for p in players] == ["home", "home", "away"]
    assert [p["source_row"] for p in players] == [0, 1, 2], "home then away, flattened"
    assert [p["playerId"] for p in players] == [1, 2, 3]
    assert [p["teamId"] for p in players] == [HOME_TEAM_ID, HOME_TEAM_ID, AWAY_TEAM_ID]
    assert all(isinstance(p["jersey"], str) for p in players), "jersey stays a string"


def test_matches_is_one_season_file_flattening_home_and_away_team(
    bundle: tuple[Path, Path],
) -> None:
    manifest_path, data_dir = bundle
    run_meta(manifest_path, data_dir)

    path = bronze_season_path(data_dir, "basketball", "matches")
    matches = rows(path)
    assert len(matches) == 2, "one file, both matches"
    assert [m["match_id"] for m in matches] == [MATCH_A, MATCH_B], "match_id is the native id"
    assert [m["id"] for m in matches] == [MATCH_A, MATCH_B]
    assert matches[0]["home_team_id"] == HOME_TEAM_ID
    assert matches[0]["home_team_name"] == "Home FC"
    assert matches[0]["away_team_id"] == AWAY_TEAM_ID
    assert matches[0]["status"] == "closed"
    assert [m["source_row"] for m in matches] == [0, 1]


def test_player_id_aliases_has_no_match_id(bundle: tuple[Path, Path]) -> None:
    manifest_path, data_dir = bundle
    run_meta(manifest_path, data_dir)

    path = bronze_season_path(data_dir, "basketball", "player_id_aliases")
    aliases = rows(path)
    assert len(aliases) == 2
    assert "match_id" not in aliases[0], "season-grain table: no match dimension at all"
    assert [a["player_id"] for a in aliases] == [59129, 59237]
    assert [a["canonical_player_id"] for a in aliases] == [59129, 59129]
    assert [a["acb_player_id"] for a in aliases] == [20202039, 20202039]
    assert [a["source_row"] for a in aliases] == [0, 1]


def test_game_id_mismatch_fails_naming_the_file(tmp_path: Path) -> None:
    raw_root = tmp_path / "clone"
    data_dir = tmp_path / "data"
    bad = game_data(MATCH_A)
    bad["gameId"] = 999999
    blob = write_json(raw_root / game_data_path(MATCH_A), bad)
    source = frozen_source([entry(game_data_path(MATCH_A), blob, "game_data", MATCH_A)])

    def log(_: str) -> None:
        pass

    with pytest.raises(ValueError, match=r"gameId 999999 != 900001"):
        build_games_and_players(source, raw_root, data_dir, COMMIT, log)
