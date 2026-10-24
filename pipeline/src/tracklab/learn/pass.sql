-- Run it from a match folder of the public basketball bundle: DuckDB, two files, no other input.
-- Every complete pass that ends after it starts and has the ball at every frame of the way: the
-- ball's chord (from where it is at the start frame to where it is at the end frame) over the
-- pass's time, the ball's path over that chord, and the provider's `distance` over the same time.
-- Metres and seconds.
WITH pass AS (
  SELECT p.id, p.startFrame AS f0, p.endFrame AS f1, p.distance * 0.3048 AS d
  FROM (SELECT unnest(passes) AS p FROM read_json('114099_dynamic_events.json'))
  WHERE p.complete AND p.startFrame IS NOT NULL AND p.endFrame IS NOT NULL
    AND p.distance IS NOT NULL AND p.endFrame > p.startFrame
),
ball AS (
  SELECT frameIdx AS f, ball.xyz[1] * 0.3048 AS x, ball.xyz[2] * 0.3048 AS y, ball.xyz[3] * 0.3048 AS z
  FROM read_json('114099_tracking_data.jsonl.gz', format = 'newline_delimited',
                 columns = {frameIdx: 'BIGINT', ball: 'STRUCT(xyz DOUBLE[])'})
  WHERE ball.xyz IS NOT NULL
),
flight AS (
  SELECT pass.id, any_value(f1 - f0) / 25 AS s, any_value(d) AS d, count(*) AS rows,
         sum(sqrt((b.x - a.x) ^ 2 + (b.y - a.y) ^ 2 + (b.z - a.z) ^ 2)) FILTER (WHERE b.f > f0) AS path,
         any_value(sqrt((e.x - o.x) ^ 2 + (e.y - o.y) ^ 2 + (e.z - o.z) ^ 2)) AS chord
  FROM pass
  JOIN ball b ON b.f BETWEEN f0 AND f1
  LEFT JOIN ball a ON a.f = b.f - 1
  JOIN ball o ON o.f = f0
  JOIN ball e ON e.f = f1
  GROUP BY pass.id
  HAVING count(*) = any_value(f1 - f0) + 1
)
SELECT count(*) AS passes,
       round(quantile_cont(chord / s, 0.5), 2) AS chord_speed_median,
       round(quantile_cont(chord / s, 0.9), 2) AS chord_speed_p90,
       round(quantile_cont(path / chord, 0.5) FILTER (WHERE chord > 0), 4) AS path_over_chord,
       round(quantile_cont(d / s, 0.5), 2) AS distance_speed_median,
       round(quantile_cont(chord / d, 0.5) FILTER (WHERE d > 0), 4) AS chord_over_distance
FROM flight
