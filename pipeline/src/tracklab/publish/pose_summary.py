"""`web/public/data/pose.json`: what the page `/pose` says, every figure read from a report
(task 62 of tasks/todo.md, P6). Nothing here is typed except the names of the fields.

* `status`: `alive` (M1, M2 and M4 pass), `unreplicated` (1996435 does not reach the minima
  of M1 and M2: not evaluable by coverage, not dead) or `dead`, with `dead_at` `noise` (the rule
  of (W, cap) found no cell), `M1`, `M2` or `M4`.
* the three limits of SkillCorner with their line of the README, the coverage per match and
  period, the protocol with the sha of each stage, and what was not opened.
* if P6 lives or is unreplicated: the tables per match and per player of `pose_metric.json`
  (the denominator in every row, the propagated sd beside each value) and M3's concordance,
  published without a propagated error and saying so.
* `clips`: the files under `pose/` with their bytes and sha256.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tracklab.publish import pose as base

SCHEMA_VERSION = 1
REPORT_FILES = {
    "protocol": "pose_protocol.json",
    "coverage": "pose_coverage.json",
    "calibration": "pose_calibration.json",
    "verdict": "pose_verdict.json",
    "metric": "pose_metric.json",
    "clip": base.RECORD_FILE,
}
OPTIONAL = ("verdict", "metric")
DEAD_AT = {"m1": "M1", "m2_coverage": "M2", "m2_sign": "M2", "m2_precision": "M2"}


def load_reports(reports_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, name in REPORT_FILES.items():
        path = reports_dir / name
        if path.is_file():
            out[key] = base._load(path)
        elif key not in OPTIONAL:
            raise base.PosePublishError(f"{path} is missing")
    return out


def status_of(reports: dict[str, Any]) -> tuple[str, str | None]:
    """(status, dead_at), from the reports: the rule of (W, cap) first, then M1 and M2 of the
    verdict on 1925299, then M4 of the metric."""
    if reports["calibration"]["rule_w_cap"].get("chosen") is None:
        return "dead", "noise"
    verdict = reports.get("verdict")
    if verdict is None:
        raise base.PosePublishError("the rule chose a cell but pose_verdict.json is missing")
    dies = verdict["verdict"].get("dies_at")
    if dies is not None:
        return "dead", DEAD_AT[dies]
    metric = reports.get("metric")
    if metric is None:
        raise base.PosePublishError("P6 lives on 1925299 but pose_metric.json is missing")
    p6 = metric["verdicts"]["p6"]
    if p6 == "alive":
        return "alive", None
    if p6 == "unreplicated":
        return "unreplicated", None
    if p6 == "replication_failed":
        return "dead", "M4"
    raise base.PosePublishError(f"pose_metric.json says p6 {p6!r}")


def _coverage(reports: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "frames",
        "frames_with_pose",
        "player_frames",
        "with_pose",
        "share_frames_with_pose",
        "share_player_frames_with_pose",
        "skeletons_per_frame",
    )
    out = {}
    for match, c in reports["coverage"]["matches"].items():
        out[match] = {
            "periods": {
                k: {f: v[f] for f in keep} for k, v in c["periods"].items() if k != "outside"
            },
            "total": {f: c["periods"]["total"][f] for f in keep},
            "players_with_pose": len(c["players"]),
            "mae_cm": {
                "all": c["mae_cm"]["all"],
                "ankles": {j: c["mae_cm"]["by_joint"][j] for j in ("lAnkle", "rAnkle")},
            },
        }
    return out


def _stages(reports: dict[str, Any]) -> list[dict[str, Any]]:
    """The sha of the protocol at each stage: the fingerprint of the design, the seal of the
    frozen file with the code tree and the calibration it froze, and the seals of the verdict
    and of the metric that answered to it."""
    protocol = reports["protocol"]
    frozen = protocol.get("frozen")
    stages = [
        {"stage": "design", "sha256": protocol["fingerprint"], "what": "fingerprint of the design"}
    ]
    if frozen is not None:
        stages.append(
            {
                "stage": "frozen",
                "sha256": protocol["content_sha256"],
                "what": "seal of pose_protocol.json",
                "code_tree_sha": frozen["code_tree_sha"],
                "calibration_sha256": frozen["calibration_from"]["content_sha256"],
            }
        )
    for key, label in (("verdict", "verdict on 1925299"), ("metric", "metric on both matches")):
        if key in reports:
            stages.append(
                {
                    "stage": key,
                    "sha256": reports[key]["content_sha256"],
                    "what": f"seal of the {label}",
                }
            )
    return stages


def _protocol(reports: dict[str, Any]) -> dict[str, Any]:
    protocol = reports["protocol"]
    frozen = protocol.get("frozen") or {}
    split = protocol["design"]["split"]
    return {
        "stage": protocol["stage"],
        "calibration": split["calibration"][0],
        "confirmation": split["confirmation"][0],
        "width": frozen.get("width"),
        "cap_cm": frozen.get("cap_cm"),
        "bands": {
            "low_m_s": protocol["design"]["bands"]["low_m_s"],
            "high_m_s_from": protocol["design"]["bands"]["high_m_s_from"],
        },
        "numbers": protocol["design"]["numbers"],
        "blind_spots": protocol["design"]["death_criteria"]["blind_spots"],
        "stages": _stages(reports),
    }


def _verdict(reports: dict[str, Any]) -> dict[str, Any]:
    if "metric" in reports:
        return {"source": REPORT_FILES["metric"], **reports["metric"]["verdicts"]}
    if "verdict" in reports:
        return {"source": REPORT_FILES["verdict"], **reports["verdict"]["verdict"]}
    return {"source": REPORT_FILES["calibration"], "chosen": None}


def _opened(reports: dict[str, Any]) -> dict[str, Any]:
    """What was not opened: 1996435's joints are read only by the metric, which is written
    only when P6 lives on 1925299."""
    seen = reports["protocol"]["design"]["seen_of_confirmation"]
    opened = "metric" in reports
    return {
        "confirmation_match_opened": opened,
        "at_the_freeze": {"not_seen": seen["not_seen"], "consequence": seen["consequence"]},
        "not_opened": [] if opened else [reports["protocol"]["design"]["split"]["confirmation"][0]],
    }


def _tables(reports: dict[str, Any]) -> dict[str, Any]:
    metric = reports["metric"]
    return {
        "note": metric["note"],
        "columns": metric["columns"],
        "matches": metric["matches"],
        "m3": "the concordance of M3 (m3_abs_diff_p50_hz, m3_nan_h_share) carries no propagated "
        "error: the sd propagated to cad_h is not calibrated (phase B1 of task 60)",
        "order": "by team and shirt number, never by a metric",
    }


def build_summary(reports: dict[str, Any], clips: list[dict[str, Any]]) -> dict[str, Any]:
    status, dead_at = status_of(reports)
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "dead_at": dead_at,
        "limits": [dict(item) for item in base.LIMITS],
        "protocol": _protocol(reports),
        "verdict": _verdict(reports),
        "opened": _opened(reports),
        "coverage": _coverage(reports),
        "phase406": {
            "file": reports["clip"]["clip"]["file"],
            "bytes": reports["clip"]["clip"]["bytes"],
            "sha256": reports["clip"]["clip"]["sha256"],
            "coverage": reports["clip"]["coverage"],
        },
        "clips": clips,
        "tables": _tables(reports) if status in ("alive", "unreplicated") else None,
    }
    return out
