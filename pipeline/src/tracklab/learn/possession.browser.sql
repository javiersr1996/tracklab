-- files: /data/learn/possession.json
-- The football timeline, one row per run of same-team phases: period, start and end (s on the
-- video), team (0 or 1) and how many phases it spans.
CREATE VIEW runs AS
SELECT r[1]::INT AS period, r[2] AS start_s, r[3] AS end_s, r[4]::INT AS team, r[5]::INT AS phases
FROM (SELECT unnest(football.timeline.rows) AS r FROM read_json('/data/learn/possession.json'));
-- The basketball timeline, one row per possession: period, start and end (s on the video), team.
CREATE VIEW possessions AS
SELECT r[1]::INT AS period, r[2] AS start_s, r[3] AS end_s, r[4]::INT AS team
FROM (SELECT unnest(basketball.timeline.rows) AS r FROM read_json('/data/learn/possession.json'));
-- Lesson 10 in this browser: from the two timelines alone, each example match's row of the
-- tables, and the share of runs and possessions that outlast twice their median (an exponential
-- with the same median gives a quarter).
WITH fb AS (SELECT end_s - start_s AS s, phases FROM runs),
bb AS (SELECT end_s - start_s AS s FROM possessions),
fb_med AS (SELECT quantile_cont(s, 0.5) AS m FROM fb),
bb_med AS (SELECT quantile_cont(s, 0.5) AS m FROM bb),
figures AS (
  SELECT 'possession.football.matches.fb:1874553.runs' AS figure, count(*)::VARCHAR AS value, 1 AS k
  FROM fb
  UNION ALL
  SELECT 'possession.football.matches.fb:1874553.run_median_s', round(quantile_cont(s, 0.5), 4)::VARCHAR, 2
  FROM fb
  UNION ALL
  SELECT 'possession.football.matches.fb:1874553.run_p90_s', round(quantile_cont(s, 0.9), 4)::VARCHAR, 3
  FROM fb
  UNION ALL
  SELECT 'possession.football.matches.fb:1874553.multi_phase_pct',
         round(100 * avg((phases > 1)::INT), 2)::VARCHAR, 4
  FROM fb
  UNION ALL
  SELECT 'learn.fb.beyond2_pct', round(100 * avg((s > 2 * (SELECT m FROM fb_med))::INT), 1)::VARCHAR, 5
  FROM fb
  UNION ALL
  SELECT 'possession.basketball.matches.bb:114086.possessions', count(*)::VARCHAR, 6 FROM bb
  UNION ALL
  SELECT 'possession.basketball.matches.bb:114086.median_s', round(quantile_cont(s, 0.5), 4)::VARCHAR, 7
  FROM bb
  UNION ALL
  SELECT 'possession.basketball.matches.bb:114086.p90_s', round(quantile_cont(s, 0.9), 4)::VARCHAR, 8
  FROM bb
  UNION ALL
  SELECT 'learn.bb.beyond2_pct', round(100 * avg((s > 2 * (SELECT m FROM bb_med))::INT), 1)::VARCHAR, 9
  FROM bb
)
SELECT figure, regexp_replace(value, '\.0$', '') AS value FROM figures ORDER BY k
