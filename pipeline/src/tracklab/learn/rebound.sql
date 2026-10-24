-- Run it from a match folder of the public basketball bundle: DuckDB, two files, no other input.
-- For every rebound a player took after a missed shot, it freezes the ten players at the shot's
-- last frame and asks who reaches the rebounder's spot first: the nearest player, and the time to
-- arrive model (0.7 s of reaction carrying the player's velocity, then 5 m/s). Metres and seconds.
WITH rebound AS (
  SELECT r.id AS rebound, r.rebounderId AS rebounder, s.endFrame AS e,
         r.location[1] * 0.3048 AS tx, r.location[2] * 0.3048 AS ty
  FROM (SELECT unnest(rebounds) AS r FROM read_json('114086_dynamic_events.json')) AS rr
  JOIN (SELECT unnest(shots) AS s FROM read_json('114086_dynamic_events.json')) AS ss
    ON s.id = r.shotId
  WHERE r.rebounded AND r.rebounderId IS NOT NULL AND r.location IS NOT NULL AND r.frame > s.endFrame
),
sample AS (
  SELECT f, p.playerId AS player, p.xyz[1] * 0.3048 AS x, p.xyz[2] * 0.3048 AS y
  FROM (SELECT frameIdx AS f, unnest(list_concat(homePlayers, awayPlayers)) AS p
        FROM read_json('114086_tracking_data.jsonl.gz', format = 'newline_delimited'))
  WHERE f IN (SELECT e + k FROM rebound, range(-1, 2) AS t(k))
),
runner AS (
  SELECT r.rebound, r.rebounder, r.tx, r.ty, a.player, a.x, a.y,
         (n.x - b.x) / (2 / 25) AS vx, (n.y - b.y) / (2 / 25) AS vy
  FROM rebound r
  JOIN sample a ON a.f = r.e
  JOIN sample b ON b.f = r.e - 1 AND b.player = a.player
  JOIN sample n ON n.f = r.e + 1 AND n.player = a.player
),
on_court AS (
  SELECT r.rebound, count(*) AS players FROM rebound r JOIN sample s ON s.f = r.e GROUP BY r.rebound
),
race AS (
  SELECT rebound, any_value(rebounder) AS rebounder,
         arg_min(player, sqrt((tx - x) ^ 2 + (ty - y) ^ 2)) AS nearest,
         arg_min(player, 0.7 + sqrt((tx - x - 0.7 * vx) ^ 2 + (ty - y - 0.7 * vy) ^ 2) / 5) AS model
  FROM runner JOIN on_court USING (rebound)
  GROUP BY rebound
  HAVING count(*) = 10 AND any_value(players) = 10 AND count(*) FILTER (WHERE player = rebounder) = 1
)
SELECT count(*) AS rebounds, count(*) FILTER (WHERE model = rebounder) AS model_first,
       count(*) FILTER (WHERE nearest = rebounder) AS nearest_first
FROM race
