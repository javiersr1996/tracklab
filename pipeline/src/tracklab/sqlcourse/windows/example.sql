-- The five fastest midfielders (psv99) among those with at least 5 matches, with their rank and
-- their percentile among the midfielders.
SELECT player_name, team_name, psv99, speed_rank, percentile
FROM (
  SELECT player_name, team_name, position_group, psv99,
         rank() OVER (PARTITION BY position_group ORDER BY psv99 DESC) AS speed_rank,
         round(100 * percent_rank() OVER (PARTITION BY position_group ORDER BY psv99), 1)
           AS percentile
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
) AS pool
WHERE position_group = 'Midfield' AND speed_rank <= 5
ORDER BY speed_rank, player_name
