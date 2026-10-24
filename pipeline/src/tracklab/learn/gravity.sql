-- Run it from a match folder of the public basketball bundle: DuckDB, two files, no other input.
-- It returns the number of shots whose flight gave a usable parabola and the median g of them.
WITH shot AS (
  SELECT s.id, s.startFrame AS f0, coalesce(s.endFrame, s.startFrame + 25) AS f1
  FROM (SELECT unnest(shots) AS s FROM read_json('114086_dynamic_events.json'))
  WHERE s.startFrame IS NOT NULL AND NOT coalesce(s.blocked, false)
),
ball AS (
  SELECT frameIdx AS f, wallClock / 1000.0 AS t,
         ball.xyz[1] * 0.3048 AS x, ball.xyz[2] * 0.3048 AS y, ball.xyz[3] * 0.3048 AS z
  FROM read_json('114086_tracking_data.jsonl.gz', format = 'newline_delimited')
  WHERE len(ball.xyz) = 3
),
near AS (
  SELECT shot.id, ball.* FROM shot JOIN ball ON ball.f >= shot.f0 - 10 AND ball.f < shot.f1 + 20
),
apex AS (
  SELECT id, f AS fa, t AS ta FROM (
    SELECT id, f, t, row_number() OVER (PARTITION BY id ORDER BY z DESC, f) AS r FROM near
  ) WHERE r = 1
),
win AS (
  SELECT near.id, near.f - fa AS k, near.t - ta AS u, x, y, z
  FROM near JOIN apex USING (id) WHERE near.f BETWEEN fa - 10 AND fa + 10
),
ok AS (
  SELECT id FROM win GROUP BY id
  HAVING count(*) = 21 AND NOT bool_or(k > 0 AND (
    least(sqrt((x - (91.86 / 2 - 5.17) * 0.3048) ^ 2 + y * y), sqrt((x + (91.86 / 2 - 5.17) * 0.3048) ^ 2 + y * y)) < 2.5 * 0.3048
    OR z < 9.5 * 0.3048))
),
fit AS (
  SELECT id, sum((u * u - m) * z) / sum((u * u - m) ^ 2) AS a, sum(u * z) / sum(u * u) AS b, avg(z) AS zbar, m
  FROM win JOIN ok USING (id) JOIN (SELECT id, avg(u * u) AS m FROM win GROUP BY id) USING (id)
  GROUP BY id, m
),
flight AS (
  SELECT id, -2 * a AS g, sqrt(avg((z - (zbar - a * m + b * u + a * u * u)) ^ 2)) AS rms
  FROM win JOIN fit USING (id) GROUP BY id, a
)
SELECT count(*) AS flights, round(median(g), 4) AS g_median FROM flight WHERE rms < 0.3048
