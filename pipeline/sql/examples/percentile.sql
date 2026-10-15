-- Example "percentile" of /warehouse, on the dimensional model: a football player's top speed
-- against his position group (players with at least the minimum matches), with the players in
-- the group and the matches they played between them (a match counts once per player in it).
-- Postgres has no count(DISTINCT) as a window function: the players per group come from a join.
WITH cells AS (
    SELECT player_id, team_id, position_group,
           max(value) FILTER (WHERE metric = {football_metric}) AS metric_value,
           max(value) FILTER (WHERE metric = 'count_match') AS count_match
    FROM warehouse.fact_player_season_metric
    WHERE sport = 'football' AND family = 'physical'
      AND metric IN ({football_metric}, 'count_match')
    GROUP BY player_id, team_id, position_group
),
pool AS (
    SELECT * FROM cells WHERE metric_value IS NOT NULL AND count_match >= {min_matches}
),
ranked AS (
    SELECT pool.*,
           percent_rank() OVER (PARTITION BY position_group ORDER BY metric_value) AS pct,
           sum(count_match) OVER (PARTITION BY position_group) AS player_matches_in_group
    FROM pool
),
groups AS (
    SELECT position_group, count(DISTINCT player_id) AS players_in_group
    FROM pool
    GROUP BY position_group
)
SELECT p.player_name,
       t.team_name,
       r.position_group,
       r.metric_value AS {football_metric_column},
       round((r.pct * 100)::numeric, 1) AS percentile,
       g.players_in_group,
       r.player_matches_in_group::bigint AS player_matches_in_group
FROM ranked AS r
JOIN groups AS g USING (position_group)
JOIN warehouse.dim_player AS p ON p.sport = 'football' AND p.player_id = r.player_id
JOIN warehouse.dim_team AS t ON t.sport = 'football' AND t.team_id = r.team_id
WHERE p.player_name = {football_player}
