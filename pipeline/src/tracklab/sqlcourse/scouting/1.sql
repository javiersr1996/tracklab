-- prompt: Build the shortlist of players who are fast and accurate within their position. Speed
--   pool: fb_physical rows with a psv99 and at least 5 matches (count_match); speed_pct is 100 *
--   percent_rank() over the rows of the same position_group ordered by psv99, rounded to 1
--   decimal. Passing pool: fb_passing rows with a pass_pct_completed and at least 5
--   performance_count; passing_pct is the same over pass_pct_completed. Join the two pools on
--   player_id, team_id and position_group and keep the rows with speed_pct and passing_pct both
--   at least 70. Return player_name, team_name, position_group, speed_pct and passing_pct, in
--   that order. Row order does not matter.
-- hint: Write each pool as its own CTE (WITH speed AS (...), passing AS (...)): each has its own
--   WHERE and its own percent_rank, so the percentiles are not mixed up.
-- hint: Filter the pools inside the CTEs, before the percentile is computed; filter on the
--   percentiles after the join.
-- hint: SELECT ... FROM speed AS s JOIN passing AS p ON (the three equalities) WHERE s.speed_pct
--   >= 70 AND p.passing_pct >= 70.
-- ordered: false
WITH speed AS (
  SELECT player_id, team_id, position_group, player_name, team_name,
         round(100 * percent_rank() OVER (PARTITION BY position_group ORDER BY psv99), 1)
           AS speed_pct
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
),
passing AS (
  SELECT player_id, team_id, position_group,
         round(100 * percent_rank() OVER (
           PARTITION BY position_group ORDER BY pass_pct_completed), 1) AS passing_pct
  FROM fb_passing
  WHERE pass_pct_completed IS NOT NULL AND performance_count >= 5
)
SELECT s.player_name, s.team_name, s.position_group, s.speed_pct, p.passing_pct
FROM speed AS s
JOIN passing AS p
  ON s.player_id = p.player_id AND s.team_id = p.team_id AND s.position_group = p.position_group
WHERE s.speed_pct >= 70 AND p.passing_pct >= 70
