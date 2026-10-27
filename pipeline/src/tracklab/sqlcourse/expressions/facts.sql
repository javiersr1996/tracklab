-- (fact, value): the numbers lesson 3 prints.
SELECT 'seven_over_two' AS fact, (7 / 2)::VARCHAR AS value
UNION ALL
SELECT 'seven_whole_over_two', (7 // 2)::VARCHAR
UNION ALL
SELECT 'one_over_zero_is_inf', isinf(1 / 0)::VARCHAR
UNION ALL
SELECT 'zero_over_zero_is_nan', isnan(0.0 / 0)::VARCHAR
UNION ALL
SELECT 'one_over_nullif_zero_is_null', (1 / NULLIF(0, 0) IS NULL)::VARCHAR
UNION ALL
SELECT 'team_rows', count(*)::VARCHAR FROM bb_shots WHERE NOT is_season_total
UNION ALL
SELECT 'zero_attempts', count(*)::VARCHAR FROM bb_shots
WHERE NOT is_season_total AND attempts = 0
UNION ALL
SELECT 'zero_three_attempts', count(*)::VARCHAR FROM bb_shots
WHERE NOT is_season_total AND three_attempts = 0
UNION ALL
SELECT 'zero_games', count(*)::VARCHAR FROM bb_shots
WHERE NOT is_season_total AND games_played = 0
UNION ALL
SELECT 'whole_division_zero', count(*)::VARCHAR FROM bb_shots
WHERE NOT is_season_total AND attempts > 0 AND mades // attempts = 0
UNION ALL
SELECT 'whole_division_one', count(*)::VARCHAR FROM bb_shots
WHERE NOT is_season_total AND attempts > 0 AND mades // attempts = 1
UNION ALL
SELECT 'total_rows_excluded', count(*)::VARCHAR FROM bb_shots WHERE is_season_total
UNION ALL
SELECT 'midfield_20_matches', count(*)::VARCHAR FROM fb_physical
WHERE position_group = 'Midfield' AND count_match >= 20
