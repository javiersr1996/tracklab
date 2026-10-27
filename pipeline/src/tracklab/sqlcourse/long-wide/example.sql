-- Two metrics of Perth Glory's center forwards (team_id 871), turned from long to wide.
SELECT *
FROM (
  PIVOT (
    SELECT player_id, metric, value
    FROM fact
    WHERE sport = 'football' AND family = 'physical'
      AND team_id = 871 AND position_group = 'Center Forward'
      AND metric IN ('count_match', 'psv99')
  )
  ON metric IN ('count_match', 'psv99')
  USING max(value)
)
ORDER BY player_id
