-- prompt: Basketball version, as /warehouse does it. Take the team rows (is_season_total is false)
--   with at least 10 games_played. threes_per_game is three_attempts / games_played, and the
--   percentile is 100 * percent_rank() over all those rows ordered by threes_per_game from low
--   to high, rounded to 1 decimal. Return player_name, team_name, threes_per_game (rounded to 2
--   decimals) and percentile, in that order, for the 5 highest percentiles, highest percentile
--   first. Break ties by player_name, from A to Z.
-- hint: Divide with a decimal number, three_attempts * 1.0 / games_played, and use the same
--   expression in the percent_rank() ORDER BY.
-- hint: There is no PARTITION BY: the window is the whole pool, which is the rows left by the
--   WHERE of the same query.
-- hint: Wrap the query in a subquery so the outer one can ORDER BY percentile DESC, player_name
--   LIMIT 5.
-- ordered: true
-- order_key: percentile DESC, player_name
SELECT player_name, team_name, threes_per_game, percentile
FROM (
  SELECT player_name, team_name,
         round(three_attempts * 1.0 / games_played, 2) AS threes_per_game,
         round(100 * percent_rank() OVER (ORDER BY three_attempts * 1.0 / games_played), 1)
           AS percentile
  FROM bb_shots
  WHERE NOT is_season_total AND games_played >= 10
) AS pool
ORDER BY percentile DESC, player_name
LIMIT 5
