"""The two matches of P6 and the guard on the confirmation one (task 60 of tasks/todo.md, phase
B2), on the pattern of P5's `runs/data.py`.

Every match id comes from the protocol committed in HEAD of the repository that holds this
code (`reports/pose_protocol.json`, read with `git show`), never from the working copy: its
`content_sha256` and its `fingerprint` are verified before its split is read. The confirmation
match opens only past `assert_confirmation_open`: the committed protocol is in stage `frozen`
with a frozen entry after the design ones in its history; the `pose/` tree committed in HEAD is
the one the freeze recorded; the installed numpy is the one the design names; HEAD holds the
verdict of the second time on 1925299 (`reports/pose_verdict.json`), sealed, computed against
that frozen protocol by that same code tree, with P6 alive and a finite `m4.half_iqr_hz` (if M1
or M2 killed P6 on 1925299, 1996435 never opens); and the working tree is clean, untracked
files included. Anything else raises `HeldOutLocked`.

Two doors to a match's Body Pose bronze, and no other read of it under `tracklab.pose` (a test
greps the package):

* `load_players`, the only public function that returns rows of `bodypose_players`. It runs
  `require_readable` before it opens anything, and the `PoseRows` it returns runs it again as
  it is built, so a calibration one relabelled is refused. The rows are read in
  `_read_players`, whose only caller it is.
* `CountingHandle`, for `pose coverage`, the protocol's evidence and the lineup the metric is
  ordered by: fixed aggregate queries over either match, each returning integers, save two:
  `mae_cm` (quantiles of the provider's predicted error, not a position) and `z_range_m` (two
  numbers, the least and the greatest z over every joint and row), which task 58 published for
  both matches and the review of method lists as seen (point 5).

There is no path argument for the repository: tests point `repo_root` at a throwaway one.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow.parquet as pq
from numpy.typing import NDArray

from tracklab.bronze.common import bronze_path
from tracklab.pose.jsonl import JOINTS
from tracklab.runs.data import HeldOutLocked, dirty_paths
from tracklab.runs.protocol import fingerprint, sealed

PROTOCOL_IN_REPO = "pipeline/reports/pose_protocol.json"
VERDICT_IN_REPO = "pipeline/reports/pose_verdict.json"
CODE_IN_REPO = "pipeline/src/tracklab/pose"  # the code that computes task 60's figures
STAGE_DESIGN = "design"
STAGE_FROZEN = "frozen"

Array = NDArray[np.float64]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # utf-8 explicitly: `text=True` would decode the blob in the console code page.
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8", check=False
    )


def repo_root() -> Path:
    """The repository this code lives in: the only one the guard ever asks."""
    here = Path(__file__).resolve().parent
    out = _git(here, "rev-parse", "--show-toplevel")
    if out.returncode != 0:
        raise HeldOutLocked(f"{here} is not inside a git repository")
    return Path(out.stdout.strip())


def head_commit() -> str:
    out = _git(repo_root(), "rev-parse", "HEAD")
    if out.returncode != 0:
        raise HeldOutLocked(f"git rev-parse HEAD failed: {out.stderr.strip()}")
    return out.stdout.strip()


def code_tree_sha() -> str:
    """The sha of the tree `CODE_IN_REPO` as committed in HEAD."""
    out = _git(repo_root(), "rev-parse", f"HEAD:{CODE_IN_REPO}")
    if out.returncode != 0:
        raise HeldOutLocked(f"git rev-parse HEAD:{CODE_IN_REPO} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def dirty_code_paths() -> list[str]:
    """The uncommitted paths under `CODE_IN_REPO` or at `PROTOCOL_IN_REPO`: the probe's write
    mode refuses while any is listed, so `head_commit` and `code_tree_sha` name the code that
    ran."""
    found: list[str] = []
    for line in dirty_paths(repo_root()):
        path = line[3:].split(" -> ")[-1].strip('"')
        if path == PROTOCOL_IN_REPO or path.startswith(CODE_IN_REPO + "/"):
            found.append(path)
    return found


def dirty_among(paths_in_repo: tuple[str, ...]) -> list[str]:
    """Which of `paths_in_repo` (from the repository's root) are uncommitted."""
    dirty = [line[3:].split(" -> ")[-1].strip('"') for line in dirty_paths(repo_root())]
    return [p for p in paths_in_repo if p in dirty]


def committed_protocol() -> dict[str, Any]:
    """The protocol committed in HEAD, verified: `content_sha256` covers the file and
    `fingerprint` is the sha256 of `design`."""
    root = repo_root()
    out = _git(root, "show", f"HEAD:{PROTOCOL_IN_REPO}")
    if out.returncode != 0:
        raise HeldOutLocked(f"HEAD of {root} holds no {PROTOCOL_IN_REPO}")
    payload: dict[str, Any] = json.loads(out.stdout)
    if not sealed(payload):
        raise HeldOutLocked(
            f"the protocol committed in HEAD fails its content_sha256: {PROTOCOL_IN_REPO} "
            "was edited without being rewritten by the code"
        )
    if payload.get("fingerprint") != fingerprint(payload["design"]):
        raise HeldOutLocked("the fingerprint committed in HEAD is not the sha256 of its design")
    return payload


def committed_verdict(protocol: dict[str, Any]) -> dict[str, Any]:
    """The verdict of the second time committed in HEAD, verified against the frozen `protocol`:
    sealed, computed against its `content_sha256` by the code tree the freeze recorded."""
    out = _git(repo_root(), "show", f"HEAD:{VERDICT_IN_REPO}")
    if out.returncode != 0:
        raise HeldOutLocked(
            f"HEAD holds no {VERDICT_IN_REPO}: the second time on 1925299 is not committed"
        )
    verdict: dict[str, Any] = json.loads(out.stdout)
    if not sealed(verdict):
        raise HeldOutLocked(f"the {VERDICT_IN_REPO} committed in HEAD fails its content_sha256")
    if (verdict.get("protocol") or {}).get("content_sha256") != protocol.get("content_sha256"):
        raise HeldOutLocked("the verdict committed in HEAD answers to another protocol")
    if verdict.get("code_tree_sha") != (protocol.get("frozen") or {}).get("code_tree_sha"):
        raise HeldOutLocked("the verdict committed in HEAD was not computed by the frozen code")
    return verdict


def committed_split() -> tuple[list[int], list[int]]:
    """(calibration, confirmation) as the committed protocol names them."""
    split = committed_protocol()["design"]["split"]
    return [int(m) for m in split["calibration"]], [int(m) for m in split["confirmation"]]


def assert_confirmation_open() -> None:
    """The conditions the confirmation match opens on, read from HEAD and the environment (the
    module's docstring lists them), in that order."""
    payload = committed_protocol()
    stage = payload.get("stage")
    if stage != STAGE_FROZEN:
        raise HeldOutLocked(
            f"the protocol committed in HEAD is in stage {stage!r}, not {STAGE_FROZEN!r}: "
            "the confirmation match stays closed"
        )
    history = payload.get("history") or []
    frozen_at = next((i for i, h in enumerate(history) if h.get("stage") == STAGE_FROZEN), None)
    if (
        frozen_at is None
        or frozen_at == 0
        or any(h.get("stage") != STAGE_DESIGN for h in history[:frozen_at])
    ):
        raise HeldOutLocked(
            "the protocol committed in HEAD says frozen but its history has no frozen entry "
            "after the design ones: the stage was set without the freeze"
        )
    recorded = (payload.get("frozen") or {}).get("code_tree_sha")
    tree = code_tree_sha()
    if recorded != tree:
        raise HeldOutLocked(
            f"the {CODE_IN_REPO} tree committed in HEAD ({tree[:12]}) is not the one the "
            f"freeze recorded ({str(recorded)[:12]}): a code commit after the freeze opens "
            "nothing"
        )
    numpy = importlib.metadata.version("numpy")
    if numpy != payload["design"].get("dependencies", {}).get("numpy"):
        raise HeldOutLocked(f"numpy {numpy} is installed, not the one the protocol names")
    verdict = committed_verdict(payload)
    if (verdict.get("verdict") or {}).get("alive") is not True:
        raise HeldOutLocked("P6 died on 1925299 (pose_verdict.json): 1996435 is never opened")
    half_iqr = (verdict.get("m4") or {}).get("half_iqr_hz")
    if not (isinstance(half_iqr, int | float) and math.isfinite(half_iqr)):
        raise HeldOutLocked("pose_verdict.json holds no finite m4.half_iqr_hz for M4")
    dirty = dirty_paths(repo_root())
    if dirty:
        raise HeldOutLocked(
            f"the working tree is dirty ({len(dirty)} path(s), e.g. {dirty[0]!r}): "
            "the confirmation match opens only to committed code"
        )


def require_readable(match_id: int) -> None:
    """Allow what returns pose values to run on `match_id`: the calibration match always, the
    confirmation one only past the guard, any other never."""
    calibration, confirmation = committed_split()
    if match_id in confirmation:
        assert_confirmation_open()
    elif match_id not in calibration:
        raise ValueError(f"match {match_id} is neither the calibration nor the confirmation one")


@dataclass(frozen=True)
class PoseRows:
    """The `bodypose_players` rows of one match, sorted by player and frame: `joints` (n, 29, 3)
    and `mae_cm` (n, 29) follow `JOINTS`, in float32 as the bronze stores them; `x`, `y` are
    the file's own. Built only past the guard: `__post_init__` runs `require_readable`."""

    match_id: int
    player_id: NDArray[np.int64]
    frame: NDArray[np.int64]
    period: NDArray[np.int64]
    x: Array
    y: Array
    joints: NDArray[np.float32]
    mae_cm: NDArray[np.float32]

    def __post_init__(self) -> None:
        require_readable(self.match_id)

    def players(self) -> list[tuple[int, slice]]:
        """(player_id, the slice of his rows) for every player, by id."""
        ids, starts = np.unique(self.player_id, return_index=True)
        stops = [*starts[1:], len(self.player_id)]
        return [(int(p), slice(int(a), int(b))) for p, a, b in zip(ids, starts, stops, strict=True)]


def _read_players(path: Path, match_id: int) -> dict[str, Any]:
    """Every row of one `bodypose_players` file, sorted by player and frame: the one read. Every
    row must carry `match_id`: a file of another match under this name is refused."""
    table = pq.read_table(
        path, columns=["match_id", "frame", "period", "player_id", "x", "y", "joints", "mae"]
    ).sort_by([("player_id", "ascending"), ("frame", "ascending")])
    if set(table.column("match_id").unique().to_pylist()) - {match_id}:
        raise ValueError(f"{path}: rows of another match than {match_id}")
    if table.column("period").null_count:
        raise ValueError(f"{path}: a row with a pose has no period")
    n = table.num_rows
    return {
        "player_id": table.column("player_id").to_numpy().astype(np.int64),
        "frame": table.column("frame").to_numpy().astype(np.int64),
        "period": table.column("period").to_numpy().astype(np.int64),
        "x": table.column("x").to_numpy().astype(np.float64),
        "y": table.column("y").to_numpy().astype(np.float64),
        "joints": table.column("joints")
        .combine_chunks()
        .flatten()
        .to_numpy()
        .reshape(n, len(JOINTS), 3),
        "mae_cm": table.column("mae").combine_chunks().flatten().to_numpy().reshape(n, len(JOINTS)),
    }


def load_players(data_dir: Path, match_id: int) -> PoseRows:
    """The `bodypose_players` rows of `match_id`, past the guard before any file is opened."""
    require_readable(match_id)
    path = bronze_path(data_dir, "football", "bodypose_players", match_id)
    return PoseRows(match_id, **_read_players(path, match_id))


class CountingHandle:
    """A match's two bronze files, for counting: no guard, and nothing it returns holds a
    position (save the two listed in the module's docstring)."""

    def __init__(self, data_dir: Path, match_id: int) -> None:
        self._frames = bronze_path(data_dir, "football", "bodypose_frames", match_id).as_posix()
        self._players = bronze_path(data_dir, "football", "bodypose_players", match_id).as_posix()
        self._lineup = bronze_path(data_dir, "football", "match_players", match_id).as_posix()
        self._con: duckdb.DuckDBPyConnection | None = None

    def _rows(self, sql: str, table: str) -> list[tuple[Any, ...]]:
        if self._con is None:
            self._con = duckdb.connect()
        path = {"frames": self._frames, "players": self._players, "lineup": self._lineup}[table]
        return self._con.execute(sql, [path]).fetchall()

    def exists(self) -> bool:
        return Path(self._frames).is_file() and Path(self._players).is_file()

    def is_whole(self) -> bool:
        """The bronze holds every line of the member: `source_row` runs 0..n-1 without a cut."""
        ((n, lo, hi),) = self._rows(
            "select count(*), min(source_row), max(source_row) from read_parquet(?)", "frames"
        )
        return bool(n) and lo == 0 and hi == n - 1

    def frames_by_period(self) -> list[tuple[Any, ...]]:
        """Per period of `bodypose_frames` (None outside every period): frames, frames with a
        pose, frame-players listed, frame-players with a pose, least and most players listed
        in a frame, least (over frames with one) and most skeletons in a frame."""
        return self._rows(
            """
            select period, count(*), count(*) filter (where n_with_pose > 0),
                   sum(n_players)::bigint, sum(n_with_pose)::bigint, min(n_players),
                   max(n_players), min(n_with_pose) filter (where n_with_pose > 0),
                   max(n_with_pose)
            from read_parquet(?) group by period
            """,
            "frames",
        )

    def players_by_period(self) -> list[tuple[Any, ...]]:
        """Per period of `bodypose_players`: rows, rows detected, joint observations."""
        return self._rows(
            "select period, count(*), count(*) filter (where is_detected), sum(len(mae))::bigint "
            "from read_parquet(?) group by period",
            "players",
        )

    def frames_present(self) -> dict[int, int]:
        """Frames each listed player appears in, with a pose or without."""
        rows = self._rows(
            "select pid, count(*) from (select unnest(player_ids) as pid "
            "from read_parquet(?)) group by pid",
            "frames",
        )
        return {int(pid): int(n) for pid, n in rows}

    def frames_posed(self) -> dict[int, tuple[int, int]]:
        """Per player with a pose: (rows, rows detected)."""
        return {
            int(r[0]): (int(r[1]), int(r[2]))
            for r in self._rows(
                "select player_id, count(*), count(*) filter (where is_detected) "
                "from read_parquet(?) group by player_id",
                "players",
            )
        }

    def runs(self, minima: tuple[int, ...]) -> dict[int, tuple[int, ...]]:
        """Per player: his longest stretch of consecutive frames with a pose inside a period,
        and how many stretches reach each of `minima`."""
        counts = ", ".join(f"count(*) filter (where len >= {int(m)})" for m in minima)
        return {
            int(r[0]): tuple(int(v) for v in r[1:])
            for r in self._rows(
                f"""
                with s as (
                  select player_id, period, frame,
                         frame - row_number() over (partition by player_id, period order by frame) g
                  from read_parquet(?)
                ), r as (select player_id, count(*) len from s group by player_id, period, g)
                select player_id, max(len), {counts} from r group by player_id
                """,
                "players",
            )
        }

    def run_lengths(self, top: int = 3) -> list[tuple[int, int]]:
        """The `top` commonest stretch lengths over every player and period: (length, count)."""
        rows = self._rows(
            f"""
            with s as (
              select player_id, period,
                     frame - row_number() over (partition by player_id, period order by frame) g
              from read_parquet(?)
            ), r as (select count(*) len from s group by player_id, period, g)
            select len, count(*) n from r group by len order by n desc, len limit {int(top)}
            """,
            "players",
        )
        return [(int(length), int(n)) for length, n in rows]

    def mae_cm(self) -> tuple[tuple[Any, ...], list[tuple[Any, ...]]]:
        """Listed exception: (min, p50, p90, max) of every `p90_mae_cm`, and per joint of
        `JOINTS`, (min, p50, p90, max). The provider's predicted error, not a position."""
        ((lo, p50, p90, hi),) = self._rows(
            "select min(m), quantile_cont(m, 0.5), quantile_cont(m, 0.9), max(m) "
            "from (select unnest(mae)::double as m from read_parquet(?))",
            "players",
        )
        cols = ", ".join(
            f"min(mae[{j}]::double), quantile_cont(mae[{j}]::double, [0.5, 0.9]), "
            f"max(mae[{j}]::double)"
            for j in range(1, len(JOINTS) + 1)
        )
        (row,) = self._rows(f"select {cols} from read_parquet(?)", "players")
        by_joint = []
        for i in range(len(JOINTS)):
            j_lo, (j_50, j_90), j_hi = row[3 * i : 3 * i + 3]
            by_joint.append((j_lo, j_50, j_90, j_hi))
        return (lo, p50, p90, hi), by_joint

    def z_range_m(self) -> tuple[float | None, float | None]:
        """Listed exception: the least and the greatest z over every joint and row (z relative
        to the player's centroid, never a height), both taken in the SQL: two numbers."""
        zs = ", ".join(f"joints[{3 * j + 3}]::double" for j in range(len(JOINTS)))
        ((lo, hi),) = self._rows(
            f"select min(least({zs})), max(greatest({zs})) from read_parquet(?)", "players"
        )
        return lo, hi

    def lineup(self) -> list[tuple[int, int, int]]:
        """(player_id, team_id, number) of every player of the match's `match_players`, by
        team and number: the order the metric's rows follow (task 61)."""
        if not Path(self._lineup).is_file():
            return []
        rows = self._rows(
            "select id, team_id, number from read_parquet(?) order by team_id, number, id",
            "lineup",
        )
        return [(int(i), int(t), int(n)) for i, t, n in rows]
