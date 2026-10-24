-- files: /data/possessions/bb_possessions_possession-114086-1-36.json /data/learn/dribble.json
-- The ball's height in the possession, one row per frame: the video's clock (ms) and z (m). Each
-- frame lists its entities as [index, x, y, z, flag]; the ball is the entity of kind 'ball'.
CREATE VIEW ball AS
SELECT f.t, o[4] AS z
FROM (
  SELECT f, unnest(f.o) AS o, ball
  FROM (
    SELECT unnest(frames) AS f, list_filter(entities, e -> e.kind = 'ball')[1].i AS ball
    FROM read_json('/data/possessions/bb_possessions_possession-114086-1-36.json')
  )
)
WHERE o[1] = ball AND o[4] IS NOT NULL;
-- The dribbles of the example's touch, as dribble.json lists them: the video's clock (ms),
-- numbered from zero.
CREATE VIEW dribbles AS
SELECT i, d.t
FROM (
  SELECT generate_subscripts(example.dribbles, 1) - 1 AS i, unnest(example.dribbles) AS d
  FROM read_json('/data/learn/dribble.json')
);
-- Lesson 9 in this browser: for each dribble, the offset in frames from the event to the ball's
-- lowest height within five frames either side (ties to the earliest) and that height; then the
-- median interval between the touch's dribbles, in seconds.
WITH near AS (
  SELECT i, (ball.t - dribbles.t) // 40 AS k, ball.z
  FROM dribbles JOIN ball ON ball.t BETWEEN dribbles.t - 200 AND dribbles.t + 200
),
low AS (
  SELECT i, arg_min(k, [z, k]) AS k, min(z) AS z FROM near GROUP BY i HAVING count(*) = 11
),
gap AS (SELECT (t - lag(t) OVER (ORDER BY t)) / 1000 AS s FROM dribbles),
figures AS (
  SELECT 'learn.dribbles.' || i || '.offset' AS figure, k::VARCHAR AS value, i, 1 AS n FROM low
  UNION ALL
  SELECT 'learn.dribbles.' || i || '.low_z', regexp_replace(round(z, 2)::VARCHAR, '\.0$', ''), i, 2
  FROM low
  UNION ALL
  SELECT 'learn.ex_median_s', regexp_replace(round(median(s), 2)::VARCHAR, '\.0$', ''), 1000, 1
  FROM gap
)
SELECT figure, value FROM figures ORDER BY i, n
