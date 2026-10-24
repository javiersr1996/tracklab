-- files: /data/learn/rebound.json
-- The ten players of the example rebound when the shot ends: position (m) and velocity (m/s),
-- with the model's reaction time (s), top speed (m/s) and the point the ball comes down at (m).
CREATE VIEW players AS
SELECT i, p.jersey, p.team, p.x, p.y, p.vx, p.vy, reaction_s, top_speed,
       target[1] AS target_x, target[2] AS target_y
FROM (
  SELECT generate_subscripts(example.players, 1) - 1 AS i, unnest(example.players) AS p,
         reaction_s, top_speed, example.target AS target
  FROM read_json('/data/learn/rebound.json')
);
-- Lesson 4 in this browser: every player's time to arrive (the velocity they carry for the
-- reaction time, then top speed the rest of the way), who arrives first and second, and who is
-- nearest.
WITH race AS (
  SELECT i, jersey,
         sqrt((target_x - x) ^ 2 + (target_y - y) ^ 2) AS dist,
         reaction_s + sqrt((target_x - x - vx * reaction_s) ^ 2
                           + (target_y - y - vy * reaction_s) ^ 2) / top_speed AS time
  FROM players
),
ranked AS (
  SELECT *, row_number() OVER (ORDER BY time, i) AS by_time,
         row_number() OVER (ORDER BY dist, i) AS by_dist
  FROM race
)
SELECT 'learn.ex_first_time' AS figure, round(time, 2)::VARCHAR AS value FROM ranked
WHERE by_time = 1
UNION ALL
SELECT 'learn.ex_second_time', round(time, 2)::VARCHAR FROM ranked WHERE by_time = 2
UNION ALL
SELECT 'learn.ex_near_time', round(time, 2)::VARCHAR FROM ranked WHERE by_dist = 1
UNION ALL
SELECT 'learn.ex_near_dist', round(dist, 2)::VARCHAR FROM ranked WHERE by_dist = 1
