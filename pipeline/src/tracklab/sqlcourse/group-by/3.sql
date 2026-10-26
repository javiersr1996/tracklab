-- prompt: For each position_group of fb_physical return position_group, rows (how many rows),
--   with_hsr (how many rows have a value in timetohsr_top3) and avg_minutes (the average of
--   minutes_full_all rounded to 1 decimal), in that order. Row order does not matter.
-- hint: count(*) counts rows; count(column) counts only the rows where that column is not NULL.
-- hint: avg(minutes_full_all) averages the group, and round(..., 1) goes around the whole avg.
-- ordered: false
SELECT position_group,
       count(*) AS rows,
       count(timetohsr_top3) AS with_hsr,
       round(avg(minutes_full_all), 1) AS avg_minutes
FROM fb_physical
GROUP BY position_group
