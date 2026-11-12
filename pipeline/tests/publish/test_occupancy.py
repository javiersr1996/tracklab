"""`tracklab publish occupancy` (task 184b) on a tiny synthetic silver.

Two matches outside the fence, `900001` on a 105 by 68 m pitch and `900002` on a 106 by 68 m one.
Team `fb:1` attacks +x in period 1 and -x in period 2, team `fb:2` the other way. Every expected
cell is worked out by hand below: col = floor((x + 52.5) * 30 / 105), row = floor((y + 34) * 20 /
68), cell = row * 30 + col, with (x, y) the venue position times the team's sign (and, on the 106 m
pitch, x times 105 / 106).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import duckdb
import pytest

from tracklab.cli import main
from tracklab.learn.possession import held_out
from tracklab.paths import data_root
from tracklab.publish import occupancy
from tracklab.publish.occupancy import (
    GROUPS,
    OCCUPANCY_JSON,
    OUTFIELD,
    SHARE_SCALE,
    FenceError,
    build,
    matches_at_hand,
    run_publish_occupancy,
    shares,
)

WEB_DATA = Path(__file__).resolve().parents[3] / "web" / "public" / "data"
A, B = "900001", "900002"

# (id, position_group, player_role_name): one player per group, a goalkeeper and a substitute.
PLAYERS = [
    (11, "Central Defender", "Left Center Back"),
    (12, "Full Back", "Right Back"),
    (13, "Midfield", "Defensive Midfield"),
    (14, "Wide Attacker", "Left Winger"),
    (15, "Center Forward", "Center Forward"),
    (16, "Other", "Goalkeeper"),
    (17, "Other", "Substitute"),
]
TEAM = {11: "fb:1", 12: "fb:1", 13: "fb:1", 14: "fb:2", 15: "fb:2", 16: "fb:1", 17: "fb:2"}


def _write(con: duckdb.DuckDBPyConnection, path: Path, columns: str, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"CREATE OR REPLACE TABLE t ({columns})")
    con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(rows[0]))})", rows)
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT parquet)")


def frame_rows(match: str, positions: list[tuple[int, int, int, float | None, float | None]]):
    """(period, frame, player, x, y) to silver frames rows, plus the ball in every frame."""
    rows = [
        (f"fb:{match}", period, frame, f"fb:{pid}", "player", TEAM[pid], x, y)
        for period, frame, pid, x, y in positions
    ]
    frames = sorted({(p, f) for p, f, *_ in positions})
    rows += [(f"fb:{match}", p, f, "fb:ball", "ball", None, 99.0, 99.0) for p, f in frames]
    return rows


def make_silver(root: Path, positions: dict[str, list]) -> Path:
    con = duckdb.connect()
    frame_cols = (
        "match_id VARCHAR, period SMALLINT, frame_native BIGINT, entity_id VARCHAR, "
        "entity_kind VARCHAR, team_id VARCHAR, x_m DOUBLE, y_m DOUBLE"
    )
    for match, rows in positions.items():
        part = root / "silver" / "frames" / "sport=football" / f"native_match_id={match}"
        _write(con, part / "data_0.parquet", frame_cols, frame_rows(match, rows))
        _write(
            con,
            root / "bronze" / "football" / "match_players" / f"{match}.parquet",
            "id BIGINT, position_group VARCHAR, player_role_name VARCHAR",
            PLAYERS,
        )
    signs = [
        (f"fb:{m}", period, team, sign)
        for m in positions
        for period, team, sign in ((1, "fb:1", 1), (1, "fb:2", -1), (2, "fb:1", -1), (2, "fb:2", 1))
    ]
    _write(
        con,
        root / "silver" / "dim_team_period" / "data.parquet",
        "match_id VARCHAR, period SMALLINT, team_id VARCHAR, attack_sign SMALLINT",
        signs,
    )
    lengths = {A: 105.0, B: 106.0}
    _write(
        con,
        root / "silver" / "dim_match" / "data.parquet",
        "match_id VARCHAR, competition VARCHAR, season VARCHAR, surface_length_m DOUBLE, "
        "surface_width_m DOUBLE",
        [(f"fb:{m}", "Toy League", "2024/2025", lengths[m], 68.0) for m in positions],
    )
    _write(
        con,
        root / "silver" / "dim_sport" / "data.parquet",
        "sport VARCHAR, sample_rate_hz INTEGER",
        [("football", 10), ("basketball", 25)],
    )
    return root


def every_group(frame: int, but: tuple[int, ...] = ()) -> list:
    """One frame of period 1 with each player but `but` at the centre spot: cell 10 * 30 + 15 =
    315 for every group. The publisher refuses a group with no player-frame, so a test about one
    group fills the others with this."""
    return [(1, frame, pid, 0.0, 0.0) for pid, *_ in PLAYERS if pid not in but]


def cells(payload: dict, group: str) -> dict[int, int]:
    block = next(g for g in payload["groups"] if g["group"] == group)
    return {i: s for i, s in enumerate(block["share"]) if s}


def group(payload: dict, name: str) -> dict:
    return next(g for g in payload["groups"] if g["group"] == name)


def test_shares_are_the_largest_remainder_and_sum_to_the_scale() -> None:
    # 1/3 each: 33333 + 33333 + 33333 = 99999, the one left goes to the lower cell (ties).
    assert shares(Counter({0: 1, 1: 1, 2: 1}), cells=4) == [33334, 33333, 33333, 0]
    # 2/3 and 1/3 of 100: 66.67 and 33.33, floors 66 + 33, the remainder to cell 0 (2/3 > 1/3).
    assert shares(Counter({0: 2, 3: 1}), cells=4, scale=100) == [67, 0, 0, 33]
    with pytest.raises(ValueError):
        shares(Counter(), cells=4)


def test_every_group_sums_to_the_scale_and_the_outfield_pools_the_five(tmp_path: Path) -> None:
    root = make_silver(
        tmp_path, {A: every_group(1) + every_group(2) + [(1, 3, 13, 40.0, 0.0)], B: every_group(1)}
    )
    payload = build(root, [A, B])
    assert [g["group"] for g in payload["groups"]] == [*GROUPS, OUTFIELD]
    for g in payload["groups"]:
        assert sum(g["share"]) == SHARE_SCALE, g["group"]
        assert len(g["share"]) == 600
    # Midfield: three frames at the centre spot (cell 315) and one at x = 40 for team fb:1,
    # attacking +x in period 1: col floor(92.5 * 30 / 105) = 26, row 10, cell 326.
    assert cells(payload, "Midfield") == {315: 75_000, 326: 25_000}
    assert group(payload, "Midfield")["player_frames"] == 4
    # Outfield: 5 groups x 3 centre frames + 1 = 16 player-frames, 15 of them in cell 315.
    assert cells(payload, OUTFIELD) == {315: 93_750, 326: 6_250}
    assert group(payload, OUTFIELD)["player_frames"] == 16
    assert group(payload, OUTFIELD)["player_matches"] == 10  # five players in each of two matches
    assert payload["left_out"] == {"goalkeeper": 3, "no_group": 3}
    assert payload["frames"] == 4  # three in A, one in B
    assert payload["matches"] == [A, B]
    assert payload["grid"]["pitches"] == [
        {"length_m": 105.0, "width_m": 68.0, "matches": 1},
        {"length_m": 106.0, "width_m": 68.0, "matches": 1},
    ]


def test_attack_normalisation_turns_the_team_attacking_minus_x(tmp_path: Path) -> None:
    root = make_silver(
        tmp_path,
        {
            A: [
                # fb:1 attacks +x in period 1: (40, 10) stays, col 26, row floor(44 * 20 / 68) = 12.
                (1, 1, 11, 40.0, 10.0),
                # fb:2 attacks -x in period 1: (40, 10) turns to (-40, -10), col floor(12.5 * 30 /
                # 105) = 3, row floor(24 * 20 / 68) = 7, the own half and the right flank.
                (1, 1, 14, 40.0, 10.0),
                # Period 2 swaps the signs: fb:1's (40, 10) turns to (-40, -10), cell 7 * 30 + 3.
                (2, 2, 11, 40.0, 10.0),
                # fb:2 attacks +x in period 2: (40, 10) stays, cell 12 * 30 + 26.
                (2, 2, 14, 40.0, 10.0),
                *every_group(3, but=(11, 14)),
            ]
        },
    )
    payload = build(root, [A])
    assert cells(payload, "Central Defender") == {12 * 30 + 26: 50_000, 7 * 30 + 3: 50_000}
    assert cells(payload, "Wide Attacker") == {7 * 30 + 3: 50_000, 12 * 30 + 26: 50_000}


def test_off_pitch_and_missing_are_counted_not_binned(tmp_path: Path) -> None:
    root = make_silver(
        tmp_path,
        {
            A: [
                (1, 1, 15, 53.0, 0.0),  # past the goal line of a 105 m pitch: off
                (1, 2, 15, 0.0, -34.5),  # past the touchline: off
                (1, 3, 15, None, 0.0),  # no x: missing
                # On both lines: binned. fb:2 attacks -x in period 1, so (52.5, 34) turns to
                # (-52.5, -34), the corner cell 0.
                (1, 4, 15, 52.5, 34.0),
                # (-10, 0) turns to (10, 0): col floor(62.5 * 30 / 105) = 17, row 10, cell 317.
                (1, 5, 15, -10.0, 0.0),
                *every_group(6, but=(15,)),
            ],
            # The 106 m pitch: 53 is on its goal line, binned; turned to -53 and scaled to -52.5,
            # col 0, row 10, cell 300. 53.1 is past it.
            B: [(1, 1, 15, 53.0, 0.0), (1, 2, 15, 53.1, 0.0)],
        },
    )
    payload = build(root, [A, B])
    cf = group(payload, "Center Forward")
    assert (cf["off_pitch"], cf["missing"], cf["player_frames"]) == (3, 1, 3)
    # Three binned frames, a third each; the unit left over goes to the lower cell.
    assert cells(payload, "Center Forward") == {0: 33_334, 300: 33_333, 317: 33_333}


def test_a_held_out_match_is_refused_and_never_opened(tmp_path: Path) -> None:
    fenced = sorted(held_out())[0]
    root = make_silver(tmp_path, {A: every_group(1)})
    # A held-out partition whose file is not even Parquet: opening it would fail loudly.
    part = root / "silver" / "frames" / "sport=football" / f"native_match_id={fenced}"
    part.mkdir(parents=True)
    (part / "data_0.parquet").write_bytes(b"not parquet")
    (root / "bronze" / "football" / "match_players" / f"{fenced}.parquet").write_bytes(b"x")
    assert matches_at_hand(root) == [A]
    # Refused before anything is read: with no data root at all the answer is still the fence.
    with pytest.raises(FenceError):
        build(tmp_path / "nothing", [fenced])
    with pytest.raises(FenceError):
        build(root, [A, fenced])
    with pytest.raises(FenceError):
        occupancy.Tally().add_match(duckdb.connect(), root, fenced)
    out = tmp_path / "web"
    assert run_publish_occupancy(root, out) == 0
    assert json.loads((out / OCCUPANCY_JSON).read_text("utf-8"))["matches"] == [A]


def test_check_is_full_on_every_match_and_partial_on_a_slice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_silver(tmp_path, {A: every_group(1), B: every_group(1)})
    out = tmp_path / "web"
    assert run_publish_occupancy(root, out) == 0
    raw = (out / OCCUPANCY_JSON).read_bytes()
    assert b"\r" not in raw
    assert run_publish_occupancy(root, out, check=True) == 0
    assert "FULL 2/2" in capsys.readouterr().out

    # A changed byte fails.
    (out / OCCUPANCY_JSON).write_bytes(raw.replace(b'"frames": 2', b'"frames": 3'))
    assert run_publish_occupancy(root, out, check=True) == 1
    (out / OCCUPANCY_JSON).write_bytes(raw)

    # A match of the file not at hand: the code runs on the rest, PARTIAL 1/2, which
    # TRACKLAB_REQUIRE_FULL turns into a failure.
    for f in (root / "silver" / "frames" / "sport=football" / f"native_match_id={B}").iterdir():
        f.unlink()
    assert run_publish_occupancy(root, out, check=True) == 0
    assert "PARTIAL 1/2" in capsys.readouterr().out
    argv = ["publish", "occupancy", "--check", "--data-dir", str(root), "--out-dir", str(out)]
    monkeypatch.setenv("TRACKLAB_REQUIRE_FULL", "1")
    assert main(argv) == 1


def test_check_fails_on_a_file_that_names_a_held_out_match(tmp_path: Path) -> None:
    root = make_silver(tmp_path, {A: every_group(1)})
    out = tmp_path / "web"
    assert run_publish_occupancy(root, out) == 0
    payload = json.loads((out / OCCUPANCY_JSON).read_text("utf-8"))
    payload["matches"].append(sorted(held_out())[0])
    (out / OCCUPANCY_JSON).write_text(occupancy.render(payload), "utf-8", newline="\n")
    assert run_publish_occupancy(root, out, check=True) == 1


built = pytest.mark.skipif(
    not (WEB_DATA / OCCUPANCY_JSON).is_file()
    or not set(json.loads((WEB_DATA / OCCUPANCY_JSON).read_text("utf-8"))["matches"])
    <= set(matches_at_hand(data_root())),
    reason="needs the silver frames of every match occupancy.json names",
)


@built
def test_the_committed_occupancy_file_is_what_silver_gives(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_publish_occupancy(data_root(), WEB_DATA, check=True) == 0
    assert "FULL 10/10" in capsys.readouterr().out
