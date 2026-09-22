"""`tracklab possessions`: the two candidate rules for a football team possession, measured.

Football has no team possession as a delivered event, so task 12 has to derive
one, and the plan named two candidates. This probe implements both, scores them
against a third source neither of them uses, and writes
`reports/possessions_football.csv` so the losing rule's figures stay
reproducible instead of surviving as a sentence in a document.

* **phases**: consecutive rows of `phases_of_play` with the same
  `team_in_possession_id` whose frames touch, merged into one possession.
* **chain**: the span from the `player_possession` the provider flags with
  `first_player_possession_in_team_possession` to the last one before the next
  such flag. This is not an inference: those flags are the provider delimiting
  its own team possessions.

The referee is `tracking_frames.possession_group`, which says `home team` or
`away team` for each frame and is produced by neither rule. Two numbers come out
of it per match: how much of what the provider itself calls possession a rule
covers, and how often the rule and the tracking name the same team on a frame
they both claim.

What the probe does not do is measure coverage of every in-play frame, which is
what the plan's acceptance asked for. The provider attributes a team to only
71.25% of the frames where the ball has a position, so no rule can reach 90%
without inventing an owner for the other 29%; that figure is reported per match
and the bar sits on the denominators that mean something.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

RULES = ("phases", "chain")
CHOSEN_RULE = "chain"

# Merge consecutive phases of the same team whose frames touch. A phase ends where
# the next begins (they share a frame), so this rule's possessions share it too.
_PHASES_SQL = """
WITH marked AS (
    SELECT
        match_id, period, team_in_possession_id AS team_id, frame_start, frame_end,
        CASE
            WHEN team_in_possession_id = lag(team_in_possession_id) OVER w
                 AND frame_start <= lag(frame_end) OVER w + 1 THEN 0
            ELSE 1
        END AS is_new
    FROM phases_of_play
    WINDOW w AS (PARTITION BY match_id, period ORDER BY frame_start)
),
grouped AS (
    SELECT *, sum(is_new) OVER (PARTITION BY match_id, period ORDER BY frame_start) AS grp
    FROM marked
)
SELECT
    match_id,
    any_value(period) AS period,
    any_value(team_id) AS team_id,
    min(frame_start) AS frame_start,
    max(frame_end) AS frame_end,
    count(*) AS n_parts
FROM grouped
GROUP BY match_id, period, grp
"""

# Open a possession on each flagged first player_possession and close it on the
# row before the next one. The provider's own chain, read rather than inferred.
_CHAIN_SQL = """
WITH touches AS (
    SELECT
        match_id, period, team_id, frame_start, frame_end,
        first_player_possession_in_team_possession AS opens,
        row_number() OVER (PARTITION BY match_id ORDER BY frame_start, event_id) AS rn
    FROM dynamic_events
    WHERE event_type = 'player_possession'
),
opened AS (
    SELECT *, sum(CASE WHEN opens THEN 1 ELSE 0 END) OVER (PARTITION BY match_id ORDER BY rn) AS grp
    FROM opened_source
)
SELECT
    match_id,
    any_value(period) AS period,
    any_value(team_id) AS team_id,
    min(frame_start) AS frame_start,
    max(frame_end) AS frame_end,
    count(*) AS n_parts
FROM opened
WHERE grp > 0
GROUP BY match_id, grp
"""


def rule_sql(rule: str) -> str:
    """The SQL of one rule, as a SELECT over the bronze views this module creates."""
    if rule == "phases":
        return _PHASES_SQL
    if rule == "chain":
        return _CHAIN_SQL.replace("FROM opened_source", "FROM touches")
    raise ValueError(f"unknown possession rule {rule!r} (known: {', '.join(RULES)})")


@dataclass(frozen=True)
class RuleScore:
    rule: str
    native_match_id: int
    possessions: int
    inplay_frames: int
    inplay_covered_pct: float
    provider_frames: int
    provider_covered_pct: float
    agree_pct: float
    overlapping_possessions: int
    frame_start_outside_period: int


def _views(con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
    bronze = data_dir / "bronze" / "football"
    for table in ("phases_of_play", "dynamic_events", "tracking_frames", "match", "match_periods"):
        glob = (bronze / table / "*.parquet").as_posix()
        if not list((bronze / table).glob("*.parquet")):
            raise FileNotFoundError(f"{bronze / table} is empty; run `tracklab bronze football`")
        con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet('{glob}')")
    con.execute(
        """
        CREATE OR REPLACE VIEW inplay AS
        SELECT t.match_id, t.frame,
               CASE t.possession_group
                   WHEN 'home team' THEN m.home_team_id
                   WHEN 'away team' THEN m.away_team_id
               END AS provider_team_id
        FROM tracking_frames t
        JOIN match m ON m.id = t.match_id
        WHERE t.period IS NOT NULL AND t.ball_x IS NOT NULL
        """
    )


def score_rule(con: duckdb.DuckDBPyConnection, rule: str) -> list[RuleScore]:
    """One row per match: how many possessions the rule makes, how much of the match
    they cover, and how often they name the team the tracking names."""
    con.execute(f"CREATE OR REPLACE VIEW candidate AS {rule_sql(rule)}")
    rows = con.execute(
        """
        WITH frames AS (
            SELECT i.match_id, i.frame, i.provider_team_id,
                   -- a frame claimed by two possessions is counted once, by the first
                   min_by(c.team_id, c.frame_start) AS rule_team_id
            FROM inplay i
            LEFT JOIN candidate c
              ON c.match_id = i.match_id AND i.frame BETWEEN c.frame_start AND c.frame_end
            GROUP BY ALL
        ),
        per_match AS (
            SELECT
                match_id,
                count(*) AS inplay_frames,
                count(*) FILTER (WHERE rule_team_id IS NOT NULL) AS covered,
                count(*) FILTER (WHERE provider_team_id IS NOT NULL) AS provider_frames,
                count(*) FILTER (
                    WHERE provider_team_id IS NOT NULL AND rule_team_id IS NOT NULL
                ) AS both,
                count(*) FILTER (WHERE provider_team_id = rule_team_id) AS agree
            FROM frames GROUP BY ALL
        ),
        neighboured AS (
            SELECT match_id, frame_start,
                   lag(frame_end) OVER (PARTITION BY match_id ORDER BY frame_start) AS previous_end
            FROM candidate
        ),
        counted AS (
            SELECT match_id, count(*) AS possessions,
                   count(*) FILTER (WHERE frame_start <= previous_end) AS overlapping
            FROM neighboured GROUP BY ALL
        ),
        outside AS (
            SELECT c.match_id, count(*) FILTER (
                       WHERE p.period IS NULL
                          OR c.frame_start < p.start_frame OR c.frame_start > p.end_frame
                   ) AS bad_starts
            FROM candidate c
            LEFT JOIN match_periods p ON p.match_id = c.match_id AND p.period = c.period
            GROUP BY ALL
        )
        SELECT m.match_id, c.possessions, m.inplay_frames,
               round(100.0 * m.covered / m.inplay_frames, 2),
               m.provider_frames,
               round(100.0 * m.both / nullif(m.provider_frames, 0), 2),
               round(100.0 * m.agree / nullif(m.both, 0), 2),
               c.overlapping, o.bad_starts
        FROM per_match m
        JOIN counted c USING (match_id)
        JOIN outside o USING (match_id)
        ORDER BY 1
        """
    ).fetchall()
    return [
        RuleScore(
            rule,
            int(r[0]),
            int(r[1]),
            int(r[2]),
            float(r[3]),
            int(r[4]),
            float(r[5]),
            float(r[6]),
            int(r[7]),
            int(r[8]),
        )
        for r in rows
    ]


def report_path(reports_dir: Path) -> Path:
    return reports_dir / "possessions_football.csv"


def run_possessions(data_dir: Path, reports_dir: Path) -> int:
    con = duckdb.connect()
    _views(con, data_dir)

    scores: list[RuleScore] = []
    for rule in RULES:
        by_match = score_rule(con, rule)
        scores.extend(by_match)
        possessions = sum(s.possessions for s in by_match)
        provider = sum(s.provider_frames for s in by_match)
        covered = sum(round(s.provider_frames * s.provider_covered_pct / 100) for s in by_match)
        overlapping = sum(s.overlapping_possessions for s in by_match)
        bad_starts = sum(s.frame_start_outside_period for s in by_match)
        worst_agree = min(s.agree_pct for s in by_match)
        print(
            f"possessions {rule}: {possessions} in {len(by_match)} matches; "
            f"{round(100.0 * covered / provider, 2)}% of the frames the provider calls "
            f"possession; agreement {worst_agree}% in the worst match; "
            f"{overlapping} overlapping, {bad_starts} starting outside their period"
        )
        for score in by_match:
            print(
                f"possessions {rule} {score.native_match_id}: {score.possessions} "
                f"covering {score.provider_covered_pct}% of provider frames "
                f"({score.inplay_covered_pct}% of in-play), agreement {score.agree_pct}%, "
                f"{score.overlapping_possessions} overlapping"
            )

    report = report_path(reports_dir)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(scores[0])), lineterminator="\n")
        writer.writeheader()
        writer.writerows([asdict(s) for s in scores])
    print(f"report: {report} ({len(scores)} rows)")

    chosen = [s for s in scores if s.rule == CHOSEN_RULE]
    failures = [s for s in chosen if s.overlapping_possessions or s.frame_start_outside_period]
    for score in failures:
        print(
            f"FAIL possessions {CHOSEN_RULE} {score.native_match_id}: "
            f"{score.overlapping_possessions} overlapping, "
            f"{score.frame_start_outside_period} starting outside their period"
        )
    if failures:
        print(f"possessions: {len(failures)} match(es) failed the chosen rule's invariants")
        return 1
    print(f"possessions: {CHOSEN_RULE} holds in {len(chosen)} matches")
    return 0
