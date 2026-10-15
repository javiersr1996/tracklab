"""`tracklab pose freeze`: the protocol frozen at the (W, cap) the rule chose (task 60 of
tasks/todo.md, phase B2). Written and tested before the freeze, because the freeze records the
`pose/` tree and a later code commit closes 1996435 for good.

It refuses unless the protocol on disk is the design committed in HEAD, the code, the protocol
and `reports/pose_calibration.json` are committed, and that calibration passes the probe's own
check (seal, protocol, rule following the sweep and its figures). It writes the frozen file
(`protocol.freeze_payload`) and nothing else: the freeze commit is the caller's.
"""

from __future__ import annotations

import json
from pathlib import Path

from tracklab.pose import probe, sweep
from tracklab.pose.data import (
    code_tree_sha,
    committed_protocol,
    committed_split,
    dirty_among,
    dirty_code_paths,
)
from tracklab.pose.protocol import (
    CALIBRATION_NAME,
    PROTOCOL_NAME,
    freeze_payload,
    render,
)

CALIBRATION_IN_REPO = f"pipeline/reports/{CALIBRATION_NAME}"


def run_pose_freeze(reports_dir: Path, *, date: str) -> int:
    path = reports_dir / PROTOCOL_NAME
    current = json.loads(path.read_text(encoding="utf-8"))
    if current != committed_protocol():
        print(f"pose freeze: {path} is not the protocol committed in HEAD")
        return 1
    dirty = dirty_code_paths() + dirty_among((CALIBRATION_IN_REPO,))
    if dirty:
        print(f"pose freeze: {len(dirty)} path(s) not committed (e.g. {dirty[0]!r})")
        return 1
    calibration = json.loads((reports_dir / CALIBRATION_NAME).read_text(encoding="utf-8"))
    sweep_report = json.loads((reports_dir / sweep.SWEEP_NAME).read_text(encoding="utf-8"))
    (match,) = committed_split()[0]
    problems = probe.consistency_problems(calibration, match, sweep_report)
    if problems:
        print(f"pose freeze: {CALIBRATION_NAME}: " + "; ".join(problems))
        return 1
    try:
        payload = freeze_payload(current, calibration, code_tree=code_tree_sha(), date=date)
    except ValueError as exc:
        print(f"pose freeze: {exc}")
        return 1
    path.write_text(render(payload), encoding="utf-8", newline="\n")
    frozen = payload["frozen"]
    print(
        f"pose freeze: {path} frozen at W {frozen['width']}, cap {frozen['cap_cm']} cm, pose/ "
        f"tree {frozen['code_tree_sha'][:12]}; commit it alone, then run pose verdict"
    )
    return 0
