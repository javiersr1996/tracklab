-- Lesson 12: every row of the per-team tables, from expected-points.json alone, the counts by zone
-- class the site publishes. Save the file next to this query first.
WITH seasons AS (
  SELECT unnest(seasons) AS s FROM read_json('expected-points.json')
),
-- The league's attempts and points in each zone class, one row per season and class.
league AS (
  SELECT s.season AS season, 'rim' AS zone, s.league.rim.n AS n, s.league.rim.pts AS pts FROM seasons
  UNION ALL SELECT s.season, 'mid', s.league.mid.n, s.league.mid.pts FROM seasons
  UNION ALL SELECT s.season, 'three', s.league.three.n, s.league.three.pts FROM seasons
),
-- Each team's, the same way.
team_rows AS (
  SELECT s.season AS season, unnest(s.teams) AS t FROM seasons
),
teams AS (
  SELECT season, t.code AS code, 'rim' AS zone, t.rim.n AS n, t.rim.pts AS pts FROM team_rows
  UNION ALL SELECT season, t.code, 'mid', t.mid.n, t.mid.pts FROM team_rows
  UNION ALL SELECT season, t.code, 'three', t.three.n, t.three.pts FROM team_rows
),
-- e: the league's points per shot in a class. mean: over the three classes, each weighted by its
-- attempts, which is the league's points over its attempts.
e AS (SELECT season, zone, pts / n AS e FROM league),
mean AS (SELECT season, sum(pts) / sum(n) AS mean FROM league GROUP BY season),
-- A team's points per shot, and its expected points per shot: its attempts in each class at the
-- league's points per shot there, over its attempts.
split AS (
  SELECT t.season, t.code, sum(t.pts) / sum(t.n) AS pps, sum(t.n * e.e) / sum(t.n) AS xpps
  FROM teams t JOIN e ON t.season = e.season AND t.zone = e.zone
  GROUP BY t.season, t.code
)
SELECT split.season, code, round(pps, 3) AS pps, round(xpps, 3) AS xpps,
       round(xpps - mean.mean, 3) AS mix, round(pps - xpps, 3) AS making
FROM split JOIN mean ON split.season = mean.season
ORDER BY split.season, code;
