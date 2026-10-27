-- prompt: From fact (sport 'football', family 'physical') take the Wide Attackers of the team
--   with team_id 868, one row per player, and return player_id, sprint_count_full_all and
--   psv99, in that order: the two metrics as columns. You can pivot or use conditional
--   aggregation: both give the same result. Row order does not matter.
-- hint: One row per player_id means the metric names have to become columns: that is pivoting.
-- hint: Pivot: SELECT * FROM (PIVOT (SELECT player_id, metric, value FROM fact WHERE ...) ON
--   metric IN ('sprint_count_full_all', 'psv99') USING max(value)). Without PIVOT:
--   GROUP BY player_id and max(CASE WHEN metric = '...' THEN value END) for each column.
-- hint: With CASE: SELECT player_id, max(CASE WHEN metric = 'sprint_count_full_all' THEN value
--   END) AS sprint_count_full_all, max(CASE WHEN metric = 'psv99' THEN value END) AS psv99
--   FROM fact WHERE (filters) GROUP BY player_id.
-- ordered: false
SELECT player_id,
       max(CASE WHEN metric = 'sprint_count_full_all' THEN value END) AS sprint_count_full_all,
       max(CASE WHEN metric = 'psv99' THEN value END) AS psv99
FROM fact
WHERE sport = 'football' AND family = 'physical'
  AND team_id = 868 AND position_group = 'Wide Attacker'
  AND metric IN ('sprint_count_full_all', 'psv99')
GROUP BY player_id
