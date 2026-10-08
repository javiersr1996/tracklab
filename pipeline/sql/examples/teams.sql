-- Example "teams" of /warehouse, on the dimensional model: basketball teams from their players'
-- counts, summed over the team rows (the total rows of traded players are left out).
SELECT t.team_name,
       (sum(f.value) FILTER (WHERE f.metric = 'attempts'))::bigint AS attempts,
       (sum(f.value) FILTER (WHERE f.metric = 'mades'))::bigint AS mades,
       round((100.0 * sum(f.value) FILTER (WHERE f.metric = 'mades')
              / sum(f.value) FILTER (WHERE f.metric = 'attempts'))::numeric, 1) AS fg_pct,
       (sum(f.value) FILTER (WHERE f.metric = 'total_points'))::bigint AS points
FROM warehouse.fact_player_season_metric AS f
JOIN warehouse.dim_team AS t ON t.sport = f.sport AND t.team_id = f.team_id
WHERE f.sport = 'basketball' AND f.family = 'shots' AND NOT f.is_season_total
  AND f.metric IN ('attempts', 'mades', 'total_points')
GROUP BY t.team_name
ORDER BY points DESC, t.team_name COLLATE "C"
