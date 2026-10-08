-- Example "fact" of /warehouse: median and 90th percentile of one metric over the long fact.
-- percentile_cont interpolates between the closest ranks, as quantile_cont in DuckDB.
SELECT round((percentile_cont(0.5) WITHIN GROUP (ORDER BY value))::numeric, 2) AS p50,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY value))::numeric, 2) AS p90,
       count(*) AS n
FROM warehouse.fact_player_season_metric
WHERE metric = {football_metric} AND sport = 'football' AND family = 'physical'
  AND NOT is_season_total
