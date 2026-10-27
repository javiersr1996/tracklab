-- Full backs with more than 98 minutes_full_all, the most minutes first.
SELECT player_name, team_name, minutes_full_all
FROM fb_physical
WHERE position_group = 'Full Back' AND minutes_full_all > 98
ORDER BY minutes_full_all DESC, player_name
