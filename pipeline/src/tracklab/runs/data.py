"""The two halves of P5, and the guard on the held-out one (task 47, D11 of the sister repo).

Every match id of either half comes from the protocol committed in HEAD of the repository
that holds this code, never from the working copy: the blob is read with `git show`, its
`content_sha256` and its `fingerprint` are verified, and the two lists are regenerated from
the 20 rows it carries with `protocol.split_matches`; the lists written in the file are
compared with them and never trusted on their own. For the held-out half the committed
protocol must also be in stage `frozen` and the working tree clean, untracked files included,
so what reads the held-out half is exactly the committed code and the committed rules.
Anything else raises `HeldOutLocked`, and no held-out id leaves this module.

There is no path argument (review of tasks 47-48): the repository is the one this file lives
in. Tests exercise throwaway repositories by monkeypatching `repo_root`, and a test greps
`src/` so nothing there does. What the freeze adds to the guard (the candidates, a sha of
the code tree) belongs to task 50's spec and is said there.

Two ways to touch a match's tracking (second review of 47-48): `require_readable`, for
anything that returns a value of it, and `counting_handle`, which lets `windows.load_tracking`
load any match of the protocol for `windows.count_match` alone; the value functions refuse a
tracking loaded with a handle, whichever half it is in.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tracklab.runs.protocol import (
    STAGE_FROZEN,
    fingerprint,
    rows_from_protocol,
    sealed,
    split_matches,
)

Half = Literal["calibration", "held_out"]
PROTOCOL_IN_REPO = "pipeline/reports/runs_protocol.json"


class HeldOutLocked(RuntimeError):
    """The committed protocol cannot vouch for what was asked: missing or unverifiable in
    HEAD, not frozen, or a dirty working tree."""


class CountingOnly(RuntimeError):
    """A tracking loaded with a `CountingHandle` was asked for a value."""


@dataclass(frozen=True)
class CountingHandle:
    """Leave to load the tracking of one match for counting only. Issued by `counting_handle`
    for any id of the protocol, both halves, because counting runs, frames and detected
    positions is not an outcome; `windows.quantities`, `run_direction` and `pair_effects`
    refuse a tracking loaded with it."""

    match_id: int


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


def _head_text(root: Path) -> str | None:
    out = _git(root, "show", f"HEAD:{PROTOCOL_IN_REPO}")
    return out.stdout if out.returncode == 0 else None


def head_stage() -> str | None:
    """The `stage` of the protocol as committed in HEAD, or None when HEAD has no such file."""
    text = _head_text(repo_root())
    if text is None:
        return None
    stage = json.loads(text).get("stage")
    return str(stage) if stage is not None else None


def committed_protocol() -> dict[str, Any]:
    """The protocol committed in HEAD, verified: `content_sha256` covers the file and
    `fingerprint` is the sha256 of `design`. A hand edit committed without resealing fails."""
    root = repo_root()
    text = _head_text(root)
    if text is None:
        raise HeldOutLocked(f"HEAD of {root} holds no {PROTOCOL_IN_REPO}")
    payload: dict[str, Any] = json.loads(text)
    if not sealed(payload):
        raise HeldOutLocked(
            f"the protocol committed in HEAD fails its content_sha256: {PROTOCOL_IN_REPO} "
            "was edited without being rewritten by the code"
        )
    if payload.get("fingerprint") != fingerprint(payload["design"]):
        raise HeldOutLocked("the fingerprint committed in HEAD is not the sha256 of its design")
    return payload


def committed_split() -> tuple[list[int], list[int]]:
    """(calibration, held_out) regenerated from the committed rows; the committed lists must
    agree with them."""
    payload = committed_protocol()
    calibration, held_out = split_matches(rows_from_protocol(payload))
    split = payload["design"]["split"]
    if (calibration, held_out) != (
        [int(m) for m in split["calibration"]],
        [int(m) for m in split["held_out"]],
    ):
        raise HeldOutLocked("the split lists committed in HEAD are not what its rows regenerate")
    return calibration, held_out


def dirty_paths(repo: Path) -> list[str]:
    """What `git status --porcelain --untracked-files=all` lists: modified, staged and
    untracked (every file, whatever `status.showUntrackedFiles` says), ignored left out."""
    out = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if out.returncode != 0:
        raise HeldOutLocked(f"git status failed in {repo}: {out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def assert_held_out_open() -> None:
    stage = committed_protocol().get("stage")
    if stage != STAGE_FROZEN:
        raise HeldOutLocked(
            f"the protocol committed in HEAD is in stage {stage!r}, not {STAGE_FROZEN!r}: "
            "the held-out half stays closed"
        )
    dirty = dirty_paths(repo_root())
    if dirty:
        raise HeldOutLocked(
            f"the working tree is dirty ({len(dirty)} path(s), e.g. {dirty[0]!r}): "
            "the held-out half opens only to committed code"
        )


def load_half(half: Half) -> list[int]:
    """The match ids of one half, from the committed protocol. The held-out half passes the
    guard first."""
    if half == "held_out":
        assert_held_out_open()
    calibration, held_out = committed_split()
    return held_out if half == "held_out" else calibration


def counting_match_ids() -> list[int]:
    """The ids of all 20 matches, both halves, for counting runs and frames (task 48).

    This is not a way round the guard on `load_half`: the guard stops outcomes on the held-out
    half, and the ids, the kickoffs and the run counts were public in the protocol and the
    inventory before the split existed. Their tracking is loaded with `counting_handle`, which
    yields counts alone; a caller that gets tracking values out of a match goes through
    `require_readable`, which applies the guard per match."""
    calibration, held_out = committed_split()
    return sorted(calibration + held_out)


def counting_handle(match_id: int) -> CountingHandle:
    """The handle `windows.load_tracking` takes to load `match_id` for `count_match` alone, for
    any match of the protocol; no guard, because nothing a counting-only tracking yields is a
    value of it."""
    calibration, held_out = committed_split()
    if match_id not in calibration and match_id not in held_out:
        raise ValueError(f"match {match_id} is in neither half of the protocol")
    return CountingHandle(match_id)


def match_halves() -> dict[int, str]:
    """Which half each of the 20 matches belongs to, for the `half` column of the coverage
    file (counting only, see `counting_match_ids`)."""
    calibration, held_out = committed_split()
    return {**dict.fromkeys(calibration, "calibration"), **dict.fromkeys(held_out, "held_out")}


def require_readable(match_id: int) -> None:
    """Allow a function that returns tracking values (displacements, residuals, line heights)
    to run on `match_id`: calibration matches always, held-out ones only past the guard."""
    calibration, held_out = committed_split()
    if match_id in held_out:
        assert_held_out_open()
    elif match_id not in calibration:
        raise ValueError(f"match {match_id} is in neither half of the protocol")
