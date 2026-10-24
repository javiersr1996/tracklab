-- files: /data/possessions/bb_possessions_possession-114099-1-41.json /data/learn/pass.json
-- The ball of the possession, one row per frame: the video's clock (ms) and x, y, z (m). Each
-- frame lists its entities as [index, x, y, z, flag]; the ball is the entity of kind 'ball'.
CREATE VIEW ball AS
SELECT f.t, o[2] AS x, o[3] AS y, o[4] AS z
FROM (
  SELECT f, unnest(f.o) AS o, ball
  FROM (
    SELECT unnest(frames) AS f, list_filter(entities, e -> e.kind = 'ball')[1].i AS ball
    FROM read_json('/data/possessions/bb_possessions_possession-114099-1-41.json')
  )
)
WHERE o[1] = ball;
-- The passes of the example, as pass.json lists them: first and last frame (ms) and the frames
-- between, numbered from zero.
CREATE VIEW passes AS
SELECT i, p.pass_id, p.t0, p.t1, p.frames
FROM (
  SELECT generate_subscripts(example.passes, 1) - 1 AS i, unnest(example.passes) AS p
  FROM read_json('/data/learn/pass.json')
);
-- Lesson 7 in this browser: each pass's chord (the ball's first position to its last), its path
-- (the sum of the ball's steps) and its chord speed, in metres and metres per second.
WITH step AS (
  SELECT t, sqrt((x - lag(x) OVER w) ^ 2 + (y - lag(y) OVER w) ^ 2 + (z - lag(z) OVER w) ^ 2) AS s
  FROM ball WINDOW w AS (ORDER BY t)
),
measured AS (
  SELECT i,
         (SELECT sum(s) FROM step WHERE step.t > t0 AND step.t <= t1) AS path,
         (SELECT sqrt((b.x - a.x) ^ 2 + (b.y - a.y) ^ 2 + (b.z - a.z) ^ 2)
          FROM ball a, ball b WHERE a.t = t0 AND b.t = t1) AS chord,
         frames / 25 AS seconds
  FROM passes
),
figures AS (
  SELECT 'learn.passes.' || i || '.chord_m' AS figure, round(chord, 2) AS value, i, 1 AS k FROM measured
  UNION ALL
  SELECT 'learn.passes.' || i || '.path_m', round(path, 2), i, 2 FROM measured
  UNION ALL
  SELECT 'learn.passes.' || i || '.chord_speed', round(chord / seconds, 2), i, 3 FROM measured
)
SELECT figure, regexp_replace(value::VARCHAR, '\.0$', '') AS value FROM figures ORDER BY i, k
