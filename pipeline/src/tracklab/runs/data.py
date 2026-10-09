"""The two halves of P5, and the guard on the held-out one (task 47, D11 of the sister repo).

`load_half("calibration")` returns the calibration match ids of the protocol. For
`"held_out"` it first asks git: the protocol committed in HEAD must be in stage `frozen`
and the working tree must be clean, so what reads the held-out half is exactly the committed
code and the committed rules. Anything else raises `HeldOutLocked`, and no match id of the
held-out half leaves this module.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Literal

from tracklab.runs.protocol import PROTOCOL_NAME, STAGE_FROZEN, read_protocol

Half = Literal["calibration", "held_out"]
DEFAULT_PROTOCOL = Path("reports") / PROTOCOL_NAME


class HeldOutLocked(RuntimeError):
    """The held-out half asked for before the protocol is frozen in a clean tree."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


def repo_root(path: Path) -> Path:
    out = _git(path.resolve().parent, "rev-parse", "--show-toplevel")
    if out.returncode != 0:
        raise HeldOutLocked(f"{path} is not inside a git repository")
    return Path(out.stdout.strip())


def head_stage(protocol_path: Path) -> str | None:
    """The `stage` of the protocol as committed in HEAD, or None when HEAD has no such file."""
    root = repo_root(protocol_path)
    relative = protocol_path.resolve().relative_to(root).as_posix()
    out = _git(root, "show", f"HEAD:{relative}")
    if out.returncode != 0:
        return None
    stage = json.loads(out.stdout).get("stage")
    return str(stage) if stage is not None else None


def dirty_paths(repo: Path) -> list[str]:
    """What `git status --porcelain` lists: modified, staged and untracked, ignored left out."""
    out = _git(repo, "status", "--porcelain")
    if out.returncode != 0:
        raise HeldOutLocked(f"git status failed in {repo}: {out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def assert_held_out_open(protocol_path: Path = DEFAULT_PROTOCOL) -> None:
    stage = head_stage(protocol_path)
    if stage != STAGE_FROZEN:
        raise HeldOutLocked(
            f"the protocol committed in HEAD is in stage {stage!r}, not {STAGE_FROZEN!r}: "
            "the held-out half stays closed"
        )
    dirty = dirty_paths(repo_root(protocol_path))
    if dirty:
        raise HeldOutLocked(
            f"the working tree is dirty ({len(dirty)} path(s), e.g. {dirty[0]!r}): "
            "the held-out half opens only to committed code"
        )


def load_half(half: Half, protocol_path: Path = DEFAULT_PROTOCOL) -> list[int]:
    """The match ids of one half. The held-out half passes the guard first."""
    if half == "held_out":
        assert_held_out_open(protocol_path)
    ids = read_protocol(protocol_path)["design"]["split"][half]
    return [int(m) for m in ids]


def counting_match_ids(protocol_path: Path = DEFAULT_PROTOCOL) -> list[int]:
    """The ids of all 20 matches, both halves, for counting runs and frames (task 48).

    This is not a way round the guard on `load_half`: the guard stops outcomes on the held-out
    half, and the ids, the kickoffs and the run counts were public in the protocol and the
    inventory before the split existed. A caller that gets tracking values out of a match
    goes through `require_readable`, which applies the guard per match."""
    matches = read_protocol(protocol_path)["design"]["split"]["matches"]
    return sorted(int(m["match_id"]) for m in matches)


def require_readable(match_id: int, protocol_path: Path = DEFAULT_PROTOCOL) -> None:
    """Allow a function that returns tracking values (displacements, residuals, line heights)
    to run on `match_id`: calibration matches always, held-out ones only past the guard."""
    split = read_protocol(protocol_path)["design"]["split"]
    if match_id in split["held_out"]:
        assert_held_out_open(protocol_path)
    elif match_id not in split["calibration"]:
        raise ValueError(f"match {match_id} is in neither half of the protocol")
