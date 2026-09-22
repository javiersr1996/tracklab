"""The two football possession rules on a fabricated match.

Eight touches and five phases are enough to show what neither bundle can: a
phase pair that must not merge because a frame separates them, touches that
arrive before the provider has flagged any team possession, and a rule that
covers a match the tracking attributes to nobody. The real bundles are scored by
`tracklab possessions` and pinned by the contract tests.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tracklab.silver.possessions import (
    CHOSEN_RULE,
    RULES,
    report_path,
    rule_sql,
    run_possessions,
)

HOME, AWAY = 10, 20


def _write(root: Path, table: str, rows: str, columns: str) -> None:
    path = root / "bronze" / "football" / table
    path.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(
        f"COPY (SELECT * FROM (VALUES {rows}) AS t({columns})) "
        f"TO '{(path / 'data.parquet').as_posix()}' (FORMAT PARQUET)"
    )


def _bundle(
    root: Path,
    *,
    touches: str,
    phases: str,
    tracking: str,
) -> None:
    _write(root, "match", f"(1, {HOME}, {AWAY})", "id, home_team_id, away_team_id")
    _write(root, "match_periods", "(1, 1, 0, 1000)", "match_id, period, start_frame, end_frame")
    _write(
        root,
        "phases_of_play",
        phases,
        "match_id, period, team_in_possession_id, frame_start, frame_end",
    )
    _write(
        root,
        "dynamic_events",
        touches,
        "match_id, period, team_id, event_id, event_type, frame_start, frame_end, "
        "first_player_possession_in_team_possession",
    )
    _write(root, "tracking_frames", tracking, "match_id, frame, period, ball_x, possession_group")


def _frames(spec: list[tuple[int, str | None]]) -> str:
    return ", ".join(
        f"(1, {frame}, 1, 0.0, {'NULL' if group is None else repr(group)})" for frame, group in spec
    )


def test_an_unknown_rule_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="unknown possession rule"):
        rule_sql("whatever")
    assert set(RULES) == {"phases", "chain"}
    assert CHOSEN_RULE in RULES


def test_the_chain_rule_drops_the_touches_before_the_first_flag(tmp_path: Path) -> None:
    """A match can open with touches the provider has not enclosed in a team
    possession yet, and those belong to none rather than to the first one."""
    _bundle(
        tmp_path,
        touches=(
            "(1, 1, 10, 'a', 'player_possession', 10, 19, false), "
            "(1, 1, 10, 'b', 'player_possession', 20, 29, true), "
            "(1, 1, 10, 'c', 'player_possession', 30, 39, false), "
            "(1, 1, 20, 'd', 'player_possession', 40, 49, true)"
        ),
        phases="(1, 1, 10, 20, 39), (1, 1, 20, 40, 49)",
        tracking=_frames([(f, "home team") for f in range(10, 50)]),
    )
    con = duckdb.connect()
    for table in ("phases_of_play", "dynamic_events"):
        glob = (tmp_path / "bronze" / "football" / table / "*.parquet").as_posix()
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{glob}')")

    rows = con.execute(f"{rule_sql('chain')} ORDER BY frame_start").fetchall()

    print(rows)
    assert [(r[3], r[4], r[2]) for r in rows] == [(20, 39, 10), (40, 49, 20)]


def test_the_phases_rule_merges_only_what_touches(tmp_path: Path) -> None:
    """Two phases of the same team merge when they touch and stay apart when a
    frame separates them, which is the whole content of that rule."""
    _bundle(
        tmp_path,
        touches="(1, 1, 10, 'a', 'player_possession', 10, 19, true)",
        phases=(
            "(1, 1, 10, 10, 19), "  # merges with the next: they touch
            "(1, 1, 10, 19, 29), "
            "(1, 1, 10, 40, 49), "  # same team, but 10 frames later
            "(1, 1, 20, 50, 59)"
        ),
        tracking=_frames([(f, "home team") for f in range(10, 60)]),
    )
    con = duckdb.connect()
    for table in ("phases_of_play", "dynamic_events"):
        glob = (tmp_path / "bronze" / "football" / table / "*.parquet").as_posix()
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{glob}')")

    rows = con.execute(f"{rule_sql('phases')} ORDER BY frame_start").fetchall()

    print(rows)
    assert [(r[3], r[4], r[5]) for r in rows] == [(10, 29, 2), (40, 49, 1), (50, 59, 1)]


def test_scores_both_rules_and_writes_them_down(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The chosen rule holds, so the command succeeds and both rules land in the
    report: the loser's figures are the reason the winner is the winner."""
    _bundle(
        tmp_path,
        touches=(
            "(1, 1, 10, 'a', 'player_possession', 10, 19, true), "
            "(1, 1, 20, 'b', 'player_possession', 30, 39, true)"
        ),
        phases="(1, 1, 10, 10, 19), (1, 1, 20, 30, 39)",
        tracking=_frames(
            [(f, "home team") for f in range(10, 20)]
            + [(f, None) for f in range(20, 30)]
            + [(f, "away team") for f in range(30, 40)]
        ),
    )

    assert run_possessions(tmp_path, tmp_path / "reports") == 0

    out = capsys.readouterr().out
    assert "possessions: chain holds in 1 matches" in out
    text = report_path(tmp_path / "reports").read_text(encoding="utf-8").splitlines()
    print("\n".join(text))
    header = text[0].split(",")
    assert len(text) == 1 + len(RULES)
    # Both rules find the same two possessions here, both agree with the tracking,
    # and neither overlaps or starts outside its period.
    for row in text[1:]:
        fields = dict(zip(header, row.split(","), strict=True))
        assert fields["possessions"] == "2"
        assert fields["agree_pct"] == "100.0"
        assert fields["overlapping_possessions"] == "0"
        assert fields["frame_start_outside_period"] == "0"


def test_a_possession_that_starts_outside_its_period_fails_the_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The invariant the command exists to guard. Period 1 runs to frame 1000 here,
    so a touch flagged at frame 2000 opens a possession that cannot be placed."""
    _bundle(
        tmp_path,
        touches=(
            "(1, 1, 10, 'a', 'player_possession', 10, 19, true), "
            "(1, 1, 20, 'b', 'player_possession', 2000, 2009, true)"
        ),
        phases="(1, 1, 10, 10, 19)",
        tracking=_frames([(f, "home team") for f in range(10, 20)]),
    )

    assert run_possessions(tmp_path, tmp_path / "reports") == 1

    out = capsys.readouterr().out
    assert "FAIL possessions chain 1" in out
    assert "1 starting outside their period" in out


def test_a_missing_bronze_table_says_which_command_to_run(tmp_path: Path) -> None:
    (tmp_path / "bronze" / "football" / "phases_of_play").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="tracklab bronze football"):
        run_possessions(tmp_path, tmp_path / "reports")
