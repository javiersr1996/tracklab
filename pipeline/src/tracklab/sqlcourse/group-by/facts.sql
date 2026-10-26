-- (fact, value): the numbers lesson 4 prints.
WITH teams AS (
  SELECT team_name, count(*) AS players, sum(total_points) AS points
  FROM bb_shots
  WHERE NOT is_season_total
  GROUP BY team_name
)
SELECT 'teams' AS fact, count(*)::VARCHAR AS value FROM teams
UNION ALL
SELECT 'top_team', arg_max(team_name, points) FROM teams
UNION ALL
SELECT 'top_team_points', max(points)::VARCHAR FROM teams
UNION ALL
SELECT 'teams_with_20_or_more_players', count(*)::VARCHAR FROM teams WHERE players >= 20
UNION ALL
SELECT 'attempts_team_rows', sum(attempts)::VARCHAR FROM bb_shots WHERE NOT is_season_total
UNION ALL
SELECT 'attempts_all_rows', sum(attempts)::VARCHAR FROM bb_shots
UNION ALL
SELECT 'count_star_hsr', count(*)::VARCHAR FROM fb_physical
UNION ALL
SELECT 'count_column_hsr', count(timetohsr_top3)::VARCHAR FROM fb_physical
UNION ALL
SELECT 'football_teams', count(DISTINCT team_name)::VARCHAR FROM fb_physical
UNION ALL
SELECT 'football_teams_250_matches', count(*)::VARCHAR FROM (
  SELECT team_name FROM fb_physical GROUP BY team_name HAVING sum(count_match) >= 250
)
UNION ALL
SELECT 'avg_of_empty_group_is_null', (avg(minutes_full_all) IS NULL)::VARCHAR
FROM fb_physical WHERE position_group = 'Goalkeeper'
