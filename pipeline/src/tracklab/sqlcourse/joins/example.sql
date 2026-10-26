-- Auckland FC full backs with their speed (fb_physical) and pass completion (fb_passing).
SELECT p.player_name, p.position_group, p.psv99, q.pass_pct_completed
FROM fb_physical AS p
JOIN fb_passing AS q
  ON p.player_id = q.player_id
 AND p.team_id = q.team_id
 AND p.position_group = q.position_group
WHERE p.team_name = 'Auckland FC' AND p.position_group = 'Full Back'
ORDER BY p.player_name
