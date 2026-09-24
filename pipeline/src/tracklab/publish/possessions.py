"""`tracklab publish possessions`: six curated possessions per sport, picked in
code rather than by hand (task 17 of tasks/todo.md).

* **Basketball**: a `chances` row that is `usable`, `qualityIndex = 5` and
  `ptsScored > 0` -- SkillCorner's own top-quality, scored look -- on the
  possession it belongs to; 8-20 s long; the 10 players on the floor with
  `is_detected` in 90% or more of the possession's frames; the ball present
  in 90% or more (see the deviation below); from at least 4 distinct matches.
* **Football**: a derived team possession (task 12's `chain` rule, already in
  silver `events`) that contains a `phases_of_play` phase with
  `team_possession_lead_to_shot`; 10-25 s long; the 22 players and the ball
  present in 90% or more of the possession's frames; from at least 4 distinct
  matches.

Coverage is measured against silver `frames`, never against an event's own
coordinates: task 9 found that `shots.location` does not say where the
shooter stood at `startFrame`, and that lesson applies to any event column
someone might be tempted to read a position from.

**Deviation from the plan, measured rather than silently patched.** The plan
asks for the basketball ball's `is_detected` at 90% or more, worded exactly
like its players. Measured on the built bronze: `isDetected` is `false` on
all 829,704 ball observations of the 10 matches
(`bronze.basketball.tracking_objects` where `side = 'ball'`), in every one of
them individually, not just on average -- so that literal bar is 0%, in all
10 matches, never a number close to 90%. This is not a quality problem in
these particular matches; it is what the provider always sends for this
field on this object (players carry a real, varying 0/1 mix: 69-94% detected
per match in the candidates below). Football's own sentence in the plan uses
"presentes" (present), not `is_detected`, for exactly this reason -- task 4
already found football's intermittence lives in `is_detected` per player
while presence is binary at the frame level. This module reads "the ball
present" as a `<prefix>:ball` row existing in `frames`, in both sports, and
keeps `is_detected` for players (basketball) or presence for players
(football, per the plan's own wording). That is the only reading under which
the basketball ball's number measures anything at all; it is not a lowered
bar; the same 90% still applies, to a metric that is not always-zero.

If a rule cannot fill 6 possessions from at least 4 matches, this module does
not relax it: `run_publish_possessions` prints how many candidates survive
each stage and returns 1.
"""

from __future__ import annotations

import glob as globmod
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from tracklab.silver.stats import table_glob

SCHEMA_VERSION = 1
N_POSSESSIONS = 6
MIN_MATCHES = 4
COVERAGE_PCT = 90.0
MAX_BYTES = 300_000
ROUND_NDIGITS = 2

BASKETBALL_DURATION_S = (8.0, 20.0)
FOOTBALL_DURATION_S = (10.0, 25.0)
BASKETBALL_FPS = 25.0
FOOTBALL_FPS = 10.0
BASKETBALL_N_PLAYERS = 10
FOOTBALL_N_PLAYERS = 22


@dataclass(frozen=True)
class Candidate:
    """One possession that passed every filter, with the numbers that got it
    there. `min_player_coverage_pct` is `is_detected` share for basketball and
    presence share for football; `ball_coverage_pct` is presence in both."""

    possession_id: str
    sport: str
    match_id: str
    native_match_id: int
    period: int
    frame_start: int
    frame_end: int
    team_id: str
    duration_s: float
    n_players: int
    min_player_coverage_pct: float
    ball_coverage_pct: float


@dataclass(frozen=True)
class Funnel:
    """How many possessions survive each stage, per sport. Printed so a rule
    that comes up short says exactly where, instead of just failing."""

    quality: int
    duration: int
    coverage: int
    matches: int


def _view(con: duckdb.DuckDBPyConnection, name: str, glob: str, hint: str) -> None:
    if not globmod.glob(glob, recursive=True):
        raise FileNotFoundError(f"{glob} is empty; run `{hint}`")
    con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{glob}')")


def register_candidate_views(con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
    """`events` and `frames`: what both sports' candidate search reads.
    `register_basketball_chances_view` adds the one bronze table basketball
    also needs; `register_payload_views` adds what building the JSON needs."""
    _view(con, "events", table_glob(data_dir, "events"), "dbt build --select events")
    _view(con, "frames", table_glob(data_dir, "frames"), "dbt build --select frames")


def register_basketball_chances_view(con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
    """The one bronze table (`events_chances`) that carries the basketball
    quality columns silver does not copy (decision 5: what a join can recover
    is not duplicated). Football's candidate search never needs this."""
    chances = (data_dir / "bronze" / "basketball" / "events_chances" / "*.parquet").as_posix()
    _view(con, "chances", chances, "tracklab bronze basketball --tables events")


def register_payload_views(con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
    """The dimensions `build_payload` reads: match and team metadata, sport
    constants, the roster and the attack sign."""
    _view(con, "dim_match", table_glob(data_dir, "dim_match"), "dbt build --select dim_match")
    _view(con, "dim_team", table_glob(data_dir, "dim_team"), "dbt build --select dim_team")
    _view(con, "dim_sport", table_glob(data_dir, "dim_sport"), "dbt build --select dim_sport")
    _view(con, "dim_entity", table_glob(data_dir, "dim_entity"), "dbt build --select dim_entity")
    _view(
        con,
        "dim_team_period",
        table_glob(data_dir, "dim_team_period"),
        "dbt build --select dim_team_period",
    )


def register_views(con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
    """Every table this module reads: candidates, basketball's chances and the
    payload views."""
    register_candidate_views(con, data_dir)
    register_basketball_chances_view(con, data_dir)
    register_payload_views(con, data_dir)


_BASKETBALL_CANDIDATES_SQL = """
WITH good_chances AS (
    SELECT DISTINCT gameId, possessionId
    FROM chances
    WHERE usable AND qualityIndex = 5 AND ptsScored > 0
),
possessions AS (
    SELECT
        e.event_id AS possession_id, e.match_id, e.native_match_id, e.period,
        e.frame_start, e.frame_end, e.team_id,
        (e.frame_end - e.frame_start) / {fps} AS duration_s
    FROM events e
    JOIN good_chances g ON g.gameId = e.native_match_id AND g.possessionId = e.native_event_id
    WHERE e.sport = 'basketball' AND e.event_type = 'possession'
),
windowed AS (
    SELECT * FROM possessions WHERE duration_s BETWEEN {lo} AND {hi}
),
entities AS (
    SELECT
        w.possession_id, w.match_id, w.frame_start, w.frame_end,
        f.entity_id, f.entity_kind,
        count(*) AS n_rows,
        count(*) FILTER (WHERE f.is_detected) AS n_detected
    FROM windowed w
    JOIN frames f
      ON f.match_id = w.match_id AND f.frame_native BETWEEN w.frame_start AND w.frame_end
    WHERE f.entity_kind IN ('player', 'ball')
    GROUP BY w.possession_id, w.match_id, w.frame_start, w.frame_end, f.entity_id, f.entity_kind
),
summary AS (
    SELECT
        possession_id, match_id, frame_start, frame_end,
        count(*) FILTER (WHERE entity_kind = 'player') AS n_players,
        count(*) FILTER (WHERE entity_kind = 'ball') AS n_ball,
        -- Over every frame of the possession, not the rows present: a frame that
        -- is missing from `frames` is not a frame the player was detected in.
        min(100.0 * n_detected / (frame_end - frame_start + 1))
            FILTER (WHERE entity_kind = 'player') AS min_player_coverage_pct,
        max(100.0 * n_rows / (frame_end - frame_start + 1))
            FILTER (WHERE entity_kind = 'ball') AS ball_coverage_pct
    FROM entities
    GROUP BY possession_id, match_id, frame_start, frame_end
)
SELECT
    w.possession_id, w.match_id, w.native_match_id, w.period, w.frame_start, w.frame_end,
    w.team_id, w.duration_s, s.n_players, s.min_player_coverage_pct, s.ball_coverage_pct
FROM windowed w
JOIN summary s USING (possession_id, match_id, frame_start, frame_end)
ORDER BY w.match_id, w.frame_start
"""

_FOOTBALL_CANDIDATES_SQL = """
WITH shot_possessions AS (
    SELECT DISTINCT possession_id
    FROM events
    WHERE sport = 'football' AND native_family = 'phases_of_play'
      AND outcome = 'shot' AND possession_id IS NOT NULL
),
possessions AS (
    SELECT
        p.event_id AS possession_id, p.match_id, p.native_match_id, p.period,
        p.frame_start, p.frame_end, p.team_id,
        (p.frame_end - p.frame_start) / {fps} AS duration_s
    FROM events p
    JOIN shot_possessions s ON s.possession_id = p.event_id
    WHERE p.sport = 'football' AND p.event_type = 'possession'
),
windowed AS (
    SELECT * FROM possessions WHERE duration_s BETWEEN {lo} AND {hi}
),
entities AS (
    SELECT
        w.possession_id, w.match_id, w.frame_start, w.frame_end,
        f.entity_id, f.entity_kind,
        count(*) AS n_rows
    FROM windowed w
    JOIN frames f
      ON f.match_id = w.match_id AND f.frame_native BETWEEN w.frame_start AND w.frame_end
    WHERE f.entity_kind IN ('player', 'ball')
    GROUP BY w.possession_id, w.match_id, w.frame_start, w.frame_end, f.entity_id, f.entity_kind
),
summary AS (
    SELECT
        possession_id, match_id, frame_start, frame_end,
        count(*) FILTER (WHERE entity_kind = 'player') AS n_players,
        count(*) FILTER (WHERE entity_kind = 'ball') AS n_ball,
        min(100.0 * n_rows / (frame_end - frame_start + 1))
            FILTER (WHERE entity_kind = 'player') AS min_player_coverage_pct,
        max(100.0 * n_rows / (frame_end - frame_start + 1))
            FILTER (WHERE entity_kind = 'ball') AS ball_coverage_pct
    FROM entities
    GROUP BY possession_id, match_id, frame_start, frame_end
)
SELECT
    w.possession_id, w.match_id, w.native_match_id, w.period, w.frame_start, w.frame_end,
    w.team_id, w.duration_s, s.n_players, s.min_player_coverage_pct, s.ball_coverage_pct
FROM windowed w
JOIN summary s USING (possession_id, match_id, frame_start, frame_end)
ORDER BY w.match_id, w.frame_start
"""


def _rows_to_candidates(sport: str, rows: list[tuple[Any, ...]]) -> list[Candidate]:
    return [
        Candidate(
            possession_id=str(r[0]),
            sport=sport,
            match_id=str(r[1]),
            native_match_id=int(r[2]),
            period=int(r[3]),
            frame_start=int(r[4]),
            frame_end=int(r[5]),
            team_id=str(r[6]),
            duration_s=float(r[7]),
            n_players=int(r[8]),
            min_player_coverage_pct=float(r[9]) if r[9] is not None else 0.0,
            ball_coverage_pct=float(r[10]) if r[10] is not None else 0.0,
        )
        for r in rows
    ]


def basketball_candidates(con: duckdb.DuckDBPyConnection) -> tuple[list[Candidate], Funnel]:
    lo, hi = BASKETBALL_DURATION_S
    quality = con.execute(
        "SELECT count(DISTINCT (gameId, possessionId)) FROM chances "
        "WHERE usable AND qualityIndex = 5 AND ptsScored > 0"
    ).fetchone()
    assert quality is not None
    sql = _BASKETBALL_CANDIDATES_SQL.format(fps=BASKETBALL_FPS, lo=lo, hi=hi)
    rows = con.execute(sql).fetchall()
    duration_n = len(rows)
    candidates = [
        c
        for c in _rows_to_candidates("basketball", rows)
        if c.n_players == BASKETBALL_N_PLAYERS
        and c.min_player_coverage_pct >= COVERAGE_PCT
        and c.ball_coverage_pct >= COVERAGE_PCT
    ]
    funnel = Funnel(
        quality=int(quality[0]),
        duration=duration_n,
        coverage=len(candidates),
        matches=len({c.match_id for c in candidates}),
    )
    return candidates, funnel


def football_candidates(con: duckdb.DuckDBPyConnection) -> tuple[list[Candidate], Funnel]:
    lo, hi = FOOTBALL_DURATION_S
    quality = con.execute(
        "SELECT count(DISTINCT possession_id) FROM events "
        "WHERE sport = 'football' AND native_family = 'phases_of_play' "
        "AND outcome = 'shot' AND possession_id IS NOT NULL"
    ).fetchone()
    assert quality is not None
    sql = _FOOTBALL_CANDIDATES_SQL.format(fps=FOOTBALL_FPS, lo=lo, hi=hi)
    rows = con.execute(sql).fetchall()
    duration_n = len(rows)
    candidates = [
        c
        for c in _rows_to_candidates("football", rows)
        if c.n_players == FOOTBALL_N_PLAYERS
        and c.min_player_coverage_pct >= COVERAGE_PCT
        and c.ball_coverage_pct >= COVERAGE_PCT
    ]
    funnel = Funnel(
        quality=int(quality[0]),
        duration=duration_n,
        coverage=len(candidates),
        matches=len({c.match_id for c in candidates}),
    )
    return candidates, funnel


def select_six(candidates: list[Candidate]) -> list[Candidate]:
    """Round-robins across matches, earliest possession first within a match:
    reproducible, and it spreads the pick across matches instead of clustering
    in whichever one happens to have the most qualifying possessions. `frames`
    orders by (match, frame) and nothing else (a documented invariant), so the
    tie-break here is this module's own, not inherited from a read order."""
    by_match: dict[str, list[Candidate]] = {}
    for c in sorted(candidates, key=lambda c: (c.match_id, c.frame_start, c.possession_id)):
        by_match.setdefault(c.match_id, []).append(c)
    matches = sorted(by_match)

    chosen: list[Candidate] = []
    round_idx = 0
    while len(chosen) < N_POSSESSIONS:
        added = False
        for match_id in matches:
            bucket = by_match[match_id]
            if round_idx < len(bucket):
                chosen.append(bucket[round_idx])
                added = True
                if len(chosen) == N_POSSESSIONS:
                    break
        if not added:
            break
        round_idx += 1
    return chosen


def safe_filename(possession_id: str) -> str:
    """A possession id carries colons (`bb:possessions:...`), which Windows
    refuses in a file name (task 11 hit the same wall on `match_id`)."""
    return possession_id.replace(":", "_") + ".json"


def _entities(
    con: duckdb.DuckDBPyConnection, match_id: str, frame_start: int, frame_end: int
) -> list[dict[str, Any]]:
    """The roster of the possession: only entities with at least one row in
    `frames` inside the window, from `dim_entity`. Players first, then the
    ball, grouped by team and then by id, so the index assignment is fixed
    even though a frame's own entity order is not (that ordering is this
    module's job, not the source table's)."""
    rows = con.execute(
        """
        WITH present AS (
            SELECT DISTINCT entity_id
            FROM frames
            WHERE match_id = ? AND frame_native BETWEEN ? AND ?
        )
        SELECT e.entity_id, e.entity_kind, e.team_id, e.name, e.jersey
        FROM dim_entity e
        JOIN present p ON p.entity_id = e.entity_id
        WHERE e.match_id = ?
        ORDER BY e.entity_kind = 'ball', e.team_id, e.entity_id
        """,
        [match_id, frame_start, frame_end, match_id],
    ).fetchall()
    entities = []
    for i, (entity_id, kind, team_id, name, jersey) in enumerate(rows):
        is_ball = kind == "ball"
        entities.append(
            {
                "i": i,
                "entity_id": str(entity_id),
                "kind": str(kind),
                "team_id": None if is_ball else str(team_id),
                "jersey": None if is_ball else (str(jersey) if jersey is not None else None),
                # dim_entity fills the synthetic ball row's name with the literal
                # 'ball' so the column is never null by accident; the contract
                # has no use for a ball's name, so publish nulls it out here.
                "name": None if is_ball else (str(name) if name is not None else None),
            }
        )
    return entities


def _frames(
    con: duckdb.DuckDBPyConnection,
    match_id: str,
    frame_start: int,
    frame_end: int,
    index_by_entity: dict[str, int],
) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT frame_native, t_ms, clock_s, entity_id, x_m, y_m, z_m, is_detected
        FROM frames
        WHERE match_id = ? AND frame_native BETWEEN ? AND ?
        ORDER BY frame_native, entity_id
        """,
        [match_id, frame_start, frame_end],
    ).fetchall()

    by_frame: dict[int, dict[str, Any]] = {}
    for frame_native, t_ms, clock_s, entity_id, x_m, y_m, z_m, is_detected in rows:
        if entity_id not in index_by_entity:
            continue
        clock = round(float(clock_s), ROUND_NDIGITS)
        entry = by_frame.setdefault(int(frame_native), {"t": int(t_ms), "clock": clock, "o": []})
        entry["o"].append(
            [
                index_by_entity[entity_id],
                round(float(x_m), ROUND_NDIGITS),
                round(float(y_m), ROUND_NDIGITS),
                None if z_m is None else round(float(z_m), ROUND_NDIGITS),
                1 if is_detected else 0,
            ]
        )
    for entry in by_frame.values():
        entry["o"].sort(key=lambda o: o[0])  # by entity index: a frame's own order is not given
    return [by_frame[f] for f in sorted(by_frame)]


def _match_block(con: duckdb.DuckDBPyConnection, match_id: str) -> dict[str, Any]:
    row = con.execute(
        """
        SELECT m.match_id, home.name, away.name, m.kickoff_utc,
               m.surface_spec, m.surface_length_m, m.surface_width_m
        FROM dim_match m
        JOIN dim_team home ON home.team_id = m.home_team_id
        JOIN dim_team away ON away.team_id = m.away_team_id
        WHERE m.match_id = ?
        """,
        [match_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"no dim_match row for {match_id}")
    match_id_v, home, away, kickoff, spec, length_m, width_m = row
    return {
        "match": {
            "match_id": str(match_id_v),
            "home": str(home),
            "away": str(away),
            "kickoff_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "surface": {
            "spec": str(spec),
            "length_m": float(length_m),
            "width_m": float(width_m),
        },
    }


def _sport_block(con: duckdb.DuckDBPyConnection, sport: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT clock_kind, sample_rate_hz FROM dim_sport WHERE sport = ?", [sport]
    ).fetchone()
    if row is None:
        raise ValueError(f"no dim_sport row for {sport}")
    clock_kind, sample_rate_hz = row
    return {"clock_kind": str(clock_kind), "sample_rate_hz": int(sample_rate_hz)}


def _attack_sign(con: duckdb.DuckDBPyConnection, match_id: str, period: int, team_id: str) -> int:
    row = con.execute(
        "SELECT attack_sign FROM dim_team_period WHERE match_id = ? AND period = ? AND team_id = ?",
        [match_id, period, team_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"no dim_team_period row for {match_id} period {period} team {team_id}")
    return int(row[0])


def build_payload(con: duckdb.DuckDBPyConnection, candidate: Candidate) -> dict[str, Any]:
    entities = _entities(con, candidate.match_id, candidate.frame_start, candidate.frame_end)
    index_by_entity = {e["entity_id"]: e["i"] for e in entities}
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "possession_id": candidate.possession_id,
        "sport": candidate.sport,
        **_match_block(con, candidate.match_id),
        **_sport_block(con, candidate.sport),
        "team_in_possession": candidate.team_id,
        "attack_sign": _attack_sign(con, candidate.match_id, candidate.period, candidate.team_id),
        "entities": entities,
        "frames": _frames(
            con, candidate.match_id, candidate.frame_start, candidate.frame_end, index_by_entity
        ),
    }
    return payload


def run_publish_possessions(data_dir: Path, out_dir: Path) -> int:
    con = duckdb.connect()
    register_views(con, data_dir)

    bb_candidates, bb_funnel = basketball_candidates(con)
    fb_candidates, fb_funnel = football_candidates(con)

    ok = True
    chosen: dict[str, list[Candidate]] = {}
    for sport, candidates, funnel in (
        ("basketball", bb_candidates, bb_funnel),
        ("football", fb_candidates, fb_funnel),
    ):
        print(
            f"publish possessions {sport}: {funnel.quality} pass the quality filter, "
            f"{funnel.duration} in the duration window, {funnel.coverage} meet "
            f"{COVERAGE_PCT}% coverage, across {funnel.matches} matches"
        )
        picked = select_six(candidates)
        if len(picked) < N_POSSESSIONS or len({c.match_id for c in picked}) < MIN_MATCHES:
            print(
                f"FAIL publish possessions {sport}: only {len(picked)} of {N_POSSESSIONS} "
                f"possessions available across {len({c.match_id for c in picked})} of "
                f"{MIN_MATCHES} required matches; not relaxing the rule, fix the filter "
                "or the plan"
            )
            ok = False
        chosen[sport] = picked

    if not ok:
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    possessions_dir = out_dir / "possessions"
    possessions_dir.mkdir(parents=True, exist_ok=True)
    # A previous selection's files would otherwise ship, and count in stats.json.
    for stale in possessions_dir.glob("*.json"):
        stale.unlink()

    index_entries: list[dict[str, Any]] = []
    total_bytes = 0
    for sport in ("basketball", "football"):
        for candidate in chosen[sport]:
            payload = build_payload(con, candidate)
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            filename = safe_filename(candidate.possession_id)
            path = possessions_dir / filename
            path.write_text(text, encoding="utf-8", newline="\n")
            size = path.stat().st_size
            total_bytes += size
            status = "OK" if size < MAX_BYTES else "FAIL"
            print(f"publish possessions: {filename} {size} bytes ({status} < {MAX_BYTES})")
            if size >= MAX_BYTES:
                ok = False
            index_entries.append(
                {
                    "possession_id": candidate.possession_id,
                    "sport": sport,
                    "match_id": candidate.match_id,
                    "home": payload["match"]["home"],
                    "away": payload["match"]["away"],
                    # What the replay plays: first to last published frame.
                    "duration_s": round(
                        (payload["frames"][-1]["t"] - payload["frames"][0]["t"]) / 1000, 1
                    ),
                    "sample_rate_hz": payload["sample_rate_hz"],
                    "file": f"possessions/{filename}",
                    "bytes": size,
                }
            )

    index = {"schema_version": SCHEMA_VERSION, "possessions": index_entries}
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"publish possessions: {len(index_entries)} files, {total_bytes} bytes total")
    return 0 if ok else 1
