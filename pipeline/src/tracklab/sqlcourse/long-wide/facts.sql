-- (fact, value): the numbers lesson 6 prints.
SELECT 'fact_rows' AS fact, count(*)::VARCHAR AS value FROM fact
UNION ALL
SELECT 'football_physical_metrics', count(DISTINCT metric)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'physical'
UNION ALL
SELECT 'football_passing_metrics', count(DISTINCT metric)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'passing'
UNION ALL
SELECT 'football_obr_metrics', count(DISTINCT metric)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'obr'
UNION ALL
SELECT 'physical_rows_per_metric_max', max(n)::VARCHAR FROM (
  SELECT count(*) AS n FROM fact WHERE sport = 'football' AND family = 'physical' GROUP BY metric
)
UNION ALL
SELECT 'fb_physical_rows', count(*)::VARCHAR FROM fb_physical
UNION ALL
SELECT 'psv99_rows', count(*)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'physical' AND metric = 'psv99'
UNION ALL
SELECT 'timetohsr_top3_rows', count(*)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'physical' AND metric = 'timetohsr_top3'
UNION ALL
SELECT 'null_values_in_fact', count(*)::VARCHAR FROM fact WHERE value IS NULL
UNION ALL
SELECT 'example_players', count(*)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'physical' AND team_id = 871
  AND position_group = 'Center Forward' AND metric = 'psv99'
UNION ALL
SELECT 'long_rows_of_example', count(*)::VARCHAR FROM fact
WHERE sport = 'football' AND family = 'physical' AND team_id = 871
  AND position_group = 'Center Forward' AND metric IN ('count_match', 'psv99')
UNION ALL
SELECT 'basketball_shots_metrics', count(DISTINCT metric)::VARCHAR FROM fact
WHERE sport = 'basketball' AND family = 'shots'
