-- files: /data/possessions/bb_possessions_possession-114086-1-36.json /data/possessions/fb_possession_1874553_1.json
-- The video clock of the two possessions the home page plays, one row per frame: t in ms.
CREATE VIEW clocks AS
SELECT 'basketball' AS sport, sample_rate_hz, fr.t AS t_ms FROM (
  SELECT sample_rate_hz, unnest(frames) AS fr
  FROM read_json('/data/possessions/bb_possessions_possession-114086-1-36.json')
)
UNION ALL
SELECT 'football', sample_rate_hz, fr.t FROM (
  SELECT sample_rate_hz, unnest(frames) AS fr
  FROM read_json('/data/possessions/fb_possession_1874553_1.json')
);
-- Lesson 3 in this browser: each sport's step between frames, the first clock both share, how
-- many steps of each it takes, and the sample rate the steps give.
WITH dt AS (
  SELECT sport, t_ms - lag(t_ms) OVER (PARTITION BY sport ORDER BY t_ms) AS ms FROM clocks
),
step AS (SELECT sport, min(ms) AS ms FROM dt GROUP BY sport HAVING min(ms) = max(ms)),
bb AS (SELECT ms FROM step WHERE sport = 'basketball'),
fb AS (SELECT ms FROM step WHERE sport = 'football')
SELECT 'learn.step_bb_ms' AS figure, bb.ms::VARCHAR AS value FROM bb
UNION ALL
SELECT 'learn.step_fb_ms', fb.ms::VARCHAR FROM fb
UNION ALL
SELECT 'learn.shared_ms', lcm(bb.ms, fb.ms)::VARCHAR FROM bb, fb
UNION ALL
SELECT 'learn.every_bb', (lcm(bb.ms, fb.ms) // bb.ms)::VARCHAR FROM bb, fb
UNION ALL
SELECT 'learn.every_fb', (lcm(bb.ms, fb.ms) // fb.ms)::VARCHAR FROM bb, fb
UNION ALL
SELECT 'possession.bb_possessions_possession-114086-1-36.sample_rate_hz',
       (1000 // bb.ms)::VARCHAR FROM bb
UNION ALL
SELECT 'possession.fb_possession_1874553_1.sample_rate_hz', (1000 // fb.ms)::VARCHAR FROM fb
