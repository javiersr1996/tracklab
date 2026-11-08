-- files: /data/euroleague/expected-points.json
-- The league's counts, one row per season and zone class: attempts, makes and points.
CREATE VIEW league AS
WITH b AS (SELECT unnest(seasons) AS s FROM read_json('/data/euroleague/expected-points.json'))
SELECT s.season AS season, 'rim' AS zone, s.league.rim.n AS n, s.league.rim.made AS made, s.league.rim.pts AS pts FROM b
UNION ALL SELECT s.season, 'mid', s.league.mid.n, s.league.mid.made, s.league.mid.pts FROM b
UNION ALL SELECT s.season, 'three', s.league.three.n, s.league.three.made, s.league.three.pts FROM b;
-- The z of the intervals, as the file gives it.
CREATE VIEW params AS
SELECT z FROM read_json('/data/euroleague/expected-points.json');
-- Each team's counts, the same way, with its code.
CREATE VIEW teams AS
WITH b AS (
  SELECT s.season AS season, unnest(s.teams) AS t
  FROM (SELECT unnest(seasons) AS s FROM read_json('/data/euroleague/expected-points.json'))
)
SELECT season, t.code AS code, 'rim' AS zone, t.rim.n AS n, t.rim.made AS made, t.rim.pts AS pts FROM b
UNION ALL SELECT season, t.code, 'mid', t.mid.n, t.mid.made, t.mid.pts FROM b
UNION ALL SELECT season, t.code, 'three', t.three.n, t.three.made, t.three.pts FROM b;
-- Lesson 12 in this browser: from the counts alone, each class's points per attempt, the league's
-- points per shot (weighted by attempts) and the plain mean of its classes, and every team's
-- points per shot, expected points per shot, mix and making, and the bounds of their intervals
-- (each part plus and minus z standard errors: the spread of what one attempt adds to it, from the
-- counts by class, over the square root of the attempts).
WITH e AS (SELECT season, zone, pts / n AS e, CASE zone WHEN 'three' THEN 3 ELSE 2 END AS v FROM league),
mean AS (SELECT season, sum(pts) / sum(n) AS mean, avg(pts / n) AS plain FROM league GROUP BY season),
split AS (
  SELECT t.season, t.code, sum(t.n) AS n, sum(t.pts) / sum(t.n) AS pps, sum(t.n * e.e) / sum(t.n) AS xpps,
         sum(t.n * e.e * e.e) / sum(t.n) AS mix_sq,
         sum(e.v * t.pts - 2 * e.e * t.pts + t.n * e.e * e.e) / sum(t.n) AS making_sq
  FROM teams t JOIN e ON t.season = e.season AND t.zone = e.zone
  GROUP BY t.season, t.code
),
r AS (SELECT split.*, mean.mean FROM split JOIN mean ON split.season = mean.season),
ci AS (
  SELECT season, code, xpps - mean AS mix, pps - xpps AS making, params.z AS z,
         sqrt((mix_sq - xpps * xpps) / n) AS se_mix,
         sqrt((making_sq - (pps - xpps) * (pps - xpps)) / n) AS se_making
  FROM r, params
),
figures AS (
  SELECT 'xp.' || season || '.pps.' || zone AS figure, round(e, 3) AS v, 1 AS k FROM e
  UNION ALL SELECT 'xp.' || season || '.mean', round(mean, 3), 2 FROM mean
  UNION ALL SELECT 'learn.season.' || season || '.plain', round(plain, 3), 3 FROM mean
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.pps', round(pps, 3), 4 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.xpps', round(xpps, 3), 5 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.mix', round(xpps - mean, 3), 6 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.making', round(pps - xpps, 3), 7 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.mix_ci.0', round(mix - z * se_mix, 3), 8 FROM ci
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.mix_ci.1', round(mix + z * se_mix, 3), 9 FROM ci
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.making_ci.0', round(making - z * se_making, 3), 10 FROM ci
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.making_ci.1', round(making + z * se_making, 3), 11 FROM ci
)
SELECT figure, regexp_replace(regexp_replace(v::VARCHAR, '\.0$', ''), '^-0$', '0') AS value
FROM figures
ORDER BY k, figure
