-- prompt: From fact, for the metric 'psv99' of sport 'football' and family 'physical', return
--   position_group and avg_psv99 (the average of value rounded to 2 decimals), in that order. One
--   row per position_group. Row order does not matter.
-- hint: Keep one metric with WHERE metric = 'psv99' (plus sport and family) before grouping.
-- hint: GROUP BY position_group, then round(avg(value), 2).
-- ordered: false
SELECT position_group, round(avg(value), 2) AS avg_psv99
FROM fact
WHERE sport = 'football' AND family = 'physical' AND metric = 'psv99'
GROUP BY position_group
