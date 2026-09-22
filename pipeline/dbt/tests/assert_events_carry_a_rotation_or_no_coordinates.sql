-- Decision 2 with the bug task 9 found written as an assertion. An event's
-- coordinates only mean something once they have been rotated into the venue
-- frame, and the rotation comes from the provider: `leftHoop` in basketball,
-- `attacking_side` in football. A row whose rotation cannot be resolved must
-- carry no coordinates at all, never coordinates rotated by a default sign.
--
-- In these 30 matches every row resolves, so this test is green on the bundle
-- and would stay green on a broken model too; the synthetic unit test is what
-- exercises the branch. Both exist on purpose.

SELECT e.sport, e.native_family, count(*) AS n_rows
FROM {{ ref('events') }} e
LEFT JOIN {{ ref('events') }} p
    ON p.event_id = e.possession_id AND p.match_id = e.match_id
WHERE e.sport = 'basketball'
  AND e.x_start_m IS NOT NULL
  AND p.event_id IS NULL
GROUP BY ALL
