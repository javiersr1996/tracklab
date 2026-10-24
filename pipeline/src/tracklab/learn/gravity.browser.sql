-- files: /data/quality.json
-- The hook's 21 samples around its apex, as quality.json publishes them: t in s, z in m.
CREATE VIEW hook AS
SELECT unnest(hook.t_s) AS t_s, unnest(hook.z_data_m) AS z_m, hook.g_real AS g_real
FROM read_json('/data/quality.json');
-- P3's gravity check, one row per basketball match and metric.
CREATE VIEW gravity AS
SELECT r.match_id, r.metric, r.value
FROM (SELECT unnest(checks.gravity) AS r FROM read_json('/data/quality.json'))
WHERE r.sport = 'basketball';
-- Lesson 1 in this browser: the hook's g by the closed form of a window symmetric in time, and
-- the ten matches' medians and upper quartiles against the conventional g.
WITH c AS (SELECT t_s - avg(t_s) OVER () AS u, z_m FROM hook),
m AS (SELECT avg(u * u) AS m FROM c),
fit AS (SELECT -2 * sum((u * u - m) * z_m) / sum((u * u - m) ^ 2) AS g FROM c, m),
g_real AS (SELECT any_value(g_real) AS g FROM hook),
calibration AS (SELECT match_id, value = 1 AS cal FROM gravity WHERE metric = 'is_calibration'),
medians AS (
  SELECT match_id, value AS g, cal FROM gravity JOIN calibration USING (match_id)
  WHERE metric = 'g_median'
)
SELECT 'learn.fit_g' AS figure, round(g, 5)::VARCHAR AS value FROM fit
UNION ALL
SELECT 'learn.medians_below', count(*)::VARCHAR FROM medians WHERE g < (SELECT g FROM g_real)
UNION ALL
SELECT 'learn.q3_below', count(*)::VARCHAR FROM gravity
WHERE metric = 'g_q3' AND value < (SELECT g FROM g_real)
UNION ALL
SELECT 'summary.ranges.gravity_g_calibration', printf('%.2f to %.2f', min(g), max(g))
FROM medians WHERE cal
UNION ALL
SELECT 'summary.ranges.gravity_g_control', printf('%.2f to %.2f', min(g), max(g))
FROM medians WHERE NOT cal
