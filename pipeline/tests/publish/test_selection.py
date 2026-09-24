"""Task 17's selection rules, on fabricated silver/bronze tables.

The real bundle is exercised end to end by `test_contract.py` (skipped without
`pipeline/data`); this file's job is to prove each filter bites on a shape the
20 real matches may never happen to show, in particular the coverage bar the
plan asks for: a possession one player under-detects at 89% must be excluded
while an otherwise identical 90%-or-better one is kept. A test that only ever
sees real data passing every filter would not tell 90% from "no floor at
all".
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tracklab.publish.possessions import (
    COVERAGE_PCT,
    Candidate,
    basketball_candidates,
    football_candidates,
    register_basketball_chances_view,
    register_candidate_views,
    select_six,
)


def _write(path: Path, sql: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(f"COPY ({sql}) TO '{path.as_posix()}' (FORMAT PARQUET)")


def _entities_cte(offense: str, defense: str) -> str:
    rows = ", ".join(f"('{p}', 'player', '{offense}')" for p in ["p1", "p2", "p3", "p4", "p5"])
    rows += ", " + ", ".join(
        f"('{p}', 'player', '{defense}')" for p in ["p6", "p7", "p8", "p9", "p10"]
    )
    rows += ", ('ball', 'ball', NULL)"
    return f"(VALUES {rows}) AS ent(entity_id, entity_kind, team_id)"


class TestBasketballCoverage:
    """Two possessions, both `usable`/`qualityIndex=5`/`ptsScored>0`, both
    8-20s: one where every player and the ball clear the 90% bar, one where a
    single player sits at exactly 89% detected. Only the first must survive.
    """

    MATCH = "bb:1"
    NATIVE_MATCH = 1
    N_FRAMES = 500  # (500 - 1) / 25 fps = 19.96 s: inside [8, 20]
    DETECTED = 445  # 445 / 500 = 89.0%: under the 90% bar by exactly one point

    def _bundle(self, root: Path) -> None:
        _write(
            root / "silver" / "events" / "data.parquet",
            f"""
            SELECT * FROM (VALUES
                ('basketball', {self.NATIVE_MATCH}, '{self.MATCH}', 'possessions', 'p-good',
                 'bb:possessions:p-good', 'possession', 1, 0, {self.N_FRAMES - 1}, 'bb:100'),
                ('basketball', {self.NATIVE_MATCH}, '{self.MATCH}', 'possessions', 'p-bad',
                 'bb:possessions:p-bad', 'possession', 1, 1000,
                 {1000 + self.N_FRAMES - 1}, 'bb:100')
            ) AS t(sport, native_match_id, match_id, native_family, native_event_id, event_id,
                   event_type, period, frame_start, frame_end, team_id)
            """,
        )
        _write(
            root / "bronze" / "basketball" / "events_chances" / "data.parquet",
            f"""
            SELECT * FROM (VALUES
                ({self.NATIVE_MATCH}, 'p-good', true, 5, 2),
                ({self.NATIVE_MATCH}, 'p-bad', true, 5, 2)
            ) AS t(gameId, possessionId, usable, qualityIndex, ptsScored)
            """,
        )
        ent = _entities_cte("bb:100", "bb:200")
        _write(
            root / "silver" / "frames" / "data.parquet",
            f"""
            WITH good AS (
                SELECT '{self.MATCH}' AS match_id, {self.NATIVE_MATCH} AS native_match_id,
                       f AS frame_native, entity_id, entity_kind, true AS is_detected
                FROM range(0, {self.N_FRAMES}) r(f) CROSS JOIN {ent}
            ),
            bad AS (
                SELECT '{self.MATCH}', {self.NATIVE_MATCH}, 1000 + f, entity_id, entity_kind,
                       -- exactly 89% detected for p1, everyone else and the ball at 100%
                       CASE WHEN entity_id = 'p1' THEN f < {self.DETECTED} ELSE true END
                FROM range(0, {self.N_FRAMES}) r(f) CROSS JOIN {ent}
            )
            SELECT match_id, native_match_id, frame_native, entity_id, entity_kind, is_detected
            FROM good
            UNION ALL
            SELECT * FROM bad
            """,
        )

    def test_the_89_percent_possession_is_excluded_the_100_percent_one_is_kept(
        self, tmp_path: Path
    ) -> None:
        self._bundle(tmp_path)
        con = duckdb.connect()
        register_candidate_views(con, tmp_path)
        register_basketball_chances_view(con, tmp_path)

        candidates, funnel = basketball_candidates(con)

        assert funnel.quality == 2  # both possessions pass usable/qualityIndex/ptsScored
        assert funnel.duration == 2  # both are 8.0s, inside [8, 20]
        by_id = {c.possession_id: c for c in candidates}
        assert set(by_id) == {"bb:possessions:p-good"}
        good = by_id["bb:possessions:p-good"]
        assert good.min_player_coverage_pct == 100.0
        assert good.ball_coverage_pct == 100.0

    def test_the_excluded_possessions_own_number_is_89_not_something_close(
        self, tmp_path: Path
    ) -> None:
        """The bad possession is dropped for a reason this test can name: its
        worst player sits at exactly 89%, one point under the bar, not at some
        unrelated 0% that would prove nothing about the threshold itself."""
        self._bundle(tmp_path)
        con = duckdb.connect()
        register_candidate_views(con, tmp_path)
        register_basketball_chances_view(con, tmp_path)

        # Re-run the raw SQL without the coverage filter to read the number the
        # public function discards, so the test does not just trust the filter
        # it is trying to verify.
        from tracklab.publish.possessions import _BASKETBALL_CANDIDATES_SQL

        sql = _BASKETBALL_CANDIDATES_SQL.format(fps=25.0, lo=8.0, hi=20.0)
        rows = {r[0]: r[9] for r in con.execute(sql).fetchall()}
        assert rows["bb:possessions:p-bad"] == 89.0
        assert rows["bb:possessions:p-good"] == 100.0
        assert 89.0 < COVERAGE_PCT


def test_a_missing_bronze_table_says_which_command_to_run(tmp_path: Path) -> None:
    """`chances` is bronze, not silver, and the one table `dbt build` cannot
    produce: the message has to point at `tracklab bronze basketball` instead."""
    with pytest.raises(FileNotFoundError, match="tracklab bronze basketball"):
        register_basketball_chances_view(duckdb.connect(), tmp_path)


def test_a_missing_silver_table_says_which_dbt_select_to_run(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="dbt build --select events"):
        register_candidate_views(duckdb.connect(), tmp_path)


class TestFootballCoverage:
    """A derived possession containing a `team_possession_lead_to_shot` phase,
    10-25s, must have its 22 players and the ball present in 90% or more of
    its frames -- 'presentes', per the plan's own wording for football, not
    `is_detected` (task 4 already found football's players are binary at the
    frame level and intermittent only in `is_detected`)."""

    MATCH = "fb:1"
    NATIVE_MATCH = 1
    N_FRAMES = 150  # 150 / 10 fps = 15.0 s

    def _entities_22(self) -> str:
        home = ", ".join(f"('h{i}', 'player', 'fb:100')" for i in range(1, 12))
        away = ", ".join(f"('a{i}', 'player', 'fb:200')" for i in range(1, 12))
        values = f"{home}, {away}, ('ball', 'ball', NULL)"
        return f"(VALUES {values}) AS ent(entity_id, entity_kind, team_id)"

    def _bundle(self, root: Path, *, missing_player_frames: int) -> None:
        _write(
            root / "silver" / "events" / "data.parquet",
            f"""
            SELECT * FROM (VALUES
                ('football', {self.NATIVE_MATCH}, '{self.MATCH}', 'possession', NULL,
                 'fb:possession:1:1', 'possession', 'fb:possession:1:1',
                 1, 0, {self.N_FRAMES - 1}, 'fb:100', NULL),
                ('football', {self.NATIVE_MATCH}, '{self.MATCH}', 'phases_of_play', '7',
                 'fb:phases_of_play:1:7', 'other', 'fb:possession:1:1',
                 1, 10, 40, 'fb:100', 'shot'),
                ('football', {self.NATIVE_MATCH}, '{self.MATCH}', 'possession', NULL,
                 'fb:possession:1:2', 'possession', 'fb:possession:1:2',
                 1, 1000, {1000 + self.N_FRAMES - 1}, 'fb:100', NULL)
            ) AS t(sport, native_match_id, match_id, native_family, native_event_id, event_id,
                   event_type, possession_id, period, frame_start, frame_end, team_id, outcome)
            """,
        )
        ent = self._entities_22()
        _write(
            root / "silver" / "frames" / "data.parquet",
            f"""
            SELECT '{self.MATCH}' AS match_id, {self.NATIVE_MATCH} AS native_match_id,
                   f AS frame_native, entity_id, entity_kind, true AS is_detected
            FROM range(0, {self.N_FRAMES}) r(f) CROSS JOIN {ent}
            WHERE NOT (entity_id = 'h1' AND f < {missing_player_frames})
            """,
        )

    def test_the_possession_with_a_shot_phase_and_full_presence_is_kept(
        self, tmp_path: Path
    ) -> None:
        self._bundle(tmp_path, missing_player_frames=0)
        con = duckdb.connect()
        register_candidate_views(con, tmp_path)

        candidates, funnel = football_candidates(con)

        # Only fb:possession:1:1 contains a lead_to_shot phase; :1:2 never qualifies.
        assert funnel.quality == 1
        assert funnel.duration == 1
        assert [c.possession_id for c in candidates] == ["fb:possession:1:1"]
        assert candidates[0].min_player_coverage_pct == 100.0
        assert candidates[0].ball_coverage_pct == 100.0

    def test_a_player_missing_from_more_than_10_percent_of_frames_is_excluded(
        self, tmp_path: Path
    ) -> None:
        """h1 is absent (no row at all, not just undetected) from 16 of 150
        frames: 89.33% presence, under the bar."""
        self._bundle(tmp_path, missing_player_frames=16)
        con = duckdb.connect()
        register_candidate_views(con, tmp_path)

        candidates, funnel = football_candidates(con)

        assert funnel.quality == 1
        assert funnel.duration == 1
        assert candidates == []


def test_select_six_round_robins_across_matches_deterministically() -> None:
    """3 possessions from match A, 1 from B, 1 from C, 1 from D: picking the
    earliest-per-match first spreads the 6 across all 4 rather than taking
    A's 3 and starving the rest, and repeating the call changes nothing."""

    def make(match_id: str, frame_start: int) -> Candidate:
        return Candidate(
            possession_id=f"{match_id}:{frame_start}",
            sport="basketball",
            match_id=match_id,
            native_match_id=1,
            period=1,
            frame_start=frame_start,
            frame_end=frame_start + 100,
            team_id="bb:1",
            duration_s=10.0,
            n_players=10,
            min_player_coverage_pct=100.0,
            ball_coverage_pct=100.0,
        )

    candidates = [
        make("bb:a", 300),
        make("bb:a", 100),
        make("bb:a", 200),
        make("bb:b", 50),
        make("bb:c", 10),
        make("bb:d", 5),
    ]

    picked = select_six(candidates)

    assert len(picked) == 6
    assert {c.match_id for c in picked} == {"bb:a", "bb:b", "bb:c", "bb:d"}
    # The single possession of b, c and d always makes it in before a's 2nd or 3rd.
    assert sum(1 for c in picked if c.match_id == "bb:a") == 3
    assert select_six(candidates) == picked  # deterministic


def test_select_six_reports_short_when_fewer_than_six_exist() -> None:
    def make(match_id: str) -> Candidate:
        return Candidate(
            possession_id=match_id,
            sport="basketball",
            match_id=match_id,
            native_match_id=1,
            period=1,
            frame_start=0,
            frame_end=100,
            team_id="bb:1",
            duration_s=10.0,
            n_players=10,
            min_player_coverage_pct=100.0,
            ball_coverage_pct=100.0,
        )

    picked = select_six([make("bb:a"), make("bb:b")])
    assert len(picked) == 2
