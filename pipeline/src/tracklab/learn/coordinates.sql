-- Run it with DuckDB from a folder that holds the two public SkillCorner repositories side by side,
-- opendata-basketball and opendata. Three results: no Track Lab code, no intermediate table.

-- 1. Basketball, match 114086: the attack sign of each team in each period, from `leftHoop`
--    (true when the offence shoots at the hoop on the left of the broadcast, at negative x).
SELECT p.period AS period, 'bb:' || p.offTeamId AS team_id,
       CASE WHEN p.leftHoop THEN -1 ELSE 1 END AS attack_sign, count(*) AS possessions
FROM (SELECT unnest(possessions) AS p
      FROM read_json('opendata-basketball/data/matches/114086/114086_dynamic_events.json'))
GROUP BY ALL
ORDER BY period, team_id;

-- 2. The first frame of the home page's basketball possession, as delivered in feet and in metres.
WITH frame AS (
  SELECT homePlayers || awayPlayers AS players, ball
  FROM read_json('opendata-basketball/data/matches/114086/114086_tracking_data.jsonl.gz',
                 format = 'newline_delimited')
  WHERE wallClock = 1199000
),
entity AS (
  SELECT 'bb:' || pl.playerId AS entity_id, pl.xyz[1] AS x_ft, pl.xyz[2] AS y_ft
  FROM (SELECT unnest(players) AS pl FROM frame)
  UNION ALL
  SELECT 'bb:ball', ball.xyz[1], ball.xyz[2] FROM frame
)
SELECT entity_id, round(x_ft, 2) AS x_ft, round(y_ft, 2) AS y_ft,
       round(x_ft * 0.3048, 2) AS x_m, round(y_ft * 0.3048, 2) AS y_m
FROM entity
ORDER BY entity_id;

-- 3. Football, match 1874553: the pitch, and the attack sign of each team in each period, from
--    `home_team_side` (left_to_right when the home team attacks towards positive x).
WITH side AS (
  SELECT unnest(range(1, len(home_team_side) + 1)) AS period, unnest(home_team_side) AS home_side,
         home_team.id AS home, away_team.id AS away, pitch_length, pitch_width
  FROM read_json('opendata/data/matches/1874553/1874553_match.json')
),
sign AS (
  SELECT *, CASE home_side WHEN 'left_to_right' THEN 1 WHEN 'right_to_left' THEN -1 END AS home_sign
  FROM side
)
SELECT period, 'fb:' || home AS team_id, home_sign AS attack_sign, pitch_length, pitch_width FROM sign
UNION ALL
SELECT period, 'fb:' || away, -home_sign, pitch_length, pitch_width FROM sign
ORDER BY period, team_id;
