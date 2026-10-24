-- files: /data/learn/speed.json /data/possessions/bb_possessions_possession-114099-1-41.json
-- The example player's published track, one row per frame of the possession: x, y in m.
CREATE VIEW track AS
WITH p AS (SELECT * FROM read_json('/data/possessions/bb_possessions_possession-114099-1-41.json')),
player AS (SELECT e.i FROM (SELECT unnest(entities) AS e FROM p) WHERE e.entity_id = 'bb:59191'),
objects AS (
  SELECT k - 1 AS frame, unnest(fr.o) AS o
  FROM (SELECT unnest(frames) AS fr, generate_subscripts(frames, 1) AS k FROM p)
)
SELECT frame, o[2] AS x, o[3] AS y FROM objects, player WHERE o[1] = player.i;
-- The provider's speed of the same player at the same frames (m/s), and the frame rate.
CREATE VIEW provider AS
SELECT generate_subscripts(example.speed, 1) - 1 AS frame, unnest(example.speed) AS speed, fps
FROM read_json('/data/learn/speed.json');
-- Lesson 2 in this browser: the central difference of the published track against the
-- provider's speed, frame by frame, and the median of their gap.
WITH d AS (
  SELECT frame, speed,
         sqrt(((lead(x) OVER w - lag(x) OVER w) * fps / 2) ^ 2
              + ((lead(y) OVER w - lag(y) OVER w) * fps / 2) ^ 2) AS central
  FROM track JOIN provider USING (frame)
  WINDOW w AS (ORDER BY frame)
)
SELECT 'learn.frames' AS figure, count(*)::VARCHAR AS value FROM d
UNION ALL
SELECT 'learn.peak', round(max(speed), 2)::VARCHAR FROM d
UNION ALL
SELECT 'learn.ex_central_frames', count(central)::VARCHAR FROM d
UNION ALL
SELECT 'learn.ex_central_median', round(median(abs(speed - central)), 4)::VARCHAR FROM d
