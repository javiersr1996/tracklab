-- Run it from a match folder of the public basketball bundle: DuckDB, two files, no other input.
-- The dribbles as points in time: the intervals between consecutive dribbles of one touch (s).
-- The dribbles against the ball's height: for every dribble with the ball at each frame from five
-- before to five after, the offset from the event to the lowest height in that window (frames,
-- ties to the earliest), and whether two consecutive dribbles of a touch share that lowest frame.
WITH dribble AS (
  SELECT d.id, d.touchId AS touch, d.frame
  FROM (SELECT unnest(dribbles) AS d FROM read_json('114086_dynamic_events.json'))
  WHERE d.frame IS NOT NULL
),
gap AS (
  SELECT (frame - lag(frame) OVER (PARTITION BY touch ORDER BY frame, id)) / 25 AS s
  FROM dribble WHERE touch IS NOT NULL
),
ball AS (
  SELECT frameIdx AS f, ball.xyz[3] * 0.3048 AS z
  FROM read_json('114086_tracking_data.jsonl.gz', format = 'newline_delimited',
                 columns = {frameIdx: 'BIGINT', ball: 'STRUCT(xyz DOUBLE[])'})
  WHERE ball.xyz[3] IS NOT NULL
),
low AS (
  SELECT dribble.id, arg_min(ball.f - frame, [ball.z, ball.f - frame]) AS k, min(ball.z) AS z
  FROM dribble JOIN ball ON ball.f BETWEEN frame - 5 AND frame + 5
  GROUP BY dribble.id
  HAVING count(*) = 11
),
pair AS (
  SELECT low.k IS NOT NULL AND lag(low.k IS NOT NULL) OVER w AS paired,
         frame + low.k = lag(frame + low.k) OVER w AS shared
  FROM dribble LEFT JOIN low USING (id)
  WHERE touch IS NOT NULL
  WINDOW w AS (PARTITION BY touch ORDER BY frame, id)
)
SELECT (SELECT count(*) FROM dribble) AS dribbles,
       (SELECT count(s) FROM gap) AS intervals,
       (SELECT round(quantile_cont(s, 0.5), 4) FROM gap) AS interval_median_s,
       (SELECT round(quantile_cont(s, 0.1), 4) FROM gap) AS interval_p10_s,
       (SELECT round(quantile_cont(s, 0.9), 4) FROM gap) AS interval_p90_s,
       (SELECT count(*) FROM (SELECT touch FROM dribble WHERE touch IS NOT NULL
                              GROUP BY touch HAVING count(*) >= 3)) AS touches_3,
       (SELECT count(*) FROM low) AS windows,
       (SELECT round(quantile_cont(k, 0.5), 4) FROM low) AS offset_median,
       (SELECT round(quantile_cont(abs(k), 0.5), 4) FROM low) AS offset_abs_median,
       (SELECT round(100 * avg((abs(k) <= 3)::INT), 2) FROM low) AS near_pct,
       (SELECT round(100 * avg((abs(k) = 5)::INT), 2) FROM low) AS edge_pct,
       (SELECT round(quantile_cont(z, 0.5), 3) FROM low) AS low_z_median,
       (SELECT count(*) FILTER (WHERE paired) FROM pair) AS pairs,
       (SELECT count(*) FILTER (WHERE paired AND shared) FROM pair) AS shared_low
