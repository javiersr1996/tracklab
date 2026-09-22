"""Bronze of the basketball metadata: ``games``, ``game_players``, ``matches``,
``player_id_aliases``.

All four are small enough (12 header keys, 10-12 players a side, 10 matches, 18 alias
rows) that their schema is pyarrow written in code, not frozen by
``tracklab freeze-schema`` like the wide event families in ``events.py``. ``games``
and ``game_players`` share one read of ``game_data.json`` per match (both come from
the same file, so it is only parsed once). ``matches`` is the one exception to
per-match files: ``matches.json`` already holds all 10 matches together, so bronze
keeps it as a single file at the season path while every row still carries its own
``match_id`` (the native ``id``) in ``LINEAGE_FIELDS`` -- see ``bronze.common`` for
why that is a deliberate exception, not an oversight. ``player_id_aliases`` has no
match dimension at all and uses ``SEASON_LINEAGE_FIELDS`` (no ``match_id``).
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

from tracklab.bronze.common import (
    LINEAGE_FIELDS,
    SEASON_LINEAGE_FIELDS,
    ParquetSink,
    batch_from_columns,
    bronze_path,
    bronze_season_path,
)
from tracklab.ingest.manifest import FileEntry, Source

SPORT = "basketball"
Log = Callable[[str], None]

GAMES_SCHEMA = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("gameId", pa.int64(), nullable=False),
        pa.field("date", pa.string(), nullable=False),
        pa.field("competitionEditionId", pa.int64(), nullable=False),
        pa.field("competitionId", pa.int64(), nullable=False),
        pa.field("competitionName", pa.string(), nullable=False),
        pa.field("seasonId", pa.int64(), nullable=False),
        pa.field("seasonName", pa.string(), nullable=False),
        pa.field("dynamicEventsLastProcessingDate", pa.string(), nullable=False),
        pa.field("trackingLastProcessingDate", pa.string(), nullable=False),
        pa.field("physicalLastProcessingDate", pa.string(), nullable=False),
        pa.field("homeTeamId", pa.int64(), nullable=False),
        pa.field("homeTeamName", pa.string(), nullable=False),
        pa.field("awayTeamId", pa.int64(), nullable=False),
        pa.field("awayTeamName", pa.string(), nullable=False),
    ]
)

GAME_PLAYERS_SCHEMA = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("side", pa.string(), nullable=False),  # 'home' | 'away'
        pa.field("playerId", pa.int64(), nullable=False),
        pa.field("firstName", pa.string(), nullable=False),
        pa.field("lastName", pa.string(), nullable=False),
        pa.field("jersey", pa.string(), nullable=False),  # delivered as a string, e.g. "0"
        pa.field("teamId", pa.int64(), nullable=False),
    ]
)

MATCHES_SCHEMA = pa.schema(
    [
        *LINEAGE_FIELDS,
        pa.field("id", pa.int64(), nullable=False),
        pa.field("date_time", pa.string(), nullable=False),
        pa.field("home_team_id", pa.int64(), nullable=False),
        pa.field("home_team_name", pa.string(), nullable=False),
        pa.field("away_team_id", pa.int64(), nullable=False),
        pa.field("away_team_name", pa.string(), nullable=False),
        pa.field("home_score", pa.int64(), nullable=False),
        pa.field("away_score", pa.int64(), nullable=False),
        pa.field("competition_id", pa.int64(), nullable=False),
        pa.field("competition_name", pa.string(), nullable=False),
        pa.field("season_id", pa.int64(), nullable=False),
        pa.field("competition_edition_id", pa.int64(), nullable=False),
        pa.field("season", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
    ]
)

PLAYER_ALIASES_SCHEMA = pa.schema(
    [
        *SEASON_LINEAGE_FIELDS,
        pa.field("player_id", pa.int64(), nullable=False),
        pa.field("player_name", pa.string(), nullable=False),
        pa.field("canonical_player_id", pa.int64(), nullable=False),
        pa.field("canonical_player_name", pa.string(), nullable=False),
        pa.field("acb_player_id", pa.int64(), nullable=False),
    ]
)

TABLES = {
    "games": GAMES_SCHEMA,
    "game_players": GAME_PLAYERS_SCHEMA,
    "matches": MATCHES_SCHEMA,
    "player_id_aliases": PLAYER_ALIASES_SCHEMA,
}


@dataclass(frozen=True)
class MetaStats:
    table: str
    match_id: int | None
    rows: int
    seconds: float
    mb: float


def _log_stat(log: Log, s: MetaStats) -> None:
    match_id = s.match_id if s.match_id is not None else "-"
    log(f"{s.table:>17} {match_id:>8} {s.rows:>6} {s.seconds:>8.2f} {s.mb:>7.2f}")


def _only_file(source: Source, role: str) -> FileEntry:
    matches = [f for f in source.files if f.role == role and f.match_id is None]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one '{role}' file, found {len(matches)}")
    return matches[0]


def _games_and_players_batches(
    game_data: dict[str, Any], match_id: int, source_file: str
) -> tuple[pa.RecordBatch, pa.RecordBatch]:
    lineage = {"sport": SPORT, "match_id": match_id, "source_file": source_file}
    games_columns: dict[str, Any] = {
        **lineage,
        "source_row": [0],
        "gameId": [game_data["gameId"]],
        "date": [game_data["date"]],
        "competitionEditionId": [game_data["competitionEditionId"]],
        "competitionId": [game_data["competitionId"]],
        "competitionName": [game_data["competitionName"]],
        "seasonId": [game_data["seasonId"]],
        "seasonName": [game_data["seasonName"]],
        "dynamicEventsLastProcessingDate": [game_data["dynamicEventsLastProcessingDate"]],
        "trackingLastProcessingDate": [game_data["trackingLastProcessingDate"]],
        "physicalLastProcessingDate": [game_data["physicalLastProcessingDate"]],
        "homeTeamId": [game_data["homeTeam"]["teamId"]],
        "homeTeamName": [game_data["homeTeam"]["teamName"]],
        "awayTeamId": [game_data["awayTeam"]["teamId"]],
        "awayTeamName": [game_data["awayTeam"]["teamName"]],
    }
    games_batch = batch_from_columns(GAMES_SCHEMA, games_columns, 1)

    sides: list[str] = []
    player_ids: list[int] = []
    first_names: list[str] = []
    last_names: list[str] = []
    jerseys: list[str] = []
    team_ids: list[int] = []
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        team = game_data[key]
        for player in team["players"]:
            sides.append(side)
            player_ids.append(player["playerId"])
            first_names.append(player["firstName"])
            last_names.append(player["lastName"])
            jerseys.append(player["jersey"])
            team_ids.append(team["teamId"])
    n = len(sides)
    players_columns: dict[str, Any] = {
        **lineage,
        "source_row": list(range(n)),
        "side": sides,
        "playerId": player_ids,
        "firstName": first_names,
        "lastName": last_names,
        "jersey": jerseys,
        "teamId": team_ids,
    }
    players_batch = batch_from_columns(GAME_PLAYERS_SCHEMA, players_columns, n)
    return games_batch, players_batch


def build_games_and_players(
    source: Source, raw_root: Path, data_dir: Path, commit: str, log: Log
) -> list[MetaStats]:
    entries = sorted(
        (f for f in source.files if f.role == "game_data" and f.match_id is not None),
        key=lambda f: f.match_id or 0,
    )
    stats: list[MetaStats] = []
    for entry in entries:
        assert entry.match_id is not None
        started = time.perf_counter()
        game_data = json.loads((raw_root / entry.path).read_text(encoding="utf-8"))
        if game_data["gameId"] != entry.match_id:
            raise ValueError(f"{entry.path}: gameId {game_data['gameId']} != {entry.match_id}")
        games_batch, players_batch = _games_and_players_batches(
            game_data, entry.match_id, entry.path
        )
        metadata = {
            "tracklab.sport": SPORT,
            "tracklab.source_file": entry.path,
            "tracklab.source_sha256": entry.sha256,
            "tracklab.source_commit": commit,
        }
        games_path = bronze_path(data_dir, SPORT, "games", entry.match_id)
        players_path = bronze_path(data_dir, SPORT, "game_players", entry.match_id)
        with ParquetSink(games_path, GAMES_SCHEMA, metadata) as games_sink:
            games_sink.write(games_batch)
        with ParquetSink(players_path, GAME_PLAYERS_SCHEMA, metadata) as players_sink:
            players_sink.write(players_batch)
        seconds = time.perf_counter() - started
        s_games = MetaStats(
            "games", entry.match_id, games_sink.rows, seconds, games_sink.bytes / 1e6
        )
        s_players = MetaStats(
            "game_players", entry.match_id, players_sink.rows, seconds, players_sink.bytes / 1e6
        )
        _log_stat(log, s_games)
        _log_stat(log, s_players)
        stats += [s_games, s_players]
    return stats


def build_matches(
    source: Source, raw_root: Path, data_dir: Path, commit: str, log: Log
) -> MetaStats:
    entry = _only_file(source, "matches")
    started = time.perf_counter()
    matches = json.loads((raw_root / entry.path).read_text(encoding="utf-8"))
    n = len(matches)
    columns: dict[str, Any] = {
        "sport": SPORT,
        "match_id": [m["id"] for m in matches],
        "source_file": entry.path,
        "source_row": list(range(n)),
        "id": [m["id"] for m in matches],
        "date_time": [m["date_time"] for m in matches],
        "home_team_id": [m["home_team"]["id"] for m in matches],
        "home_team_name": [m["home_team"]["name"] for m in matches],
        "away_team_id": [m["away_team"]["id"] for m in matches],
        "away_team_name": [m["away_team"]["name"] for m in matches],
        "home_score": [m["home_score"] for m in matches],
        "away_score": [m["away_score"] for m in matches],
        "competition_id": [m["competition_id"] for m in matches],
        "competition_name": [m["competition_name"] for m in matches],
        "season_id": [m["season_id"] for m in matches],
        "competition_edition_id": [m["competition_edition_id"] for m in matches],
        "season": [m["season"] for m in matches],
        "status": [m["status"] for m in matches],
    }
    batch = batch_from_columns(MATCHES_SCHEMA, columns, n)
    metadata = {
        "tracklab.sport": SPORT,
        "tracklab.source_file": entry.path,
        "tracklab.source_sha256": entry.sha256,
        "tracklab.source_commit": commit,
    }
    path = bronze_season_path(data_dir, SPORT, "matches")
    with ParquetSink(path, MATCHES_SCHEMA, metadata) as sink:
        sink.write(batch)
    s = MetaStats("matches", None, sink.rows, time.perf_counter() - started, sink.bytes / 1e6)
    _log_stat(log, s)
    return s


def build_player_aliases(
    source: Source, raw_root: Path, data_dir: Path, commit: str, log: Log
) -> MetaStats:
    entry = _only_file(source, "player_aliases")
    started = time.perf_counter()
    path = raw_root / entry.path
    with path.open(encoding="utf-8", newline="") as fh:
        records = list(csv.DictReader(fh))
    n = len(records)
    columns: dict[str, Any] = {
        "sport": SPORT,
        "source_file": entry.path,
        "source_row": list(range(n)),
        "player_id": [int(r["player_id"]) for r in records],
        "player_name": [r["player_name"] for r in records],
        "canonical_player_id": [int(r["canonical_player_id"]) for r in records],
        "canonical_player_name": [r["canonical_player_name"] for r in records],
        "acb_player_id": [int(r["acb_player_id"]) for r in records],
    }
    batch = batch_from_columns(PLAYER_ALIASES_SCHEMA, columns, n)
    metadata = {
        "tracklab.sport": SPORT,
        "tracklab.source_file": entry.path,
        "tracklab.source_sha256": entry.sha256,
        "tracklab.source_commit": commit,
    }
    path_out = bronze_season_path(data_dir, SPORT, "player_id_aliases")
    with ParquetSink(path_out, PLAYER_ALIASES_SCHEMA, metadata) as sink:
        sink.write(batch)
    s = MetaStats(
        "player_id_aliases", None, sink.rows, time.perf_counter() - started, sink.bytes / 1e6
    )
    _log_stat(log, s)
    return s


def build_meta(source: Source, raw_root: Path, data_dir: Path, log: Log = print) -> list[MetaStats]:
    """``games``, ``game_players``, ``matches`` and ``player_id_aliases``, in that order."""
    commit = source.commit
    if commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    log(f"{'table':>17} {'match_id':>8} {'rows':>6} {'seconds':>8} {'MB':>7}")
    stats = build_games_and_players(source, raw_root, data_dir, commit, log)
    stats.append(build_matches(source, raw_root, data_dir, commit, log))
    stats.append(build_player_aliases(source, raw_root, data_dir, commit, log))
    return stats
