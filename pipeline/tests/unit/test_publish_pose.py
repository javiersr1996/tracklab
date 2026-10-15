"""`tracklab publish pose` (task 55): the clip of the Body Pose sample and its record.

What these tests hold:

* the builder on synthetic frames: the body frame (the subtraction of the player's (x, y)),
  nothing invented for a player without joints, a quantisation of at most 0.5 cm, the joints'
  declared order changing the bytes and nothing else;
* the versioned clip: it validates against `web/lib/pose/schema.json`, its bytes and sha256 are
  the record's, its midHip sits at the body origin, the schema refuses a damaged clip;
* `--check`: PARTIAL without the sample, a failure when the clip, the record or the manifest
  disagree;
* the real sample (skipped, with the reason printed by `-rs`, unless it is under the data
  root, which CI's fixtures are not): the coverage against a second, independent reading
  (duckdb `read_json` on the gz), the alignment with the tracking by `frame`, and two builds
  with the same bytes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pytest
from jsonschema import Draft202012Validator

from tracklab.ingest.manifest import FileEntry
from tracklab.paths import data_root
from tracklab.pose import jsonl
from tracklab.pose.jsonl import JOINTS, PoseFrame
from tracklab.publish import pose as publish_pose
from tracklab.publish.pose import (
    ALIGN_FRAME,
    BONE_NAMES,
    CLIP_FILE,
    LIMITS,
    RECORD_FILE,
    build_clip,
    cm,
    run_publish_pose,
)

REPO = Path(__file__).resolve().parents[3]
WEB_DATA = REPO / "web" / "public" / "data"
REPORTS = REPO / "pipeline" / "reports"
SCHEMA = REPO / "web" / "lib" / "pose" / "schema.json"
MANIFEST = REPO / "pipeline" / "manifest" / "sources.json"
MIDHIP_LIMIT_CM = 50.0  # measured max 38.64 cm; the plan's 30 cm hypothesis was contradicted
HALF_CM = 0.5 + 1e-9


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clip() -> dict[str, Any]:
    return _json(WEB_DATA / CLIP_FILE)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    return _json(REPORTS / RECORD_FILE)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def real_data() -> Path:
    """The data root, if the sample and the match's bronze are under it; else skip, saying why."""
    root = data_root()
    needed = [
        publish_pose.sample_path(root),
        root / "bronze" / "football" / "tracking_objects" / "1925299.parquet",
    ]
    absent = [p.name for p in needed if not p.is_file()]
    if absent:
        pytest.skip(f"{absent} not under TRACKLAB_DATA_ROOT={root}: CI's check says PARTIAL 0/1")
    return root


@pytest.fixture(scope="module")
def built(real_data: Path) -> tuple[str, dict[str, Any]]:
    """What the code writes from the real sample, once for the module."""
    return publish_pose.build(real_data, MANIFEST)


# --- synthetic frames ---------------------------------------------------------------------


def _line(frame: int, players: list[tuple[int, float, float, bool, float]]) -> str:
    """A file line: every joint at (x, y) + an offset that names it (its index in the README's
    order), midHip at (+0.123, -0.054, 0.95) from (x, y); keys in reverse order, as a file may."""
    data = []
    for pid, x, y, with_pose, seed in players:
        joints = None
        if with_pose:
            joints = {}
            for i, name in enumerate(JOINTS):
                dx, dy, dz = (
                    (0.123, -0.054, 0.95)
                    if name == "midHip"
                    else (i * 0.011, -i * 0.007, 0.9 + i * 0.013 + seed)
                )
                joints[name] = {"xyz": [x + dx, y + dy, dz], "p90_mae_cm": 4.0 + i * 0.5 + seed}
            joints = dict(reversed(joints.items()))
        data.append({"player_id": pid, "x": x, "y": y, "is_detected": True, "joints": joints})
    return json.dumps(
        {
            "frame": frame,
            "timestamp": "00:00:00.00",
            "period": 2,
            "ball_data": {"x": 1.0, "y": 2.0, "z": 0.3, "is_detected": True},
            "possession": {"player_id": None, "group": None},
            "player_data": data,
        }
    )


def _frames() -> list[PoseFrame]:
    """The frames as the parser makes them, under the module's current `JOINTS`."""
    return [
        jsonl.parse_frame(
            _line(
                100 + i,
                [(8, -30.0 + i, 5.5, i != 1, 0.0), (7, 41.27 + i, -12.345, True, i * 0.1)],
            )
        )
        for i in range(3)
    ]


ENTRY = FileEntry("data/bodypose/x.jsonl.gz", 10, "0" * 64, False, "bodypose_sample", None)
PLAYERS = [
    {"player_id": 7, "team_id": 1, "number": 9},
    {"player_id": 8, "team_id": 2, "number": 4},
]
TEAMS = [{"team_id": 1, "side": "home"}, {"team_id": 2, "side": "away"}]
SURFACE = {"spec": "provider_105x68", "length_m": 105, "width_m": 68}


def synthetic() -> dict[str, Any]:
    return build_clip(_frames(), ENTRY, PLAYERS, TEAMS, SURFACE)


def test_the_synthetic_clip_validates_against_the_schema() -> None:
    validator = Draft202012Validator(_json(SCHEMA))
    assert sorted(e.message for e in validator.iter_errors(synthetic())) == []


def test_joints_are_in_the_body_frame_and_midhip_sits_at_the_origin() -> None:
    clip = synthetic()
    mid = clip["joints"].index("midHip")
    seen = 0
    for f in clip["frames"]:
        for entry in f["p"]:
            if entry[4] is not None:
                assert entry[4][0][mid] == [12, -5, 95]  # (0.123, -0.054, 0.95) m in cm
                seen += 1
    assert seen == 5


def test_a_player_without_joints_stays_null_and_is_not_filled_from_a_neighbour_frame() -> None:
    clip = synthetic()
    # player 8 is the second in PLAYERS and has no pose in the middle frame only
    assert [f["p"][1][4] is None for f in clip["frames"]] == [False, True, False]
    assert all(f["p"][0][4] is not None for f in clip["frames"])


def test_players_come_in_the_order_of_the_players_list_in_every_frame() -> None:
    clip = synthetic()
    assert [[e[0] for e in f["p"]] for f in clip["frames"]] == [[0, 1]] * 3
    assert [f["t"] for f in clip["frames"]] == [0, 40, 80]


def test_quantising_to_whole_centimetres_moves_no_value_more_than_half_a_centimetre() -> None:
    metres = np.random.default_rng(5).uniform(-60, 60, 100_000)
    assert float(np.abs(cm(metres) - metres * 100).max()) <= HALF_CM
    for f, source in zip(synthetic()["frames"], _frames(), strict=True):
        ordered = sorted(source.players, key=lambda q: q.player_id)
        for entry, p in zip(f["p"], ordered, strict=True):
            assert abs(entry[1] - p.x * 100) <= HALF_CM and abs(entry[2] - p.y * 100) <= HALF_CM
            if p.xyz is not None:
                exact = (p.xyz - np.array([p.x, p.y, 0.0])) * 100
                assert float(np.abs(np.array(entry[4][0]) - exact).max()) <= HALF_CM


def test_shuffling_the_declared_order_changes_the_order_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = synthetic()
    order = list(JOINTS)
    random.Random(1).shuffle(order)
    monkeypatch.setattr(jsonl, "JOINTS", tuple(order))
    other = build_clip(_frames(), ENTRY, PLAYERS, TEAMS, SURFACE)
    assert other["joints"] == order and other["joints"] != base["joints"]
    assert json.dumps(other) != json.dumps(base)  # the bytes did change ...
    base_at = {n: i for i, n in enumerate(base["joints"])}
    other_at = {n: i for i, n in enumerate(other["joints"])}
    for fb, fo in zip(base["frames"], other["frames"], strict=True):
        for pb, po in zip(fb["p"], fo["p"], strict=True):
            assert pb[:4] == po[:4]
            if pb[4] is None:
                assert po[4] is None
                continue
            for name in JOINTS:  # ... but not what each joint says
                assert pb[4][0][base_at[name]] == po[4][0][other_at[name]]
                assert pb[4][1][base_at[name]] == po[4][1][other_at[name]]

    def named(c: dict[str, Any]) -> list[tuple[str, str]]:
        return sorted(tuple(sorted((c["joints"][a], c["joints"][b]))) for a, b in c["bones"])  # type: ignore[misc]

    assert named(base) == named(other)


def test_the_bones_are_pairs_of_distinct_known_joints() -> None:
    assert len(set(BONE_NAMES)) == len(BONE_NAMES)
    assert all(a != b and a in JOINTS and b in JOINTS for a, b in BONE_NAMES)


# --- the versioned clip ---------------------------------------------------------------------


def test_the_versioned_clip_validates_against_its_schema(clip: dict[str, Any]) -> None:
    validator = Draft202012Validator(_json(SCHEMA))
    assert sorted(e.message for e in validator.iter_errors(clip)) == []


def _first_skeleton(c: dict[str, Any]) -> list[Any]:
    return next(e for f in c["frames"] for e in f["p"] if e[4] is not None)  # type: ignore[no-any-return]


DAMAGES: list[Callable[[dict[str, Any]], object]] = [
    lambda c: c["joints"].pop(),
    lambda c: c.update(extra=1),
    lambda c: c["frames"][0]["p"][0].__setitem__(1, "12"),
    lambda c: c["frames"][0].pop("ball"),
    lambda c: c["limits"].pop(),
    lambda c: c["source"].__setitem__("sha256", "xyz"),
    lambda c: _first_skeleton(c)[4][0].pop(),
    lambda c: c.pop("surface"),
]


@pytest.mark.parametrize("damage", DAMAGES)
def test_the_schema_refuses_a_damaged_clip(damage: Callable[[dict[str, Any]], object]) -> None:
    broken = copy.deepcopy(synthetic())
    damage(broken)
    assert list(Draft202012Validator(_json(SCHEMA)).iter_errors(broken))


def test_the_clip_bytes_and_hash_are_the_records(
    clip: dict[str, Any], record: dict[str, Any]
) -> None:
    data = (WEB_DATA / CLIP_FILE).read_bytes()
    assert (len(data), hashlib.sha256(data).hexdigest()) == (
        record["clip"]["bytes"],
        record["clip"]["sha256"],
    )
    assert clip["coverage"] == record["coverage"] and clip["source"] == record["source"]
    assert record["clip"]["within_hypothesis"] == (len(data) <= publish_pose.MAX_POSE_CLIP_BYTES)


def test_the_header_holds_the_three_limits_of_the_readme_and_the_joint_order(
    clip: dict[str, Any],
) -> None:
    assert clip["limits"] == [dict(item) for item in LIMITS]
    assert [item["readme"] for item in clip["limits"]] == [
        "readme.md:139",
        "readme.md:140-142",
        "readme.md:143-145",
    ]
    assert clip["joints"] == list(JOINTS) and len(clip["joints"]) == 29
    assert (clip["frame_lo"], clip["frame_hi"], clip["fps"]) == (124487, 124795, 25)
    assert clip["tracking_frame_factor"] == 2.5
    assert len(clip["frames"]) == clip["frame_hi"] - clip["frame_lo"] + 1


def test_the_pitch_is_the_one_the_possessions_of_the_same_match_are_drawn_on(
    clip: dict[str, Any],
) -> None:
    index = _json(WEB_DATA / "index.json")
    same = [p for p in index["possessions"] if p["match_id"] == f"fb:{clip['match_id']}"]
    assert same, "no published possession of the match to compare the pitch with"
    for entry in same:
        assert clip["surface"] == _json(WEB_DATA / entry["file"])["surface"]


def test_every_midhip_is_at_the_body_origin_to_within_the_measured_bound(
    clip: dict[str, Any], record: dict[str, Any]
) -> None:
    mid = clip["joints"].index("midHip")
    d = [
        float(np.hypot(e[4][0][mid][0], e[4][0][mid][1]))
        for f in clip["frames"]
        for e in f["p"]
        if e[4] is not None
    ]
    assert len(d) == record["coverage"]["with_joints"]
    assert max(d) < MIDHIP_LIMIT_CM
    assert round(max(d), 2) == record["midhip_horizontal_cm"]["max"]


def test_the_players_are_the_ones_the_frames_use_and_carry_no_name(clip: dict[str, Any]) -> None:
    used = {e[0] for f in clip["frames"] for e in f["p"]}
    assert used == set(range(len(clip["players"])))
    assert all(set(p) == {"player_id", "team_id", "number"} for p in clip["players"])
    ordered = [(p["team_id"], p["number"], p["player_id"]) for p in clip["players"]]
    assert ordered == sorted(ordered)


def test_the_published_mae_in_millimetres_keeps_the_median_within_a_twentieth_of_a_centimetre(
    clip: dict[str, Any],
) -> None:
    mae = [v for f in clip["frames"] for e in f["p"] if e[4] is not None for v in e[4][1]]
    assert abs(float(np.median(mae)) / 10 - clip["coverage"]["p90_mae_cm"]["median"]) <= 0.05 + 1e-9


# --- --check --------------------------------------------------------------------------------


def _copy_published(tmp_path: Path) -> tuple[Path, Path]:
    out, reports = tmp_path / "data", tmp_path / "reports"
    shutil.copytree(WEB_DATA / "pose", out / "pose")  # the sample's clip and the two of task 62
    shutil.copy(WEB_DATA / "pose.json", out / "pose.json")
    reports.mkdir()
    for path in REPORTS.glob("pose_*.json"):
        shutil.copy(path, reports / path.name)
    return out, reports


def _check(tmp_path: Path, out: Path, reports: Path, manifest: Path = MANIFEST) -> int:
    return run_publish_pose(tmp_path / "nodata", reports, out, manifest, SCHEMA, check=True)


def test_check_says_partial_without_the_sample_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, reports = _copy_published(tmp_path)
    assert _check(tmp_path, out, reports) == 0
    assert "PARTIAL 0/3" in capsys.readouterr().out


def test_check_fails_when_one_byte_of_the_clip_changes(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    path = out / CLIP_FILE
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"fps":25', '"fps":25 ', 1), encoding="utf-8")
    assert _check(tmp_path, out, reports) == 1


def test_check_fails_when_the_clip_no_longer_validates(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    data = json.loads((out / CLIP_FILE).read_bytes())
    data["joints"].pop()
    raw = json.dumps(data, separators=(",", ":")).encode()
    (out / CLIP_FILE).write_bytes(raw)
    record = _json(reports / RECORD_FILE)
    record["clip"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (reports / RECORD_FILE).write_text(json.dumps(record), encoding="utf-8")
    assert _check(tmp_path, out, reports) == 1  # size and hash agree: only the schema catches it


def test_check_fails_when_the_manifest_pins_another_sample(tmp_path: Path) -> None:
    out, reports = _copy_published(tmp_path)
    manifest = _json(MANIFEST)
    for source in manifest["sources"]:
        for f in source["files"]:
            if f["role"] == "bodypose_sample":
                f["sha256"] = "0" * 64
    other = tmp_path / "sources.json"
    other.write_text(json.dumps(manifest), encoding="utf-8")
    assert _check(tmp_path, out, reports, other) == 1


def test_check_fails_on_a_stray_file_in_the_clip_directory_and_a_missing_record(
    tmp_path: Path,
) -> None:
    out, reports = _copy_published(tmp_path)
    (out / "pose" / "other.json").write_text("{}", encoding="utf-8")
    assert _check(tmp_path, out, reports) == 1
    (out / "pose" / "other.json").unlink()
    (reports / RECORD_FILE).unlink()
    assert _check(tmp_path, out, reports) == 1


# --- the real sample (skipped without it) -----------------------------------------------------


def _independent_coverage(path: Path) -> dict[str, Any]:
    """Coverage by a second reading: duckdb `read_json` on the gz, sharing no code with ours."""
    con = duckdb.connect()
    con.execute(  # a view cannot be prepared, so the path is quoted into the statement
        "create view raw as select frame, player_data from read_json("
        f"'{path.as_posix()}', format='newline_delimited', "
        "columns={frame: 'BIGINT', player_data: 'JSON'})"
    )
    con.execute(
        "create view players as select frame, p from (select frame, "
        "unnest(from_json(player_data, '[\"json\"]')) as p from raw)"
    )
    posed = "json_type(p->'joints') = 'OBJECT'"
    frames = con.execute("select count(*) from raw").fetchone()
    player_frames = con.execute("select count(*) from players").fetchone()
    with_joints = con.execute(f"select count(*) from players where {posed}").fetchone()
    mae = con.execute(
        "select count(*), min(v), median(v), quantile_cont(v, 0.9), max(v) from ("
        "select (j.value->>'p90_mae_cm')::double as v from players, "
        f"json_each(p->'joints') as j where {posed})"
    ).fetchone()
    per_frame = con.execute(
        "select min(n), max(n) from (select frame, "
        f"count(*) filter (where {posed}) as n from players group by frame)"
    ).fetchone()
    assert frames and player_frames and with_joints and mae and per_frame
    return {
        "frames": frames[0],
        "player_frames": player_frames[0],
        "with_joints": with_joints[0],
        "joint_observations": mae[0],
        "skeletons_per_frame": {"min": per_frame[0], "max": per_frame[1]},
        "p90_mae_cm": {"min": mae[1], "median": mae[2], "p90": mae[3], "max": mae[4]},
    }


def test_the_published_coverage_is_a_second_readings_and_the_inventory(
    real_data: Path, clip: dict[str, Any]
) -> None:
    second = _independent_coverage(publish_pose.sample_path(real_data))
    published = clip["coverage"]
    for key in (
        "frames",
        "player_frames",
        "with_joints",
        "joint_observations",
        "skeletons_per_frame",
    ):
        assert published[key] == second[key], key
    for key, value in second["p90_mae_cm"].items():
        assert published["p90_mae_cm"][key] == pytest.approx(value, abs=1e-9), key
    # the inventory of 2026-10-13 (tasks/todo.md, "Lo que ya existe, medido")
    assert (second["frames"], second["player_frames"], second["with_joints"]) == (309, 9888, 4953)
    assert second["joint_observations"] == 143637 == 4953 * 29
    assert round(second["p90_mae_cm"]["median"], 2) == 11.35


def test_at_pose_frame_124490_every_tracked_player_is_in_the_clip_within_a_metre_and_a_half(
    real_data: Path, clip: dict[str, Any]
) -> None:
    tracking = int(ALIGN_FRAME / 2.5)
    assert tracking == 49796
    rows = (
        duckdb.connect()
        .execute(
            "select player_id, x, y from read_parquet(?) where frame = ?",
            [(real_data / "bronze/football/tracking_objects/1925299.parquet").as_posix(), tracking],
        )
        .fetchall()
    )
    assert len(rows) == 22
    ids = [p["player_id"] for p in clip["players"]]
    here = {ids[e[0]]: e for e in next(f for f in clip["frames"] if f["f"] == ALIGN_FRAME)["p"]}
    assert {r[0] for r in rows} <= here.keys()
    gaps = [float(np.hypot(here[r[0]][1] / 100 - r[1], here[r[0]][2] / 100 - r[2])) for r in rows]
    assert max(gaps) < 1.5


def test_the_code_puts_every_midhip_of_the_real_sample_at_the_body_origin(
    built: tuple[str, dict[str, Any]],
) -> None:
    clip = json.loads(built[0])
    mid = clip["joints"].index("midHip")
    d = [
        float(np.hypot(e[4][0][mid][0], e[4][0][mid][1]))
        for f in clip["frames"]
        for e in f["p"]
        if e[4] is not None
    ]
    assert len(d) == 4953
    assert max(d) < MIDHIP_LIMIT_CM


def test_two_builds_have_the_same_bytes_and_are_the_versioned_files(
    real_data: Path, built: tuple[str, dict[str, Any]], record: dict[str, Any]
) -> None:
    assert publish_pose.build(real_data, MANIFEST) == built
    assert built[0].encode("utf-8") == (WEB_DATA / CLIP_FILE).read_bytes()
    assert publish_pose.render(built[1]) == (REPORTS / RECORD_FILE).read_text(encoding="utf-8")
    assert built[1]["quantisation"]["joint_offset_max_abs_cm"] <= HALF_CM
    assert built[1]["quantisation"]["player_xy_max_abs_cm"] <= HALF_CM
    assert built[1]["clip"]["bytes"] == record["clip"]["bytes"]


def test_a_sample_that_is_not_the_manifests_is_refused_before_it_is_read(
    real_data: Path, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    target = publish_pose.sample_path(root)
    target.parent.mkdir(parents=True)
    data = bytearray(publish_pose.sample_path(real_data).read_bytes())
    data[len(data) // 2] ^= 0xFF  # same size, other content
    target.write_bytes(bytes(data))
    with pytest.raises(publish_pose.PosePublishError, match="not the file the manifest pins"):
        publish_pose.read_sample(root, MANIFEST)
