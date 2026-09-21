"""freeze-schema football on a synthetic two-match bundle. No real data, no network.

The bundle is built to a known truth (clock rule, 22-or-0 frames, ids, goalkeeper
sides, attack-normalised event coordinates, phases vs possessions) so every column
of the report can be asserted, and the second match breaks `home_team_side` on
purpose to prove the side check reports a mismatch instead of averaging it away.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb
import pytest

from tracklab.cli import main
from tracklab.formats.csvschema import freeze_csv_family, load_schema
from tracklab.formats.football import EVENT_COLUMNS, PHASE_COLUMNS, discover, probe_match
from tracklab.ingest.manifest import FileEntry, Manifest, Source, save_manifest

SOURCE_ID = "opendata-football"
COMMIT = "4340d274572876239c154c90bc507a9b3250a656"
HOME, AWAY = 10, 20
P1 = (2, 41)  # start_frame, end_frame
P2 = (44, 83)
EMPTY_EVERY = 4  # in-period frames with (frame - start) % 4 == 3 carry no players


def clock(frame: int, period: int) -> str:
    start = (P1, P2)[period - 1][0]
    cs = 45 * 60 * 100 * (period - 1) + (frame - start) * 10
    h, rest = divmod(cs, 360000)
    m, rest = divmod(rest, 6000)
    s, c = divmod(rest, 100)
    return f"{h:02d}:{m:02d}:{s:02d}.{c:02d}"


def event_clock(frame: int, period: int) -> str:
    start = (P1, P2)[period - 1][0]
    ds = 45 * 60 * 10 * (period - 1) + (frame - start)
    m, rest = divmod(ds, 600)
    s, d = divmod(rest, 10)
    return f"{m:02d}:{s:02d}.{d}"


def period_of(frame: int) -> int | None:
    for p, (a, b) in enumerate((P1, P2), start=1):
        if a <= frame <= b:
            return p
    return None


def position(player_id: int, period: int) -> tuple[float, float]:
    """Home ids 100..110 (GK 100 at x=-45 in period 1), away ids 200..210 (GK 200 at +45)."""
    home = player_id < 200
    i = player_id - (100 if home else 200)
    x = (-45.0 + 5 * i) if home else (45.0 - 5 * i)
    y = (i - 5) * 3.0 + (0.0 if home else 1.0)
    if period == 2:
        x = -x
    return x, y


def players_json() -> list[dict[str, object]]:
    players = []
    for team, base in ((HOME, 100), (AWAY, 200)):
        for i in range(11):
            pid = base + i
            players.append(
                {
                    "id": pid,
                    "team_id": team,
                    "team_player_id": pid + 5000,
                    "trackable_object": pid + 1000,
                    "player_role": {"acronym": "GK" if i == 0 else "CB", "position_group": "x"},
                }
            )
    return players


def phases_rows() -> list[dict[str, object]]:
    return [
        dict(index=0, period=1, frame_start=4, frame_end=8, team=HOME, npp=2, loss=True),
        dict(index=1, period=1, frame_start=8, frame_end=20, team=AWAY, npp=0, loss=False),
        dict(index=2, period=2, frame_start=48, frame_end=50, team=AWAY, npp=1, loss=True),
        dict(index=3, period=2, frame_start=52, frame_end=60, team=HOME, npp=1, loss=False),
    ]


def write_tracking(path: Path, n_frames: int) -> None:
    owner = {}
    for ph in phases_rows():
        for f in range(int(str(ph["frame_start"])), int(str(ph["frame_end"])) + 1):
            owner[f] = "home team" if ph["team"] == HOME else "away team"
    with path.open("w", encoding="utf-8") as fh:
        for frame in range(n_frames):
            period = period_of(frame)
            start = (P1, P2)[period - 1][0] if period else 0
            empty = period is None or (frame - start) % EMPTY_EVERY == 3
            players = []
            if not empty:
                assert period is not None
                for pid in [*range(100, 111), *range(200, 211)]:
                    x, y = position(pid, period)
                    players.append({"x": x, "y": y, "player_id": pid, "is_detected": pid % 2 == 0})
            ball = (
                {"x": None, "y": None, "z": None, "is_detected": None}
                if empty
                else {"x": 1.0, "y": 2.0, "z": -0.3 if frame == 4 else 0.5, "is_detected": True}
            )
            fh.write(
                json.dumps(
                    {
                        "frame": frame,
                        "timestamp": None if period is None else clock(frame, period),
                        "period": period,
                        "ball_data": ball,
                        "possession": {
                            "player_id": 101 if frame == 4 else None,
                            "group": None if empty else owner.get(frame),
                        },
                        "image_corners_projection": {"x_top_left": None},
                        "player_data": players,
                    }
                )
                + "\n"
            )


def event_rows(match_id: int) -> list[dict[str, object]]:
    """Events in the attack-normalised frame: raw when attacking ltr, (-x, -y) otherwise."""

    def ev(
        idx: int,
        kind: str,
        frame: int,
        pid: int,
        side: str,
        *,
        physical: int | None = None,
        phase: int | None = None,
        first: bool = False,
        last: bool = False,
        end: str = "",
        channel: str = "center",
        shot: bool = False,
    ) -> dict[str, object]:
        period = period_of(frame)
        assert period is not None
        x, y = position(pid, period)
        if side == "right_to_left":
            x, y = -x, -y
        return {
            "index": idx,
            "event_type": kind,
            "end_type": end,
            "frame_start": frame,
            "frame_end": frame + 2,
            "frame_physical_start": physical if physical is not None else frame,
            "time_start": event_clock(physical if physical is not None else frame, period),
            "period": period,
            "attacking_side": side,
            "player_id": pid,
            "team_id": HOME if pid < 200 else AWAY,
            "x_start": x,
            "y_start": y,
            "channel_start": channel,
            "phase_index": phase if phase is not None else "",
            "n_player_possessions_in_phase": "" if phase is None else 2,
            "first_player_possession_in_team_possession": first,
            "last_player_possession_in_team_possession": last,
            "lead_to_shot": shot,
            "match_id": match_id,
        }

    ltr, rtl, left = "left_to_right", "right_to_left", "wide_left"
    return [
        ev(0, "player_possession", 4, 108, ltr, phase=0, first=True, end="pass", channel=left),
        ev(1, "player_possession", 8, 102, ltr, phase=0, last=True, end="shot", shot=True),
        ev(2, "player_possession", 48, 201, ltr, phase=2, first=True, last=True, end="loss"),
        ev(3, "player_possession", 52, 103, rtl, phase=3, first=True, last=True, end="pass"),
        ev(4, "on_ball_engagement", 56, 204, rtl, physical=54, phase=3),
        ev(5, "passing_option", 8, 104, ltr, phase=0),
    ]


def write_csv(path: Path, header: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def write_match(raw_root: Path, match_id: int, sides: list[str]) -> None:
    d = raw_root / "data" / "matches" / str(match_id)
    d.mkdir(parents=True)
    (d / f"{match_id}_match.json").write_text(
        json.dumps(
            {
                "id": match_id,
                "date_time": "2024-12-21T06:00:00Z",
                "home_team": {"id": HOME, "short_name": "Home FC"},
                "away_team": {"id": AWAY, "short_name": "Away FC"},
                "match_periods": [
                    {"period": 1, "start_frame": P1[0], "end_frame": P1[1]},
                    {"period": 2, "start_frame": P2[0], "end_frame": P2[1]},
                ],
                "home_team_side": sides,
                "ball": {"trackable_object": 55},
                "players": players_json(),
            }
        ),
        encoding="utf-8",
    )
    write_tracking(d / f"{match_id}_tracking_extrapolated.jsonl", P2[1] + 1)
    write_csv(
        d / f"{match_id}_dynamic_events.csv",
        [*EVENT_COLUMNS, "match_id"],
        event_rows(match_id),
    )
    phases = [
        {
            "index": ph["index"],
            "period": ph["period"],
            "frame_start": ph["frame_start"],
            "frame_end": ph["frame_end"],
            "team_in_possession_id": ph["team"],
            "n_player_possessions_in_phase": ph["npp"],
            "team_possession_loss_in_phase": ph["loss"],
            "attacking_side": "left_to_right",
            "x_start": 20.0,
            "third_start": "attacking_third",
            "match_id": match_id,
        }
        for ph in phases_rows()
    ]
    write_csv(d / f"{match_id}_phases_of_play.csv", [*PHASE_COLUMNS, "match_id"], phases)


@pytest.fixture
def bundle(tmp_path: Path) -> dict[str, Path]:
    raw_root = tmp_path / "data" / "raw" / SOURCE_ID
    write_match(raw_root, 1001, ["left_to_right", "right_to_left"])
    write_match(raw_root, 1002, ["right_to_left", "left_to_right"])  # sides contradict the data
    agg = raw_root / "data" / "aggregates"
    agg.mkdir(parents=True)
    for kind in ("physical", "obr", "passing"):
        (agg / f"aus1league_{kind}aggregates_20242025.csv").write_text(
            "player_id,player_name,minutes\n1,A,90.5\n2,B,\n", encoding="utf-8"
        )
    files = [
        FileEntry(
            path=f"data/matches/{mid}/{mid}_tracking_extrapolated.jsonl",
            bytes=1000,
            sha256="0" * 64,
            lfs=True,
            role="tracking",
            match_id=mid,
        )
        for mid in (1001, 1002)
    ]
    source = Source(
        source_id=SOURCE_ID,
        sport="football",
        kind="github",
        repo="SkillCorner/opendata",
        ref="master",
        commit=COMMIT,
        license="MIT",
        raw_url="https://raw.githubusercontent.com/SkillCorner/opendata/{commit}/",
        lfs_url="https://media.githubusercontent.com/media/SkillCorner/opendata/{commit}/",
        files=files,
    )
    manifest = tmp_path / "manifest" / "sources.json"
    save_manifest(Manifest(schema_version=1, sources=[source]), manifest)
    return {
        "manifest": manifest,
        "data": tmp_path / "data",
        "reports": tmp_path / "reports",
        "docs": tmp_path / "docs" / "formats",
        "schemas": tmp_path / "schemas",
    }


def run(bundle: dict[str, Path]) -> int:
    return main(
        [
            "freeze-schema",
            "football",
            "--manifest",
            str(bundle["manifest"]),
            "--data-dir",
            str(bundle["data"]),
            "--reports-dir",
            str(bundle["reports"]),
            "--docs-dir",
            str(bundle["docs"]),
            "--schemas-dir",
            str(bundle["schemas"]),
            "--workers",
            "1",
        ]
    )


def test_probe_measures_the_planted_truth(bundle: dict[str, Path]) -> None:
    good = discover(bundle["data"] / "raw" / SOURCE_ID)[0]
    row = probe_match(good)
    assert row["match_id"] == 1001
    assert row["n_frames"] == 84
    assert row["frame_contiguous_from_0"] is True
    assert row["frames_outside_periods"] == 4
    assert row["frame_max_minus_last_end"] == 0
    assert row["ts_null_iff_outside"] is True
    assert row["ts_rule_pct"] == 100.0
    assert row["p2_first_ts"] == "00:45:00.00"
    assert row["periods"] == "p1:2-41;p2:44-83"
    assert row["pct_22_players"] == 75.0
    assert row["pct_0_players"] == 25.0
    assert row["pct_partial_1_21"] == 0.0
    assert row["ball_present_iff_22"] is True
    assert row["pct_entries_detected"] == 54.55  # 6 even ids of 11 per team are detected
    assert row["z_min"] == -0.3 and row["z_max"] == 0.5
    assert row["tracking_id_key"] == "id"
    assert row["ids_in_players_id"] == 22 and row["ids_in_trackable_object"] == 0
    assert row["possession_id_key"] == "id" and row["events_id_key"] == "id"
    assert row["gk_home_mean_x"] == "p1:-45.0;p2:+45.0"
    assert row["side_check"] == "ok"
    assert row["ev_coord_frame"] == "attack_normalized"
    assert row["ev_xy_raw_ltr_pct"] == 100.0 and row["ev_xy_flip_rtl_pct"] == 100.0
    assert row["ev_xy_raw_rtl_pct"] == 0.0 and row["ev_xy_flip_ltr_pct"] == 0.0
    assert row["y_left_pos_ltr_pct"] == 100.0
    assert row["n_shots"] == 1 and row["n_pp_lead_to_shot"] == 1
    assert row["ev_time_rule_pct"] == 83.33
    assert row["ev_time_eq_physical_start_pct"] == 16.67
    assert row["ev_time_unexplained"] == 0
    assert row["n_phases"] == 4 and row["n_player_possessions"] == 4
    assert row["n_tp_first_flags"] == 3 and row["n_tp_last_flags"] == 3
    assert row["n_phase_runs_same_team"] == 4
    assert row["pct_tp_multi_phase"] == 0.0
    assert row["n_phases_without_pp"] == 1
    assert row["loss_vs_team_change_mismatch"] == 0
    assert row["phase_overlaps"] == 0
    assert row["pct_group_agrees_phase"] == 100.0


def test_side_mismatch_is_reported_not_averaged(bundle: dict[str, Path]) -> None:
    bad = discover(bundle["data"] / "raw" / SOURCE_ID)[1]
    row = probe_match(bad)
    assert row["match_id"] == 1002
    assert row["side_check"] == "MISMATCH p1:home,p1:away,p2:home,p2:away"
    # Same positions as 1001, so the goalkeepers did not move: only the label is wrong.
    assert row["gk_home_mean_x"] == "p1:-45.0;p2:+45.0"


def test_freeze_schema_writes_report_docs_and_schemas(
    bundle: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(bundle) == 0
    out = capsys.readouterr().out
    assert "1001" in out and "1002" in out
    assert "same in all 2 matches:" in out

    with (bundle["reports"] / "football_format.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["match_id"] for r in rows] == ["1001", "1002"]
    assert rows[0]["ts_format"] == "HH:MM:SS.ff"
    assert rows[0]["player_keys"] == "is_detected,player_id,x,y"
    assert rows[0]["ball_keys"] == "is_detected,x,y,z"
    assert rows[1]["side_check"].startswith("MISMATCH")

    names = sorted(p.name for p in bundle["schemas"].glob("*.schema.json"))
    assert names == [
        "aggregates_obr.schema.json",
        "aggregates_passing.schema.json",
        "aggregates_physical.schema.json",
        "dynamic_events.schema.json",
        "phases_of_play.schema.json",
    ]
    events = load_schema(bundle["schemas"] / "dynamic_events.schema.json")
    assert len(events.columns) == len(EVENT_COLUMNS) + 1
    assert events.names[:3] == ("index", "event_type", "end_type")
    assert (
        dict(zip(events.names, (c.type for c in events.columns), strict=True))["lead_to_shot"]
        == "BOOLEAN"
    )
    assert len(events.frozen_from) == 2
    phases = load_schema(bundle["schemas"] / "phases_of_play.schema.json")
    assert len(phases.columns) == len(PHASE_COLUMNS) + 1
    raw = json.loads((bundle["schemas"] / "phases_of_play.schema.json").read_text("utf-8"))
    assert raw["commit"] == COMMIT and raw["sport"] == "football"

    doc = (bundle["docs"] / "football.md").read_text(encoding="utf-8")
    assert COMMIT in doc
    assert "| 1001 |" in doc and "| 1002 |" in doc
    assert "`players[].id`" in doc

    # Second run: nothing changed, exit 0 and the schemas are reported unchanged.
    assert run(bundle) == 0
    assert "unchanged" in capsys.readouterr().out


def test_header_drift_fails_freeze(bundle: dict[str, Path]) -> None:
    events = bundle["data"] / "raw" / SOURCE_ID / "data" / "matches" / "1002"
    path = events / "1002_dynamic_events.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("match_id", "match_identifier", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="headers differ"):
        run(bundle)


def test_type_merge_ignores_all_null_votes_and_promotes(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "c.csv"
    a.write_text("k,v,w\n1,,\n", encoding="utf-8")  # v and w empty here
    b.write_text("k,v,w\n2,7,\n", encoding="utf-8")  # v is an integer here, w still empty
    c.write_text("k,v,w\n3,1.5,\n", encoding="utf-8")  # v is a double here
    con = duckdb.connect()
    schema = freeze_csv_family("t", [a, b, c], tmp_path, con)
    assert [(col.name, col.type) for col in schema.columns] == [
        ("k", "BIGINT"),
        ("v", "DOUBLE"),
        ("w", "VARCHAR"),
    ]
    assert schema.all_null_columns == ("w",)
    assert schema.frozen_from == ("a.csv", "b.csv", "c.csv")
