-- prompt: Which five players scored the most points? Return player_name and total_points, in that
--   order. The order of the rows does not matter here: the checker compares them as a set.
-- hint: The rows can come in any order, but picking the top five still needs ORDER BY.
-- hint: Sort by total_points from the largest down, then keep five rows with LIMIT.
-- ordered: false
SELECT player_name, total_points
FROM bb_shots
ORDER BY total_points DESC
LIMIT 5
