-- Run it from a match folder of the public basketball bundle: DuckDB, one file, no other input.
-- For every player sample whose frames just before and just after are in the file, it puts the
-- provider's speed next to the central difference of the positions, both in m/s.
WITH frame AS (
  SELECT frameIdx AS f, list_concat(homePlayers, awayPlayers) AS players
  FROM read_json('114099_tracking_data.jsonl.gz', format = 'newline_delimited')
),
sample AS (
  SELECT f, p.playerId AS id, p.xyz[1] * 0.3048 AS x, p.xyz[2] * 0.3048 AS y, p.speed * 0.3048 AS speed
  FROM (SELECT f, unnest(players) AS p FROM frame)
),
around AS (
  SELECT f, speed,
         lag(f) OVER w AS f_before, lead(f) OVER w AS f_after,
         lag(x) OVER w AS x_before, lead(x) OVER w AS x_after,
         lag(y) OVER w AS y_before, lead(y) OVER w AS y_after
  FROM sample WINDOW w AS (PARTITION BY id ORDER BY f)
),
triple AS (
  SELECT speed, sqrt((x_after - x_before) ^ 2 + (y_after - y_before) ^ 2) / (2 / 25) AS central
  FROM around WHERE f_before = f - 1 AND f_after = f + 1
)
SELECT count(*) AS triples, round(corr(speed, central), 5) AS r,
       round(median(abs(speed - central)), 4) AS median_gap
FROM triple
