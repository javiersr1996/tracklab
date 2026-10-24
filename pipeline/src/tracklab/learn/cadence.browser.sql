-- files: /data/pose/hook_1925299.json
-- The hook window of 1925299: s, the two ankles apart along the player's run, one row per sample
-- (m; published in mm), and the clip's frame rate.
CREATE VIEW hook_window AS
SELECT generate_subscripts(windows[1].s_mm, 1) - 1 AS i, unnest(windows[1].s_mm) / 1000 AS s_m, fps
FROM read_json('/data/pose/hook_1925299.json',
               columns = {fps: 'INTEGER', windows: 'STRUCT(s_mm INTEGER[])[]'});
-- Lesson 5 in this browser: the autocorrelation of s (each lag averaged over its own products),
-- the first lag where it turns negative, the first peak after it, and the cadence the peak gives
-- with the parabola through its two neighbours.
WITH c AS (SELECT i, s_m - avg(s_m) OVER () AS s FROM hook_window),
r AS (
  SELECT b.i - a.i AS k, sum(a.s * b.s) / count(*) AS r
  FROM c a JOIN c b ON b.i >= a.i GROUP BY k
),
nb AS (
  SELECT k, r, lag(r) OVER (ORDER BY k) AS r_before, lead(r) OVER (ORDER BY k) AS r_after FROM r
),
neg AS (SELECT min(k) AS k FROM r WHERE r < 0),
peak AS (
  SELECT k, r / (SELECT r FROM r WHERE k = 0) AS ratio,
         CASE WHEN r_before - 2 * r + r_after < 0
              THEN 0.5 * (r_before - r_after) / (r_before - 2 * r + r_after) ELSE 0 END AS shift
  FROM nb WHERE k > (SELECT k FROM neg) AND r > 0 AND r > r_before AND r >= r_after
  ORDER BY k LIMIT 1
)
SELECT 'learn.hook.1925299.first_negative' AS figure, k::VARCHAR AS value FROM neg
UNION ALL
SELECT 'learn.hook.1925299.peak_k', k::VARCHAR FROM peak
UNION ALL
SELECT 'learn.hook.1925299.peak_ratio', round(ratio, 3)::VARCHAR FROM peak
UNION ALL
SELECT 'learn.hook.1925299.cadence',
       round(2 * (SELECT any_value(fps) FROM hook_window) / (k + shift), 4)::VARCHAR FROM peak
