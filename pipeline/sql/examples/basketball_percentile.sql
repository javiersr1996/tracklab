-- Example "basketball_percentile" of /warehouse, on the dimensional model: a basketball player's
-- three-point attempts per game against the players with at least the minimum games, with the
-- player ids in the pool and the games they played between them (a sum over players).
WITH cells AS (
    SELECT player_id, team_id,
           max(value) FILTER (WHERE metric = 'games_played') AS games_played,
           max(value) FILTER (WHERE metric = 'three_attempts') AS three_attempts
    FROM warehouse.fact_player_season_metric
    WHERE sport = 'basketball' AND family = 'shots' AND NOT is_season_total
      AND metric IN ('games_played', 'three_attempts')
    GROUP BY player_id, team_id
),
pool AS (
    SELECT cells.*, three_attempts / games_played AS threes_per_game
    FROM cells
    WHERE games_played >= {min_games}
),
ranked AS (
    SELECT pool.*,
           percent_rank() OVER (ORDER BY threes_per_game) AS pct,
           sum(games_played) OVER () AS player_games_in_pool
    FROM pool
)
SELECT p.player_name,
       t.team_name,
       r.games_played::bigint AS games_played,
       r.three_attempts::bigint AS three_attempts,
       round(r.threes_per_game::numeric, 2) AS threes_per_game,
       round((r.pct * 100)::numeric, 1) AS percentile,
       (SELECT count(DISTINCT player_id) FROM pool) AS player_ids_in_pool,
       r.player_games_in_pool::bigint AS player_games_in_pool
FROM ranked AS r
JOIN warehouse.dim_player AS p ON p.sport = 'basketball' AND p.player_id = r.player_id
JOIN warehouse.dim_team AS t ON t.sport = 'basketball' AND t.team_id = r.team_id
WHERE p.player_name = {basketball_player}
