"""Placebo candidates of an off-ball run, counted and nothing more (task 47).

The placebo of a run is the same runner at another instant of a possession of his team
(decision 2 of P5): a `player_possession` of a teammate, in another team phase, with the same
`team_in_possession_phase_type`, taken at the same offset from that possession's start as
the run had from its own (the offset is often negative: the run starts while the pass is in
the air) and inside that phase's window, so the team still has the ball. An instant is
admissible when no run overlaps the three seconds either side of it: the runner's own runs
(`runner_*`) or every run of his team (`team_*`). The plan left the second rule open, so both
are counted side by side on the calibration half, and the protocol chooses with these
coverage counts and never with an outcome. The literal reading of the plan ("no run of his
starting within 3 s", `*_start`) is counted too, so the move to overlap stays visible.

Only `dynamic_events` and `phases_of_play` are read: no tracking, no displacement, no effect.
Whether the runner is on the pitch and detected at the placebo instant is task 48's, against
the tracking, so these counts bound task 48's from above.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import duckdb

SAMPLE_RATE_HZ = 10
EXCLUSION_S = 3.0
EXCLUSION_FRAMES = int(EXCLUSION_S * SAMPLE_RATE_HZ)


@dataclass(frozen=True)
class PlaceboCount:
    """Runs of one match and how many keep at least one admissible placebo under each rule."""

    match_id: int
    runs: int
    runs_without_possession: int
    with_candidate: int
    runner_overlap: int
    team_overlap: int
    runner_start: int
    team_start: int


COLUMNS = tuple(f.name for f in fields(PlaceboCount))

_SQL = """
WITH ev AS (
    SELECT match_id, event_id, event_type, player_id, team_id, frame_start, frame_end,
           phase_index, team_in_possession_phase_type AS phase_type,
           associated_player_possession_frame_start AS pp_frame_start
    FROM read_parquet($events)
    WHERE match_id IN (SELECT unnest($matches))
),
runs AS (SELECT * FROM ev WHERE event_type = 'off_ball_run'),
phases AS (
    SELECT match_id, "index" AS phase_index, frame_start AS phase_frame_start,
           frame_end AS phase_frame_end
    FROM read_parquet($phases)
    WHERE match_id IN (SELECT unnest($matches))
),
poss AS (
    SELECT e.match_id, e.player_id, e.team_id, e.frame_start, e.phase_index, e.phase_type,
           ph.phase_frame_start, ph.phase_frame_end
    FROM ev e
    JOIN phases ph USING (match_id, phase_index)
    WHERE e.event_type = 'player_possession'
),
cand AS (
    SELECT r.match_id, r.event_id AS run_id, r.player_id, r.team_id,
           c.frame_start + (r.frame_start - r.pp_frame_start) AS t_placebo
    FROM runs r
    JOIN poss c
      ON c.match_id = r.match_id AND c.team_id = r.team_id AND c.phase_type = r.phase_type
     AND c.phase_index <> r.phase_index AND c.player_id <> r.player_id
    WHERE r.pp_frame_start IS NOT NULL
      AND c.frame_start + (r.frame_start - r.pp_frame_start)
          BETWEEN c.phase_frame_start AND c.phase_frame_end
),
judged AS (
    SELECT cand.*,
        NOT EXISTS (
            SELECT 1 FROM runs x
            WHERE x.match_id = cand.match_id AND x.player_id = cand.player_id
              AND x.frame_start <= cand.t_placebo + $margin
              AND x.frame_end >= cand.t_placebo - $margin
        ) AS runner_overlap,
        NOT EXISTS (
            SELECT 1 FROM runs x
            WHERE x.match_id = cand.match_id AND x.team_id = cand.team_id
              AND x.frame_start <= cand.t_placebo + $margin
              AND x.frame_end >= cand.t_placebo - $margin
        ) AS team_overlap,
        NOT EXISTS (
            SELECT 1 FROM runs x
            WHERE x.match_id = cand.match_id AND x.player_id = cand.player_id
              AND abs(x.frame_start - cand.t_placebo) <= $margin
        ) AS runner_start,
        NOT EXISTS (
            SELECT 1 FROM runs x
            WHERE x.match_id = cand.match_id AND x.team_id = cand.team_id
              AND abs(x.frame_start - cand.t_placebo) <= $margin
        ) AS team_start
    FROM cand
),
per_run AS (
    SELECT match_id, run_id,
           bool_or(runner_overlap) AS runner_overlap, bool_or(team_overlap) AS team_overlap,
           bool_or(runner_start) AS runner_start, bool_or(team_start) AS team_start
    FROM judged
    GROUP BY ALL
)
SELECT r.match_id,
       count(*) AS runs,
       count(*) FILTER (WHERE r.pp_frame_start IS NULL) AS runs_without_possession,
       count(p.run_id) AS with_candidate,
       count(*) FILTER (WHERE p.runner_overlap) AS runner_overlap,
       count(*) FILTER (WHERE p.team_overlap) AS team_overlap,
       count(*) FILTER (WHERE p.runner_start) AS runner_start,
       count(*) FILTER (WHERE p.team_start) AS team_start
FROM runs r
LEFT JOIN per_run p ON p.match_id = r.match_id AND p.run_id = r.event_id
GROUP BY ALL
ORDER BY r.match_id
"""


def placebo_counts(data_dir: Path, match_ids: Sequence[int]) -> list[PlaceboCount]:
    """One row per match of `match_ids`, in id order, from the football bronze under `data_dir`.
    A match with no `dynamic_events` file yields no row: the caller decides whether that is an
    error (the protocol does, for the calibration half)."""
    football = data_dir / "bronze" / "football"
    con = duckdb.connect()
    try:
        rows = con.execute(
            _SQL,
            {
                "events": (football / "dynamic_events" / "*.parquet").as_posix(),
                "phases": (football / "phases_of_play" / "*.parquet").as_posix(),
                "matches": list(match_ids),
                "margin": EXCLUSION_FRAMES,
            },
        ).fetchall()
    finally:
        con.close()
    return [PlaceboCount(*(int(v) for v in row)) for row in rows]


def total(counts: Sequence[PlaceboCount]) -> dict[str, int]:
    """The column sums over the matches, `match_id` replaced by how many there were."""
    out = {name: sum(getattr(c, name) for c in counts) for name in COLUMNS if name != "match_id"}
    return {"matches": len(counts), **out}


def as_rows(counts: Sequence[PlaceboCount]) -> list[dict[str, int]]:
    return [asdict(c) for c in counts]
