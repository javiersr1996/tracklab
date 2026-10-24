-- files: /data/learn/entry.json
-- The example's flight, one row per sample from its start frame: the time silver keeps (the
-- frame's 40 ms steps, in seconds) and x, y, z (m); `r` numbers the run the check fits, from
-- `search_offset` frames after the release.
CREATE VIEW flight AS
SELECT i - search_offset AS r, ((example.start_frame + i) * 1000 // fps) / 1000 AS t,
       example.x[i + 1] AS x, example.y[i + 1] AS y, example.z[i + 1] AS z
FROM (
  SELECT unnest(range(len(example.x))) AS i, example, search_offset, fps
  FROM read_json('/data/learn/entry.json')
);
-- The check's constants and the rim's centre for this shot.
CREATE VIEW constants AS
SELECT g, rim_height, v_h_frames, tail_back, tail_min_index, fps, example.rim_x AS rim_x
FROM read_json('/data/learn/entry.json');
-- Lesson 8 in this browser: the check on the example. v_h is the median horizontal speed between
-- the run's first samples, T the time to the rim's centre at v_h, k the arrival sample, the
-- reported angle the slope of the last heights against v_h, the required one a projectile's.
WITH step AS (
  SELECT r, sqrt((x - lag(x) OVER w) ^ 2 + (y - lag(y) OVER w) ^ 2) / (t - lag(t) OVER w) AS speed
  FROM flight WHERE r >= 0 WINDOW w AS (ORDER BY r)
),
run AS (
  SELECT (SELECT median(speed) FROM step, constants WHERE r BETWEEN 1 AND v_h_frames - 1) AS v_h,
         (SELECT sqrt((rim_x - x) ^ 2 + y ^ 2) FROM flight, constants WHERE r = 0) AS d,
         (SELECT z FROM flight WHERE r = 0) AS z0
),
arrival AS (SELECT v_h, d, z0, d / v_h AS t_flight, round(d / v_h * fps)::INTEGER AS k FROM run, constants),
angles AS (
  SELECT k, v_h,
         degrees(atan2(abs((SELECT regr_slope(z, t) FROM flight
                            WHERE r BETWEEN greatest(k - tail_back, tail_min_index) AND k)), v_h)) AS reported,
         degrees(atan2(abs((rim_height - z0 + 0.5 * g * t_flight ^ 2) / t_flight - g * t_flight), v_h)) AS required
  FROM arrival, constants
)
SELECT 'learn.ex_v_h' AS figure, round(v_h, 2)::VARCHAR AS value FROM angles
UNION ALL
SELECT 'learn.ex_k', k::VARCHAR FROM angles
UNION ALL
SELECT 'learn.ex_reported', round(reported, 4)::VARCHAR FROM angles
UNION ALL
SELECT 'learn.ex_required', round(required, 4)::VARCHAR FROM angles
