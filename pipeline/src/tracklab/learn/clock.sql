-- Run it from a match folder of the public basketball bundle: DuckDB, one file, no other input.
-- Every stretch of at least 125 consecutive frames (5 s) in which the provider says the game clock
-- runs, the least-squares slope of the game clock (s) on the video's clock (s), and how many
-- one-frame steps of those stretches leave the game clock where it was.
WITH frame AS (
  SELECT period, frameIdx, wallClock / 1000 AS t, gameClock AS clock,
         frameIdx - row_number() OVER (PARTITION BY period ORDER BY frameIdx) AS run
  FROM read_json('114086_tracking_data.jsonl.gz', format = 'newline_delimited',
                 columns = {frameIdx: 'BIGINT', wallClock: 'BIGINT', gameClock: 'DOUBLE',
                            gameClockStopped: 'BOOLEAN', period: 'BIGINT'})
  WHERE NOT gameClockStopped AND gameClock IS NOT NULL
),
step AS (
  SELECT period, run, t, clock,
         clock = lag(clock) OVER (PARTITION BY period, run ORDER BY frameIdx) AS held
  FROM frame
),
segment AS (
  SELECT count(*) AS frames, regr_slope(clock, t) AS slope, count(*) FILTER (WHERE held) AS held
  FROM step GROUP BY period, run HAVING count(*) >= 125
)
SELECT count(*) AS segments, sum(frames) AS frames, sum(held) AS held,
       round(quantile_cont(slope, 0.5), 5) AS slope_median,
       round(quantile_cont(slope, 0.25), 5) AS slope_q1,
       round(quantile_cont(slope, 0.75), 5) AS slope_q3
FROM segment
