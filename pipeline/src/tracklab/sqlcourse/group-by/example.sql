-- One row per basketball team: players, attempts, mades and field-goal percentage.
SELECT team_name,
       count(*) AS players,
       sum(attempts) AS attempts,
       sum(mades) AS mades,
       round(100.0 * sum(mades) / sum(attempts), 1) AS fg_pct
FROM bb_shots
WHERE NOT is_season_total
GROUP BY team_name
ORDER BY team_name
