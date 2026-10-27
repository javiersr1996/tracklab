-- (fact, value): the numbers lesson 1 prints.
WITH eleventh AS (
  SELECT attempts FROM bb_shots ORDER BY attempts DESC, player_name LIMIT 1 OFFSET 10
)
SELECT 'rows' AS fact, count(*)::VARCHAR AS value FROM bb_shots
UNION ALL
SELECT 'players', count(DISTINCT player_id)::VARCHAR FROM bb_shots
UNION ALL
SELECT 'top_shooter', arg_max(player_name, attempts) FROM bb_shots
UNION ALL
SELECT 'top_attempts', max(attempts)::VARCHAR FROM bb_shots
UNION ALL
SELECT 'eleventh_attempts', attempts::VARCHAR FROM eleventh
UNION ALL
SELECT 'tied_with_eleventh', count(*)::VARCHAR FROM bb_shots
WHERE attempts = (SELECT attempts FROM eleventh)
