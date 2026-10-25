-- files: /data/pose/hook_1925299.json
-- The clip /pose publishes for 1925299: its frame rate, the player its window names, and where
-- the nose and the two shoulders sit in the list of joints.
CREATE VIEW clip AS
SELECT fps, windows[1].player AS hook,
       list_position(joints, 'nose') - 1 AS nose_i,
       list_position(joints, 'lShoulder') - 1 AS l_i,
       list_position(joints, 'rShoulder') - 1 AS r_i,
       frames
FROM read_json('/data/pose/hook_1925299.json',
               columns = {fps: 'INTEGER', joints: 'VARCHAR[]', windows: 'STRUCT(player INTEGER)[]',
                          frames: 'STRUCT(f INTEGER, p JSON[])[]'});
-- The hook player's row of every frame: x and y (cm) and the three joints as [dx, dy, dz] in cm
-- from the player's own x, y (null where the frame has no skeleton for the player).
CREATE VIEW hook_rows AS
SELECT fps, f, (p ->> '$[0]')::INTEGER AS i, (p ->> '$[1]')::INTEGER AS x, (p ->> '$[2]')::INTEGER AS y,
       json_extract(p, '$[4][0][' || nose_i || ']')::DOUBLE[] AS nose,
       json_extract(p, '$[4][0][' || l_i || ']')::DOUBLE[] AS l,
       json_extract(p, '$[4][0][' || r_i || ']')::DOUBLE[] AS r
FROM (SELECT fps, hook, nose_i, l_i, r_i, fr.f AS f, unnest(fr.p) AS p
      FROM (SELECT fps, hook, nose_i, l_i, r_i, unnest(frames) AS fr FROM clip))
WHERE i = hook;
-- Lesson 11 in this browser: for every frame of the hook player with a position in the frame
-- before and the frame after, both shoulders and the nose off their line, and a speed over
-- 2 m/s, the facing (the normal to the shoulder line on the nose's side), the heading (the
-- central difference of x, y), both in (−180, 180], and their difference; then the first such frame,
-- the median of |relative|, the circular mean, the mean resultant length, the circular variance
-- and the shares side on or further and with the back to the travel.
WITH q AS (
  SELECT f, fps, nose, l, r, lag(f) OVER w AS f0, lead(f) OVER w AS f1,
         lag(x) OVER w AS x0, lead(x) OVER w AS x1, lag(y) OVER w AS y0, lead(y) OVER w AS y1
  FROM hook_rows WINDOW w AS (ORDER BY f)
),
g AS (
  SELECT f, sqrt((x1 - x0) ^ 2 + (y1 - y0) ^ 2) / 100 * fps / 2 AS speed,
         degrees(atan2(y1 - y0, x1 - x0)) AS heading,
         l[1] - r[1] AS sx, l[2] - r[2] AS sy,
         nose[1] - (l[1] + r[1]) / 2 AS nx, nose[2] - (l[2] + r[2]) / 2 AS ny
  FROM q WHERE f0 = f - 1 AND f1 = f + 1 AND nose IS NOT NULL AND l IS NOT NULL AND r IS NOT NULL
),
h AS (
  SELECT f, speed, heading,
         180 - ((((180 - degrees(CASE WHEN sy * nx - sx * ny > 0 THEN atan2(-sx, sy) ELSE atan2(sx, -sy) END))
                  % 360) + 360) % 360) AS facing
  FROM g WHERE sy * nx - sx * ny <> 0 AND speed > 2
),
rel AS (
  SELECT f, speed, facing, heading, 180 - ((((180 - (facing - heading)) % 360) + 360) % 360) AS relative
  FROM h
),
first AS (SELECT * FROM rel ORDER BY f LIMIT 1),
circ AS (SELECT avg(sin(radians(relative))) AS s, avg(cos(radians(relative))) AS c FROM rel),
figures AS (
  SELECT 'learn.hook.1925299.frames' AS figure, count(*)::VARCHAR AS value, 1 AS k FROM rel
  UNION ALL SELECT 'learn.hook.1925299.first_frame_id', f::VARCHAR, 2 FROM first
  UNION ALL SELECT 'learn.hook.1925299.first_facing', round(facing, 3)::VARCHAR, 3 FROM first
  UNION ALL SELECT 'learn.hook.1925299.first_heading', round(heading, 3)::VARCHAR, 4 FROM first
  UNION ALL SELECT 'learn.hook.1925299.first_relative', round(relative, 3)::VARCHAR, 5 FROM first
  UNION ALL SELECT 'learn.hook.1925299.median_abs', round(median(abs(relative)), 3)::VARCHAR, 6 FROM rel
  UNION ALL SELECT 'learn.hook.1925299.circ_mean', round(degrees(atan2(s, c)), 3)::VARCHAR, 7 FROM circ
  UNION ALL SELECT 'learn.hook.1925299.resultant', round(sqrt(s * s + c * c), 3)::VARCHAR, 8 FROM circ
  UNION ALL SELECT 'learn.hook.1925299.circ_var', round(1 - sqrt(s * s + c * c), 3)::VARCHAR, 9 FROM circ
  UNION ALL SELECT 'learn.hook.1925299.off_pct', round(100 * avg((abs(relative) > 45)::INTEGER), 1)::VARCHAR, 10 FROM rel
  UNION ALL SELECT 'learn.hook.1925299.back_pct', round(100 * avg((abs(relative) > 135)::INTEGER), 1)::VARCHAR, 11 FROM rel
)
SELECT figure, regexp_replace(regexp_replace(value, '\.0$', ''), '^-0$', '0') AS value FROM figures ORDER BY k
