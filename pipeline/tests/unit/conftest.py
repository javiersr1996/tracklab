"""Fixtures shared by the tests of task 60's phase B2 (`test_pose_data`, `test_pose_protocol`,
`test_pose_probe`): a Body Pose bronze written by hand, and a throwaway repository whose HEAD
holds a pose protocol for the guard to read. No real pose is read by either."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from numpy.typing import NDArray

from tracklab.bronze.common import bronze_path
from tracklab.bronze.football.bodypose import BODYPOSE_FRAMES, BODYPOSE_PLAYERS
from tracklab.pose import data
from tracklab.pose.jsonl import JOINTS
from tracklab.runs.protocol import fingerprint, seal

CALIBRATION_MATCH = 1925299
CONFIRMATION_MATCH = 1996435
ROWS = 100  # the rows of 1925299 a hand-made verdict and calibration both count


@dataclass(frozen=True)
class Body:
    """One player's rows: consecutive or not, in one period or two."""

    player_id: int
    frames: NDArray[np.int64]
    periods: NDArray[np.int64]
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    joints: NDArray[np.float64]  # (n, 29, 3)
    mae_cm: NDArray[np.float64]  # (n, 29)


def runner(
    player_id: int,
    *,
    start: int,
    n: int,
    speed_m_s: float,
    period: int | NDArray[np.int64] = 1,
    mae_cm: float = 12.0,
    fps: float = 25.0,
    cadence_hz: float = 3.0,
) -> Body:
    """A body that travels along +x at `speed_m_s`, its ankles swinging along the way and its
    nose above midHip: joints at the body's x, y, every joint's z its index / 100 except the
    nose (+0.7 m) and the ankles (-0.7 m, rising in turn), `cadence_hz` steps a second."""
    t = np.arange(n) / fps
    x = 10.0 + speed_m_s * t
    y = np.full(n, -5.0)
    joints = np.zeros((n, len(JOINTS), 3))
    joints[:, :, 0] = x[:, None]
    joints[:, :, 1] = y[:, None]
    joints[:, :, 2] = np.arange(len(JOINTS)) / 100.0
    swing = 0.6 * np.sin(np.pi * cadence_hz * t)
    left, right = JOINTS.index("lAnkle"), JOINTS.index("rAnkle")
    joints[:, left, 0] += swing
    joints[:, right, 0] -= swing
    joints[:, JOINTS.index("nose"), 2] = 0.7
    joints[:, left, 2] = -0.7 + 0.1 * np.maximum(np.cos(np.pi * cadence_hz * t), 0.0)
    joints[:, right, 2] = -0.7 + 0.1 * np.maximum(-np.cos(np.pi * cadence_hz * t), 0.0)
    periods = np.broadcast_to(np.asarray(period, dtype=np.int64), (n,)).copy()
    return Body(
        player_id,
        np.arange(start, start + n, dtype=np.int64),
        periods,
        x,
        y,
        joints,
        np.full((n, len(JOINTS)), mae_cm),
    )


def write_lineup(root: Path, match_id: int, rows: list[tuple[int, int, int]]) -> None:
    """`match_players` of `match_id` with (id, team_id, number) per player, nothing else."""
    path = bronze_path(root, "football", "match_players", match_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {
                "match_id": [match_id] * len(rows),
                "id": [r[0] for r in rows],
                "team_id": [r[1] for r in rows],
                "number": [r[2] for r in rows],
            }
        ),
        path,
    )


def write_bronze(
    root: Path, match_id: int, bodies: list[Body], *, first_row: int = 0, stored_as: int = 0
) -> Path:
    """Both bronze tables of `match_id` under `root`, one frame row per frame any body has
    (`first_row` > 0 makes it a slice, as `tracklab fixtures` cuts it); `stored_as`, a match id
    other than `match_id` written in the rows' `match_id`."""
    frames = sorted({int(f) for b in bodies for f in b.frames})
    period_of = {int(f): int(p) for b in bodies for f, p in zip(b.frames, b.periods, strict=True)}
    lineage = {
        "sport": "football",
        "match_id": stored_as or match_id,
        "source_file": f"raw/{match_id}.zip",
    }
    p_cols: dict[str, list[Any]] = {name: [] for name in BODYPOSE_PLAYERS.names}
    for b in bodies:
        for i in range(len(b.frames)):
            row = {
                **lineage,
                "source_row": first_row + frames.index(int(b.frames[i])),
                "frame": int(b.frames[i]),
                "period": int(b.periods[i]),
                "player_id": b.player_id,
                "x": float(b.x[i]),
                "y": float(b.y[i]),
                "is_detected": True,
                "joints": b.joints[i].astype(np.float32).ravel().tolist(),
                "mae": b.mae_cm[i].astype(np.float32).tolist(),
            }
            for k in p_cols:
                p_cols[k].append(row[k])
    f_cols: dict[str, list[Any]] = {name: [] for name in BODYPOSE_FRAMES.names}
    for i, f in enumerate(frames):
        ids = sorted(b.player_id for b in bodies if f in set(b.frames.tolist()))
        row = {
            **lineage,
            "source_row": first_row + i,
            "frame": f,
            "timestamp": None,
            "period": period_of[f],
            "ball_x": None,
            "ball_y": None,
            "ball_z": None,
            "ball_is_detected": None,
            "possession_group": None,
            "possession_player_id": None,
            "n_players": len(ids),
            "n_with_pose": len(ids),
            "player_ids": ids,
        }
        for k in f_cols:
            f_cols[k].append(row[k])
    for table, schema, cols in (
        ("bodypose_players", BODYPOSE_PLAYERS, p_cols),
        ("bodypose_frames", BODYPOSE_FRAMES, f_cols),
    ):
        path = bronze_path(root, "football", table, match_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pydict(cols, schema=schema), path)
    return root


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, encoding="utf-8"
    )


def protocol_payload(stage: str = "design", **extra: Any) -> dict[str, Any]:
    """A sealed pose protocol with the plan's split and the installed numpy: what the guard
    reads, nothing more."""
    design = {
        "split": {"calibration": [CALIBRATION_MATCH], "confirmation": [CONFIRMATION_MATCH]},
        "dependencies": {"numpy": importlib.metadata.version("numpy")},
    }
    history = [{"stage": "design", "task": 60, "date": "2026-10-15"}]
    if stage == "frozen":
        history.append({"stage": "frozen", "task": 60, "date": "2026-10-16"})
    return seal(
        {
            "stage": stage,
            "fingerprint": fingerprint(design),
            "design": design,
            "history": history,
            **extra,
        }
    )


class PoseRepo:
    """A throwaway repository the pose guard is pointed at, with a code tree under `pose/`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calibration_seal: str | None = None  # of the last calibration committed

    def commit(
        self,
        payload: dict[str, Any] | None = None,
        message: str = "commit",
        *,
        at: str = data.PROTOCOL_IN_REPO,
    ) -> None:
        if payload is not None:
            path = self.root / at
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", message)

    def frozen(self, width: int = 25, cap_cm: int = 20) -> dict[str, Any]:
        """The protocol frozen at (width, cap_cm) with the `pose/` tree HEAD holds now and the
        seal of the last calibration committed."""
        return protocol_payload(
            "frozen",
            frozen={
                "code_tree_sha": data.code_tree_sha(),
                "width": width,
                "cap_cm": cap_cm,
                "calibration_from": {"content_sha256": self.calibration_seal},
            },
        )

    def verdict(self, protocol: dict[str, Any], **change: Any) -> dict[str, Any]:
        """A sealed second-time verdict answering to `protocol`, alive by its own figures of M1
        and M2, computed on `ROWS` rows, `change` applied on top (keys `alive`, `dies_at`,
        `m1_players`, `half_iqr_hz`, `code_tree_sha`, `answers_to`, `rows`)."""
        m1 = change.get("m1_players", 12)
        return seal(
            {
                "protocol": {
                    k: change.get("answers_to", protocol)[k]
                    for k in ("stage", "fingerprint", "content_sha256")
                },
                "code_tree_sha": change.get("code_tree_sha", protocol["frozen"]["code_tree_sha"]),
                "inputs": {"rows": change.get("rows", ROWS)},
                "verdict": {
                    "M1": {"players": m1},
                    "M2": {
                        "players_with_both": 12,
                        "positive": 12,
                        "median_sd_hz": 0.01,
                        "half_iqr_hz": 0.1,
                    },
                    "dies_at": change.get("dies_at"),
                    "alive": change.get("alive", True),
                },
                "m4": {"half_iqr_hz": change.get("half_iqr_hz", 0.1)},
            }
        )

    def calibration(self, rows: Any = ROWS, **more: Any) -> None:
        """Commit a sealed first time of the probe that counted `rows` rows of 1925299 (`more`
        changes its content, so its seal), and remember the seal for `frozen`."""
        payload = seal({"inputs": {"rows": rows}, **more})
        self.commit(payload, "calibration", at=data.CALIBRATION_IN_REPO)
        self.calibration_seal = payload["content_sha256"]

    def open(self, width: int = 25, cap_cm: int = 20, rows: Any = ROWS) -> dict[str, Any]:
        """Commit the calibration and the frozen protocol, then its verdict: the guard opens."""
        self.calibration(rows)
        frozen = self.frozen(width, cap_cm)
        self.commit(frozen, "frozen")
        self.commit(self.verdict(frozen, rows=rows), "verdict", at=data.VERDICT_IN_REPO)
        return frozen


@pytest.fixture
def pose_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PoseRepo:
    """HEAD holds the pose protocol in stage design and a file under `pose/`."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "ci@example.invalid")
    _git(root, "config", "user.name", "ci")
    _git(root, "config", "commit.gpgsign", "false")
    code = root / data.CODE_IN_REPO / "gait.py"
    code.parent.mkdir(parents=True)
    code.write_text("# the code tree of the throwaway repository\n", encoding="utf-8")
    monkeypatch.setattr(data, "repo_root", lambda: root)
    repo = PoseRepo(root)
    repo.commit(protocol_payload(), "design")
    return repo


@pytest.fixture
def pose_kit() -> SimpleNamespace:
    """The helpers above, for the test modules (which do not import a conftest)."""
    return SimpleNamespace(
        Body=Body,
        runner=runner,
        write_bronze=write_bronze,
        write_lineup=write_lineup,
        protocol_payload=protocol_payload,
        calibration=CALIBRATION_MATCH,
        confirmation=CONFIRMATION_MATCH,
    )
