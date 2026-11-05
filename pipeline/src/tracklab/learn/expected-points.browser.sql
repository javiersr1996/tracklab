-- files: /data/euroleague/expected-points.json
-- The league's counts, one row per season and zone class: attempts, makes and points.
CREATE VIEW league AS
WITH b AS (SELECT unnest(seasons) AS s FROM read_json('/data/euroleague/expected-points.json'))
SELECT s.season AS season, 'rim' AS zone, s.league.rim.n AS n, s.league.rim.made AS made, s.league.rim.pts AS pts FROM b
UNION ALL SELECT s.season, 'mid', s.league.mid.n, s.league.mid.made, s.league.mid.pts FROM b
UNION ALL SELECT s.season, 'three', s.league.three.n, s.league.three.made, s.league.three.pts FROM b;
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
-- points per shot, expected points per shot, mix and making.
WITH e AS (SELECT season, zone, pts / n AS e FROM league),
mean AS (SELECT season, sum(pts) / sum(n) AS mean, avg(pts / n) AS plain FROM league GROUP BY season),
split AS (
  SELECT t.season, t.code, sum(t.pts) / sum(t.n) AS pps, sum(t.n * e.e) / sum(t.n) AS xpps
  FROM teams t JOIN e ON t.season = e.season AND t.zone = e.zone
  GROUP BY t.season, t.code
),
r AS (SELECT split.*, mean.mean FROM split JOIN mean ON split.season = mean.season),
figures AS (
  SELECT 'xp.' || season || '.pps.' || zone AS figure, round(e, 3) AS v, 1 AS k FROM e
  UNION ALL SELECT 'xp.' || season || '.mean', round(mean, 3), 2 FROM mean
  UNION ALL SELECT 'learn.season.' || season || '.plain', round(plain, 3), 3 FROM mean
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.pps', round(pps, 3), 4 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.xpps', round(xpps, 3), 5 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.mix', round(xpps - mean, 3), 6 FROM r
  UNION ALL SELECT 'xp.' || season || '.teams.' || code || '.making', round(pps - xpps, 3), 7 FROM r
)
SELECT figure, regexp_replace(regexp_replace(v::VARCHAR, '\.0$', ''), '^-0$', '0') AS value
FROM figures
ORDER BY k, figure
