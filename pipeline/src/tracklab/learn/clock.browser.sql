-- files: /data/possessions/bb_possessions_possession-114086-1-36.json /data/possessions/bb_possessions_possession-184439-2-38.json /data/learn/clock.json
-- The two possessions of the figure, one row per frame: the video's clock (s) and the game clock
-- (s), with the frame's place in its possession.
CREATE VIEW clock AS
SELECT 'calibration' AS example, i, f.t / 1000 AS t, f.clock
FROM (
  SELECT generate_subscripts(frames, 1) - 1 AS i, unnest(frames) AS f
  FROM read_json('/data/possessions/bb_possessions_possession-114086-1-36.json')
)
UNION ALL
SELECT 'control', i, f.t / 1000, f.clock
FROM (
  SELECT generate_subscripts(frames, 1) - 1 AS i, unnest(frames) AS f
  FROM read_json('/data/possessions/bb_possessions_possession-184439-2-38.json')
);
-- The figures of clock.json, one row per match.
CREATE VIEW matches AS
SELECT m.match_id, m.calibration, m.segments, m.held, m.steps, m.slope_median
FROM (SELECT unnest(matches) AS m FROM read_json('/data/learn/clock.json'));
-- Lesson 6 in this browser: the least-squares slope of each possession over all its frames, the
-- control's from its first move (the last frame before its clock leaves the value it holds at
-- the start), and the range of the median slopes of each kind of match. A whole number is printed
-- without its decimal point, as the page prints it.
WITH held AS (
  SELECT i, clock = lag(clock) OVER (ORDER BY i) AS same FROM clock WHERE example = 'control'
),
move AS (SELECT min(i) - 1 AS i FROM held WHERE NOT same),
figures AS (
  SELECT 'learn.cal_slope' AS figure, round(regr_slope(clock, t), 5) AS value
  FROM clock WHERE example = 'calibration'
  UNION ALL
  SELECT 'learn.ctl_slope_all', round(regr_slope(clock, t), 5) FROM clock WHERE example = 'control'
  UNION ALL
  SELECT 'learn.ctl_slope_move', round(regr_slope(clock, t), 5)
  FROM clock WHERE example = 'control' AND i >= (SELECT i FROM move)
  UNION ALL
  SELECT 'learn.cal_lo', min(slope_median) FROM matches WHERE calibration
  UNION ALL
  SELECT 'learn.cal_hi', max(slope_median) FROM matches WHERE calibration
  UNION ALL
  SELECT 'learn.ctl_lo', min(slope_median) FROM matches WHERE NOT calibration
  UNION ALL
  SELECT 'learn.ctl_hi', max(slope_median) FROM matches WHERE NOT calibration
)
SELECT figure, regexp_replace(value::VARCHAR, '\.0$', '') AS value FROM figures
