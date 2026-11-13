-- Run it with DuckDB from a folder that holds the two public SkillCorner repositories side by side,
-- opendata and opendata-basketball. Two results: no Pitch & Parquet code, no intermediate table.

-- 1. Football, one match: its phases of play, read through five columns only. A run is a
--    stretch of consecutive phases of one period with the same team in possession, from its first
--    frame to its last, at 10 frames per second; a phase with no team breaks it.
WITH phase AS (
  SELECT index, frame_start, frame_end, period, team_in_possession_id AS team
  FROM read_csv('opendata/data/matches/1874553/1874553_phases_of_play.csv')
),
marked AS (
  SELECT *, (team IS DISTINCT FROM lag(team) OVER w)::INT AS starts FROM phase
  WINDOW w AS (PARTITION BY period ORDER BY index)
),
numbered AS (
  SELECT *, sum(starts) OVER (PARTITION BY period ORDER BY index) AS run FROM marked
),
runs AS (
  SELECT period, run, count(*) AS phases, (max(frame_end) - min(frame_start)) / 10 AS s
  FROM numbered WHERE team IS NOT NULL GROUP BY period, run
)
SELECT (SELECT count(*) FROM phase) AS phases, count(*) AS runs,
       round(quantile_cont(s, 0.5), 4) AS run_median_s, round(quantile_cont(s, 0.9), 4) AS run_p90_s,
       round(100 * avg((phases > 1)::INT), 2) AS multi_phase_pct
FROM runs;

-- 2. Basketball, one match: every possession with a start and an end frame, at 25 frames per
--    second; then the same possessions on the game clock, which counts down, for those with a
--    clock at both ends.
SELECT count(*) AS possessions,
       round(quantile_cont(s, 0.5), 4) AS median_s, round(quantile_cont(s, 0.9), 4) AS p90_s,
       count(c) AS clock_possessions,
       round(quantile_cont(c, 0.5), 4) AS clock_median_s, round(quantile_cont(c, 0.9), 4) AS clock_p90_s
FROM (
  SELECT (p.endFrame - p.startFrame) / 25 AS s, p.startGameClock - p.endGameClock AS c
  FROM (SELECT unnest(possessions) AS p
        FROM read_json('opendata-basketball/data/matches/114086/114086_dynamic_events.json'))
  WHERE p.startFrame IS NOT NULL AND p.endFrame IS NOT NULL
);
