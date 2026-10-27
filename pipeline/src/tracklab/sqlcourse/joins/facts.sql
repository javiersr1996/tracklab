-- (fact, value): the numbers lesson 5 prints.
WITH physical_only AS (
  SELECT p.* FROM fb_physical p
  ANTI JOIN fb_passing q
    ON p.player_id = q.player_id AND p.team_id = q.team_id AND p.position_group = q.position_group
),
passing_only AS (
  SELECT q.* FROM fb_passing q
  ANTI JOIN fb_physical p
    ON p.player_id = q.player_id AND p.team_id = q.team_id AND p.position_group = q.position_group
)
SELECT 'physical_rows' AS fact, (SELECT count(*) FROM fb_physical)::VARCHAR AS value
UNION ALL
SELECT 'passing_rows', (SELECT count(*) FROM fb_passing)::VARCHAR
UNION ALL
SELECT 'physical_players', (SELECT count(DISTINCT player_id) FROM fb_physical)::VARCHAR
UNION ALL
SELECT 'players_with_two_or_more_rows', count(*)::VARCHAR FROM (
  SELECT player_id FROM fb_physical GROUP BY player_id HAVING count(*) > 1
)
UNION ALL
SELECT 'matched_rows', count(*)::VARCHAR FROM fb_physical p JOIN fb_passing q
  ON p.player_id = q.player_id AND p.team_id = q.team_id AND p.position_group = q.position_group
UNION ALL
SELECT 'left_join_rows', count(*)::VARCHAR FROM fb_physical p LEFT JOIN fb_passing q
  ON p.player_id = q.player_id AND p.team_id = q.team_id AND p.position_group = q.position_group
UNION ALL
SELECT 'physical_only_rows', count(*)::VARCHAR FROM physical_only
UNION ALL
SELECT 'passing_only_rows', count(*)::VARCHAR FROM passing_only
UNION ALL
SELECT 'passing_only_goalkeepers', count(*)::VARCHAR FROM passing_only
WHERE position_group = 'Goalkeeper'
UNION ALL
SELECT 'physical_goalkeepers', count(*)::VARCHAR FROM fb_physical WHERE position_group = 'Goalkeeper'
UNION ALL
SELECT 'physical_only_other_position_in_passing', count(*)::VARCHAR FROM physical_only o
WHERE EXISTS (
  SELECT 1 FROM fb_passing q WHERE q.player_id = o.player_id AND q.team_id = o.team_id
)
UNION ALL
SELECT 'physical_only_not_in_passing_at_all', count(*)::VARCHAR FROM physical_only o
WHERE NOT EXISTS (
  SELECT 1 FROM fb_passing q WHERE q.player_id = o.player_id AND q.team_id = o.team_id
)
UNION ALL
SELECT 'join_on_player_id', count(*)::VARCHAR FROM fb_physical p JOIN fb_passing q
  ON p.player_id = q.player_id
UNION ALL
SELECT 'join_on_player_and_team', count(*)::VARCHAR FROM fb_physical p JOIN fb_passing q
  ON p.player_id = q.player_id AND p.team_id = q.team_id
UNION ALL
SELECT 'join_on_name_team_position', count(*)::VARCHAR FROM fb_physical p JOIN fb_passing q
  ON p.player_name = q.player_name AND p.team_id = q.team_id AND p.position_group = q.position_group
UNION ALL
SELECT 'name_with_two_ids', string_agg(player_name, ', ' ORDER BY player_name) FROM (
  SELECT player_name FROM fb_physical GROUP BY player_name HAVING count(DISTINCT player_id) > 1
)
UNION ALL
SELECT 'name_with_two_ids_team', min(team_name) FROM fb_physical
WHERE player_name IN (
  SELECT player_name FROM fb_physical GROUP BY player_name HAVING count(DISTINCT player_id) > 1
)
