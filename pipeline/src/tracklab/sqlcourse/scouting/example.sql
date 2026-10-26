-- Full backs in the top 30% for speed and for pass completion within their position.
WITH speed AS (
  SELECT player_id, team_id, position_group, player_name, team_name, psv99,
         100 * percent_rank() OVER (PARTITION BY position_group ORDER BY psv99) AS speed_raw
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
),
passing AS (
  SELECT player_id, team_id, position_group, pass_pct_completed,
         100 * percent_rank() OVER (
           PARTITION BY position_group ORDER BY pass_pct_completed) AS passing_raw
  FROM fb_passing
  WHERE pass_pct_completed IS NOT NULL AND performance_count >= 5
)
SELECT s.player_name, s.team_name, s.psv99, round(s.speed_raw, 1) AS speed_pct,
       p.pass_pct_completed, round(p.passing_raw, 1) AS passing_pct
FROM speed AS s
JOIN passing AS p
  ON s.player_id = p.player_id AND s.team_id = p.team_id AND s.position_group = p.position_group
WHERE s.position_group = 'Full Back' AND s.speed_raw >= 70 AND p.passing_raw >= 70
ORDER BY s.speed_raw DESC, s.player_name
