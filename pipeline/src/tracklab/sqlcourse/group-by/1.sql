-- prompt: Rank the basketball teams by points. Using the team rows only (is_season_total is
--   false), return team_name, players and total_points, in that order, where players is the
--   number of rows of the team and total_points the sum of total_points. Most points first; break
--   ties by team_name, from A to Z.
-- hint: GROUP BY team_name gives one output row per team; the aggregates (count, sum) are
--   computed inside each group.
-- hint: count(*) counts the rows of the group, sum(total_points) adds the column up.
-- hint: Filter with WHERE NOT is_season_total before grouping, then ORDER BY total_points DESC,
--   team_name.
-- ordered: true
-- order_key: total_points DESC, team_name
SELECT team_name, count(*) AS players, sum(total_points) AS total_points
FROM bb_shots
WHERE NOT is_season_total
GROUP BY team_name
ORDER BY total_points DESC, team_name
