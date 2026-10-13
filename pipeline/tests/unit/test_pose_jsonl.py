"""The Body Pose line reader (task 55): joints by name, a different key set refused, one line
at a time, the same stream from a gzip and from the member of a zip."""

from __future__ import annotations

import gzip
import json
import random
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tracklab.pose import jsonl
from tracklab.pose.jsonl import JOINTS, PoseFormatError, iter_frames, open_lines, parse_frame


def joint_dict(seed: float, names: list[str] | None = None) -> dict[str, Any]:
    """Every joint of a player with values that name the joint: x is its position in JOINTS."""
    names = list(JOINTS) if names is None else names
    return {
        name: {
            "xyz": [JOINTS.index(name) + seed, 0.5 + seed, 1.0],
            "p90_mae_cm": 5.0 + JOINTS.index(name),
        }
        for name in names
    }


def frame_line(frame: int = 100, joints: dict[str, Any] | None = None) -> str:
    return json.dumps(
        {
            "frame": frame,
            "timestamp": "00:00:00.00",
            "period": 2,
            "ball_data": {"x": 1.0, "y": 2.0, "z": 0.3, "is_detected": True},
            "possession": {"player_id": None, "group": None},
            "image_corners_projection": {},
            "player_data": [
                {"player_id": 7, "x": 10.0, "y": 20.0, "is_detected": True, "joints": joints},
                {"player_id": 8, "x": 11.0, "y": 21.0, "is_detected": False, "joints": None},
            ],
        }
    )


def test_joints_are_mapped_by_name_whatever_the_order_of_the_keys() -> None:
    names = list(JOINTS)
    random.Random(3).shuffle(names)
    assert names != list(JOINTS)
    frame = parse_frame(frame_line(joints=joint_dict(0.0, names)))
    player = frame.players[0]
    assert player.xyz is not None and player.mae_cm is not None
    assert player.xyz[:, 0].tolist() == list(range(len(JOINTS)))  # x of joint i is i
    assert player.mae_cm.tolist() == [5.0 + i for i in range(len(JOINTS))]


def test_a_different_set_of_joint_names_is_refused() -> None:
    missing = joint_dict(0.0)
    del missing["nose"]
    with pytest.raises(PoseFormatError, match="missing"):
        parse_frame(frame_line(joints=missing))
    extra = joint_dict(0.0)
    extra["tail"] = {"xyz": [0, 0, 0], "p90_mae_cm": 1.0}
    with pytest.raises(PoseFormatError, match="extra"):
        parse_frame(frame_line(joints=extra))


def test_a_player_without_joints_has_no_pose_and_nothing_is_filled_in() -> None:
    frame = parse_frame(frame_line(joints=None))
    assert [p.xyz for p in frame.players] == [None, None]
    assert [p.mae_cm for p in frame.players] == [None, None]
    assert [p.is_detected for p in frame.players] == [True, False]


def test_the_iterator_reads_one_line_at_a_time() -> None:
    def lines() -> Iterator[str]:
        yield frame_line(1, joint_dict(0.0))
        raise AssertionError("the second line was read before the first frame was asked for")

    assert next(iter_frames(lines())).frame == 1


def test_blank_lines_are_skipped() -> None:
    assert [f.frame for f in iter_frames(["", frame_line(5), "  \n", frame_line(6)])] == [5, 6]


def test_gzip_and_zip_member_give_the_same_frames(tmp_path: Path) -> None:
    text = "\n".join(frame_line(f, joint_dict(f)) for f in (1, 2, 3)) + "\n"
    gz = tmp_path / "a.jsonl.gz"
    gz.write_bytes(gzip.compress(text.encode()))
    zp = tmp_path / "a.jsonl.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("a.jsonl", text)
    with open_lines(gz) as a, open_lines(zp) as b:
        from_gz, from_zip = list(iter_frames(a)), list(iter_frames(b))
    assert [f.frame for f in from_gz] == [1, 2, 3]
    for x, y in zip(from_gz, from_zip, strict=True):
        assert x.frame == y.frame and np.array_equal(x.players[0].xyz, y.players[0].xyz)  # type: ignore[arg-type]


def test_a_zip_with_two_jsonl_members_needs_the_member_named(tmp_path: Path) -> None:
    zp = tmp_path / "two.zip"
    with zipfile.ZipFile(zp, "w") as archive:
        archive.writestr("a.jsonl", frame_line(1))
        archive.writestr("b.jsonl", frame_line(2))
    with pytest.raises(PoseFormatError), open_lines(zp):
        pass
    with open_lines(zp, "b.jsonl") as stream:
        assert [f.frame for f in iter_frames(stream)] == [2]


def test_joints_in_a_shuffled_declared_order_carry_the_same_content_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line = frame_line(joints=joint_dict(0.25))
    base = parse_frame(line).players[0]
    shuffled = list(JOINTS)
    random.Random(9).shuffle(shuffled)
    monkeypatch.setattr(jsonl, "JOINTS", tuple(shuffled))
    other = parse_frame(line).players[0]
    assert base.xyz is not None and other.xyz is not None and base.mae_cm is not None
    for i, name in enumerate(shuffled):
        assert np.array_equal(other.xyz[i], base.xyz[JOINTS.index(name)])
