-- The five players with the most shot attempts, most first.
SELECT player_name, team_name, attempts
FROM bb_shots
ORDER BY attempts DESC
LIMIT 5
