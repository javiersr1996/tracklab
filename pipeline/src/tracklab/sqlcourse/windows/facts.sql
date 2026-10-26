-- (fact, value): the numbers lesson 7 prints.
WITH pool AS (
  SELECT player_name, team_name, position_group, psv99, count_match, player_id,
         percent_rank() OVER (PARTITION BY position_group ORDER BY psv99) AS pct,
         rank() OVER (PARTITION BY position_group ORDER BY psv99 DESC) AS speed_rank,
         row_number() OVER (PARTITION BY position_group ORDER BY psv99 DESC, player_name) AS rn,
         count(DISTINCT player_id) OVER (PARTITION BY position_group) AS players_in_group,
         sum(count_match) OVER (PARTITION BY position_group)::INTEGER AS matches_in_group
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
),
bb AS (
  SELECT player_name, games_played,
         percent_rank() OVER (ORDER BY three_attempts * 1.0 / games_played) AS pct
  FROM bb_shots
  WHERE NOT is_season_total AND games_played >= 10
)
SELECT 'football_pool_rows' AS fact, count(*)::VARCHAR AS value FROM pool
UNION ALL
SELECT 'midfield_pool_rows', count(*)::VARCHAR FROM pool WHERE position_group = 'Midfield'
UNION ALL
SELECT 'midfield_players', max(players_in_group)::VARCHAR FROM pool
WHERE position_group = 'Midfield'
UNION ALL
SELECT 'midfield_matches', max(matches_in_group)::VARCHAR FROM pool
WHERE position_group = 'Midfield'
UNION ALL
SELECT 'jay_barnett_psv99', psv99::VARCHAR FROM pool WHERE player_name = 'Jay Barnett'
UNION ALL
SELECT 'jay_barnett_percentile', round(100 * pct, 1)::VARCHAR FROM pool
WHERE player_name = 'Jay Barnett'
UNION ALL
SELECT 'jay_barnett_rank', speed_rank::VARCHAR FROM pool WHERE player_name = 'Jay Barnett'
UNION ALL
SELECT 'fastest_midfielder', player_name FROM pool WHERE position_group = 'Midfield' AND rn = 1
UNION ALL
SELECT 'fastest_midfielder_psv99', psv99::VARCHAR FROM pool
WHERE position_group = 'Midfield' AND rn = 1
UNION ALL
SELECT 'rank_differs_from_row_number', count(*)::VARCHAR FROM pool WHERE speed_rank <> rn
UNION ALL
SELECT 'basketball_pool_rows', count(*)::VARCHAR FROM bb
UNION ALL
SELECT 'guillem_vives_percentile', round(100 * pct, 1)::VARCHAR FROM bb
WHERE player_name = 'Guillem Vives'
