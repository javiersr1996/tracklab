-- Lesson 12: every row of the per-team tables, from expected-points.json alone, the counts by zone
-- class the site publishes. Save the file next to this query first.
WITH file AS (
  SELECT seasons, z FROM read_json('expected-points.json')
),
seasons AS (
  SELECT unnest(seasons) AS s FROM file
),
-- The league's attempts and points in each zone class, one row per season and class.
league AS (
  SELECT s.season AS season, 'rim' AS zone, s.league.rim.n AS n, s.league.rim.pts AS pts FROM seasons
  UNION ALL SELECT s.season, 'mid', s.league.mid.n, s.league.mid.pts FROM seasons
  UNION ALL SELECT s.season, 'three', s.league.three.n, s.league.three.pts FROM seasons
),
-- Each team's attempts and points, the same way.
team_rows AS (
  SELECT s.season AS season, unnest(s.teams) AS t FROM seasons
),
teams AS (
  SELECT season, t.code AS code, 'rim' AS zone, t.rim.n AS n, t.rim.pts AS pts FROM team_rows
  UNION ALL SELECT season, t.code, 'mid', t.mid.n, t.mid.pts FROM team_rows
  UNION ALL SELECT season, t.code, 'three', t.three.n, t.three.pts FROM team_rows
),
-- e: the league's points per shot in a class, and v what a make there scores (3 for a three, 2 for
-- a two). mean: over the three classes, each weighted by its attempts, which is the league's points
-- over its attempts.
e AS (SELECT season, zone, pts / n AS e, CASE zone WHEN 'three' THEN 3 ELSE 2 END AS v FROM league),
mean AS (SELECT season, sum(pts) / sum(n) AS mean FROM league GROUP BY season),
-- A team's points per shot, and its expected points per shot: its attempts in each class at the
-- league's points per shot there, over its attempts. For the intervals, the mean over its attempts
-- of the square of what each adds to mix (e) and to making (its points minus e, whose square sums
-- to v * P - 2 * e * P + n * e * e in a class, P its points there).
split AS (
  SELECT t.season, t.code, sum(t.n) AS n, sum(t.pts) / sum(t.n) AS pps, sum(t.n * e.e) / sum(t.n) AS xpps,
         sum(t.n * e.e * e.e) / sum(t.n) AS mix_sq,
         sum(e.v * t.pts - 2 * e.e * t.pts + t.n * e.e * e.e) / sum(t.n) AS making_sq
  FROM teams t JOIN e ON t.season = e.season AND t.zone = e.zone
  GROUP BY t.season, t.code
),
-- Mix and making are means over the attempts: the standard error of each is the spread of what one
-- attempt adds over the square root of the attempts, and its interval is the part plus and minus
-- z of them (z from the file).
r AS (
  SELECT split.season, code, pps, xpps, xpps - mean.mean AS mix, pps - xpps AS making,
         sqrt((mix_sq - xpps * xpps) / n) AS se_mix,
         sqrt((making_sq - (pps - xpps) * (pps - xpps)) / n) AS se_making
  FROM split JOIN mean ON split.season = mean.season
)
SELECT season, code, round(pps, 3) AS pps, round(xpps, 3) AS xpps,
       round(mix, 3) AS mix, round(making, 3) AS making,
       round(mix - z * se_mix, 3) AS mix_lo, round(mix + z * se_mix, 3) AS mix_hi,
       round(making - z * se_making, 3) AS making_lo, round(making + z * se_making, 3) AS making_hi
FROM r, (SELECT z FROM file)
ORDER BY season, code;
