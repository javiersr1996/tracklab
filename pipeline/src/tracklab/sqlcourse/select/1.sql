-- prompt: List the 11 players with the most shot attempts: player_name, team_name and attempts,
--   in that order, most attempts first. Two players can have the same number of attempts, so
--   break ties by player_name, from A to Z.
-- hint: ORDER BY takes several columns: the second one only decides between rows that tie on the
--   first.
-- hint: DESC sorts from the largest down; a column without it sorts up (A to Z for text).
-- hint: LIMIT 11 keeps the first 11 rows of the sorted result.
-- ordered: true
-- order_key: attempts DESC, player_name
SELECT player_name, team_name, attempts
FROM bb_shots
ORDER BY attempts DESC, player_name
LIMIT 11
