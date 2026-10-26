-- (fact, value): the numbers lesson 8 prints.
WITH speed AS (
  SELECT player_id, team_id, position_group,
         100 * percent_rank() OVER (PARTITION BY position_group ORDER BY psv99) AS speed_raw
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
),
passing AS (
  SELECT player_id, team_id, position_group,
         100 * percent_rank() OVER (
           PARTITION BY position_group ORDER BY pass_pct_completed) AS passing_raw
  FROM fb_passing
  WHERE pass_pct_completed IS NOT NULL AND performance_count >= 5
),
both_pools AS (
  SELECT s.position_group, s.speed_raw, p.passing_raw
  FROM speed AS s
  JOIN passing AS p
    ON s.player_id = p.player_id AND s.team_id = p.team_id AND s.position_group = p.position_group
)
SELECT 'speed_pool_rows' AS fact, count(*)::VARCHAR AS value FROM speed
UNION ALL
SELECT 'passing_pool_rows', count(*)::VARCHAR FROM passing
UNION ALL
SELECT 'rows_in_both_pools', count(*)::VARCHAR FROM both_pools
UNION ALL
SELECT 'shortlist_rows', count(*)::VARCHAR FROM both_pools
WHERE speed_raw >= 70 AND passing_raw >= 70
UNION ALL
SELECT 'full_back_shortlist_rows', count(*)::VARCHAR FROM both_pools
WHERE position_group = 'Full Back' AND speed_raw >= 70 AND passing_raw >= 70
UNION ALL
SELECT 'speed_only_70', count(*)::VARCHAR FROM both_pools WHERE speed_raw >= 70
UNION ALL
SELECT 'passing_only_70', count(*)::VARCHAR FROM both_pools WHERE passing_raw >= 70
