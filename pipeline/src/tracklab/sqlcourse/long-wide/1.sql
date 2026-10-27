-- prompt: In the long table fact, for sport 'football', return family, metrics (how many
--   different metric names the family has) and rows (how many rows it has), in that order. One
--   row per family. Row order does not matter.
-- hint: Each row of fact is one value of one metric for one player: the metric name is data, not
--   a column.
-- hint: GROUP BY family; count(DISTINCT metric) counts the names without repeating them.
-- ordered: false
SELECT family, count(DISTINCT metric) AS metrics, count(*) AS rows
FROM fact
WHERE sport = 'football'
GROUP BY family
