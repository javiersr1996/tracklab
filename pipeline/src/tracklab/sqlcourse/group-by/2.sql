-- prompt: Which football teams have at least 250 matches added up over their players? In
--   fb_physical, return team_name, players (the number of rows) and matches (the sum of
--   count_match), in that order. Row order does not matter.
-- hint: A condition on a sum cannot go in WHERE: WHERE runs before the groups exist.
-- hint: HAVING filters the groups after GROUP BY, and it can use aggregates: HAVING sum(...) >= ...
-- hint: GROUP BY team_name HAVING sum(count_match) >= 250.
-- ordered: false
SELECT team_name, count(*) AS players, sum(count_match) AS matches
FROM fb_physical
GROUP BY team_name
HAVING sum(count_match) >= 250
