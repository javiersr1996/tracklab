-- prompt: Who stands out against their own team? From fb_physical, compute each team's average
--   psv99 (over all its rows), then list the players whose psv99 is at least 3 above their
--   team's average. Return player_name, team_name, psv99 and gap, in that order, where gap is
--   psv99 minus the team average rounded to 2 decimals. Order by gap from largest to smallest
--   and break ties by player_name, from A to Z.
-- hint: A CTE can hold a GROUP BY result (team_name and its average) that the main query joins
--   back to the player rows.
-- hint: Join on team_name, then compare in WHERE: p.psv99 - t.avg_psv99 >= 3.
-- hint: WITH team AS (SELECT team_name, avg(psv99) AS avg_psv99 FROM fb_physical GROUP BY
--   team_name) SELECT ... FROM fb_physical AS p JOIN team AS t USING (team_name) WHERE ...
-- ordered: true
-- order_key: gap DESC, player_name
WITH team AS (
  SELECT team_name, avg(psv99) AS avg_psv99
  FROM fb_physical
  GROUP BY team_name
)
SELECT p.player_name, p.team_name, p.psv99, round(p.psv99 - t.avg_psv99, 2) AS gap
FROM fb_physical AS p
JOIN team AS t ON p.team_name = t.team_name
WHERE p.psv99 - t.avg_psv99 >= 3
ORDER BY gap DESC, p.player_name
