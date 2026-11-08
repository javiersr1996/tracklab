-- events.sql resolves the seed with a QUALIFY that prefers a literal subtype
-- over the `*` of its family. Two rows with the same (sport, family, pattern)
-- tie in that ORDER BY and one is picked arbitrarily, while the `unique` test
-- on event_id still passes. This keeps the seed from ever tying.

SELECT
    sport,
    native_family,
    native_subtype_pattern,
    count(*) AS n_rows
FROM {{ ref('event_type_map') }}
GROUP BY sport, native_family, native_subtype_pattern
HAVING count(*) > 1
