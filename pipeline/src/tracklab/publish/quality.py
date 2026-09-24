"""`tracklab publish quality`: `web/public/data/quality.json` and `docs/bulletin.md`,
built from the six `reports/quality_*.csv` the checks of `tracklab.quality` already
wrote (task 30). Every figure in the bulletin and every metric in the JSON's
`checks` section is a value already sitting in one of those CSVs; the `summary`
section holds the small counts (how many matches fall on each side of a split)
the bulletin's prose needs and that no single CSV cell already is; the `hook`
section is the one part that goes back to bronze and silver, reusing
`tracklab.quality.gravity`'s flight-finding helpers to pick one real basketball
shot and pair its samples with the trajectory 9.80665 m/s^2 would draw from the
same position and velocity the flight's own fit has at t=0 (its vertex need not
land exactly on the highest sample).
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from tracklab.quality.common import report_path
from tracklab.quality.flight import G, apparent_g, fit_quadratic
from tracklab.quality.gravity import (
    BB_HALF,
    CALIBRATION,
    MAX_RMS,
    Sample,
    _ball_samples,
    _rebounds,
    _shot_window,
)
from tracklab.quality.run import CHECKS

QUALITY_JSON = "quality.json"
BULLETIN_MD = "bulletin.md"

# Per check, the metrics `web/app/quality/page.tsx` and the bulletin show. The
# rest of each CSV (candidate counts, exclusion reasons) stays methodology
# detail in reports/, read by anyone who wants to audit a figure, not echoed here.
KEEP: dict[str, tuple[str, ...]] = {
    "detection": ("ball_detected_pct", "player_detected_pct"),
    "gravity": ("flights", "g_median", "g_q1", "g_q3", "g_median_bias_pct", "is_calibration"),
    "entry_angle": (
        "shots",
        "angle_reported_median_deg",
        "angle_required_median_deg",
        "gap_median_deg",
        "pairs_reordered_pct",
    ),
    "noise": (
        "ball_d2_median_m",
        "player_d2_median_m",
        "ball_player_d2_ratio",
        "ball_pred_error_median_m",
        "player_pred_error_median_m",
    ),
    "clock": ("clock_step_exact_pct", "speed_mismatch_pct", "speed_ratio_median"),
    "partitions": (
        "frame_loss_pct",
        "frame_loss_regime_high",
        "layout_frames_outside_periods",
        "layout_extra_footage",
        "players_last_modified",
        "attack_median_m",
        "event_coords_exact",
        "partitions_agree",
    ),
}

SKILLCORNER_BODYPOSE_Z_CAVEAT = (
    "`z` is not a height above the pitch. It is accurate relative to the player's "
    "centroid, but not necessarily in the pitch coordinate system, so it can be "
    "negative. Treat it as pose geometry rather than elevation. This will improve "
    "with future Body Pose enhancements."
)
SKILLCORNER_BODYPOSE_URL = "https://huggingface.co/datasets/SkillCorner/opendata-bodypose"
SKILLCORNER_BODYPOSE_CHECKED_ON = "2026-09-24"


def quality_path(out_dir: Path) -> Path:
    return out_dir / QUALITY_JSON


def bulletin_path(docs_dir: Path) -> Path:
    return docs_dir / BULLETIN_MD


# Reading the six reports.


def _raw(reports_dir: Path, check: str) -> list[dict[str, str]]:
    with report_path(reports_dir, check).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def quality_rows(reports_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """The `KEEP` metrics of every check, sport and match, value and n cast to
    number: the JSON's `checks` section, a straight echo of CSV cells."""
    out: dict[str, list[dict[str, Any]]] = {}
    for check in sorted(CHECKS):
        keep = KEEP[check]
        rows = [
            {
                "sport": row["sport"],
                "match_id": row["match_id"],
                "metric": row["metric"],
                "value": float(row["value"]),
                "unit": row["unit"],
                "n": int(row["n"]),
            }
            for row in _raw(reports_dir, check)
            if row["metric"] in keep
        ]
        out[check] = sorted(rows, key=lambda r: (r["sport"], r["match_id"], r["metric"]))
    return out


# Small, code-computed aggregates the bulletin's prose quotes: how many matches
# fall on each side of a split. Kept in the JSON's `summary` section so every
# such count is itself an artefact, not typed by hand into the bulletin.


def _filtered(
    rows: list[dict[str, str]], metric: str, sport: str, match_ids: set[str] | None = None
) -> list[dict[str, str]]:
    return [
        r
        for r in rows
        if r["metric"] == metric
        and r["sport"] == sport
        and (match_ids is None or r["match_id"] in match_ids)
    ]


def _range(rows: list[dict[str, str]], digits: int = 1) -> str:
    """The `lo to hi` of a metric's values, by magnitude, sign dropped (a bias
    is always read as "how far off", the direction is said in prose around it),
    rounded to `digits` for reading; the CSV keeps the full value."""
    if not rows:
        raise ValueError("no rows to range over")
    by_abs = sorted(abs(float(r["value"])) for r in rows)
    lo, hi = f"{by_abs[0]:.{digits}f}", f"{by_abs[-1]:.{digits}f}"
    return lo if lo == hi else f"{lo} to {hi}"


def _matches(rows: list[dict[str, str]], metric: str, sport: str, equals: str) -> list[str]:
    return sorted(
        {
            r["match_id"]
            for r in rows
            if r["metric"] == metric and r["sport"] == sport and r["value"] == equals
        }
    )


def build_summary(reports_dir: Path) -> dict[str, Any]:
    detection = _raw(reports_dir, "detection")
    gravity = _raw(reports_dir, "gravity")
    entry_angle = _raw(reports_dir, "entry_angle")
    noise = _raw(reports_dir, "noise")
    clock = _raw(reports_dir, "clock")
    partitions = _raw(reports_dir, "partitions")

    bb_calibration = _matches(gravity, "is_calibration", "basketball", "1.0")
    bb_control = _matches(gravity, "is_calibration", "basketball", "0.0")
    fb_extra_footage = _matches(partitions, "layout_extra_footage", "football", "1.0")
    bb_high_loss = _matches(partitions, "frame_loss_regime_high", "basketball", "1.0")
    fb_agree = _matches(partitions, "partitions_agree", "football", "1.0")
    fb_players_modified = _matches(partitions, "players_last_modified", "football", "1.0")

    return {
        "basketball_matches": len({r["match_id"] for r in detection if r["sport"] == "basketball"}),
        "football_matches": len({r["match_id"] for r in detection if r["sport"] == "football"}),
        "basketball_calibration_matches": len(bb_calibration),
        "basketball_control_matches": len(bb_control),
        "football_extra_footage_matches": len(fb_extra_footage),
        "football_extra_footage_match_ids": fb_extra_footage,
        "basketball_high_frame_loss_matches": len(bb_high_loss),
        "basketball_high_frame_loss_match_ids": bb_high_loss,
        "football_partitions_agree_matches": len(fb_agree),
        "football_players_last_modified_matches": len(fb_players_modified),
        "ranges": {
            "detection_ball_pct_basketball": _range(
                _filtered(detection, "ball_detected_pct", "basketball")
            ),
            "detection_player_pct_basketball": _range(
                _filtered(detection, "player_detected_pct", "basketball")
            ),
            "detection_ball_pct_football": _range(
                _filtered(detection, "ball_detected_pct", "football")
            ),
            "detection_player_pct_football": _range(
                _filtered(detection, "player_detected_pct", "football")
            ),
            "gravity_g_calibration": _range(
                _filtered(gravity, "g_median", "basketball", set(bb_calibration)), digits=2
            ),
            "gravity_bias_calibration": _range(
                _filtered(gravity, "g_median_bias_pct", "basketball", set(bb_calibration))
            ),
            "gravity_g_control": _range(
                _filtered(gravity, "g_median", "basketball", set(bb_control)), digits=2
            ),
            "gravity_bias_control": _range(
                _filtered(gravity, "g_median_bias_pct", "basketball", set(bb_control))
            ),
            "gravity_g_football": _range(_filtered(gravity, "g_median", "football"), digits=2),
            "gravity_bias_football": _range(_filtered(gravity, "g_median_bias_pct", "football")),
            "entry_angle_gap": _range(_filtered(entry_angle, "gap_median_deg", "basketball")),
            "entry_angle_reordered_pct": _range(
                _filtered(entry_angle, "pairs_reordered_pct", "basketball")
            ),
            "noise_ratio_basketball": _range(
                _filtered(noise, "ball_player_d2_ratio", "basketball")
            ),
            "noise_ratio_football": _range(_filtered(noise, "ball_player_d2_ratio", "football")),
            "noise_grid_pct_football": _range(
                _filtered(noise, "player_coord_cm_grid_pct", "football")
            ),
            "clock_step_exact_basketball": _range(
                _filtered(clock, "clock_step_exact_pct", "basketball")
            ),
            "clock_step_exact_football": _range(
                _filtered(clock, "clock_step_exact_pct", "football")
            ),
            "clock_speed_mismatch": _range(
                _filtered(clock, "speed_mismatch_pct", "basketball"), digits=2
            ),
        },
    }


# The hook: one real basketball shot, reusing `tracklab.quality.gravity`'s
# private flight-finding helpers (the same pattern `quality.entry_angle` already
# uses to reach `_ball_samples`) rather than duplicating a second reader of
# silver `frames`.


@dataclass(frozen=True)
class Flight:
    """One accepted calibration flight: its shot, its fitted g and its own
    apex-windowed samples (`t` relative to the highest sample, `z` as measured).
    `fit_c` and `fit_b` are that same fit's position and velocity at t=0 (the
    highest sample), in the samples' own time origin: the fit's vertex need not
    fall exactly on that sample, so a replay of this flight at a different
    gravity has to start from this state, not from `z_m` at t=0 with zero
    vertical velocity. Default to 0.0: only the hook's own fit needs them."""

    match_id: str
    shot_id: str
    start_frame: int
    g: float
    t_s: list[float]
    z_m: list[float]
    fit_c: float = 0.0
    fit_b: float = 0.0


def _calibration_shots(data_dir: Path) -> list[tuple[int, str, str, int, int | None, bool]]:
    """(native, match_id, shot id, startFrame, endFrame, blocked), calibration
    matches only, the same shots `quality.gravity` scores for those matches."""
    glob = (data_dir / "bronze" / "basketball" / "events_shots" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT match_id, id, startFrame, endFrame, coalesce(blocked, false)
            FROM read_parquet(?)
            WHERE startFrame IS NOT NULL
            ORDER BY match_id, startFrame, id
            """,
            [glob],
        )
        .fetchall()
    )
    return [
        (
            int(native),
            f"bb:{int(native)}",
            str(shot_id),
            int(start),
            None if end is None else int(end),
            bool(blocked),
        )
        for native, shot_id, start, end, blocked in rows
        if int(native) in CALIBRATION
    ]


def calibration_flights(data_dir: Path) -> list[Flight]:
    """Every accepted calibration flight, task 27's filters applied in the same
    order `quality.gravity._basketball` does: blocked, no window, rebound,
    residual. What differs is that this keeps the window's own samples."""
    balls = _ball_samples(data_dir)
    flights: list[Flight] = []
    for native, match_id, shot_id, start, end, blocked in _calibration_shots(data_dir):
        if blocked:
            continue
        ball = balls.get(("basketball", native), {})
        window: list[Sample] | None = _shot_window(ball, start, end)
        if window is None:
            continue
        if any(_rebounds(s) for s in window[BB_HALF + 1 :]):
            continue
        t = [s[1] for s in window]
        z = [s[4] for s in window]
        apex_t = t[BB_HALF]
        t_rel = [ti - apex_t for ti in t]
        c, b, a = fit_quadratic(t_rel, z)
        residuals = [zi - (c + b * ti + a * ti * ti) for ti, zi in zip(t_rel, z, strict=True)]
        rms = math.sqrt(statistics.fmean(r * r for r in residuals))
        if rms >= MAX_RMS:
            continue
        flights.append(
            Flight(
                match_id=match_id,
                shot_id=shot_id,
                start_frame=start,
                g=apparent_g(t_rel, z),
                t_s=[round(ti, 4) for ti in t_rel],
                z_m=[round(zi, 4) for zi in z],
                fit_c=round(c, 4),
                fit_b=round(b, 4),
            )
        )
    return flights


def select_hook_flight(flights: Sequence[Flight]) -> tuple[Flight, float]:
    """The calibration flight whose g sits closest to the calibration's own
    median, ties broken by match id then start frame: a rule, not a pick."""
    if not flights:
        raise ValueError("no calibration flights to choose a hook shot from")
    median = statistics.median(f.g for f in flights)
    best = min(flights, key=lambda f: (abs(f.g - median), f.match_id, f.start_frame))
    return best, median


def flight_z_real(flight: Flight) -> list[float]:
    """The same flight at standard gravity, starting from the exact position and
    velocity the flight's own fit (the one that gives `g_data`) has at t=0: not
    from `z_m` at t=0 with an assumed zero vertical velocity, which is only
    correct if the fit's vertex happens to land on that sample."""
    return [round(flight.fit_c + flight.fit_b * ti - 0.5 * G * ti * ti, 4) for ti in flight.t_s]


def build_hook(data_dir: Path) -> dict[str, Any]:
    flight, median = select_hook_flight(calibration_flights(data_dir))
    return {
        "match_id": flight.match_id,
        "shot_id": flight.shot_id,
        "start_frame": flight.start_frame,
        "g_data": round(flight.g, 4),
        "g_real": G,
        "median_calibration_g": round(median, 4),
        "t_s": flight.t_s,
        "z_data_m": flight.z_m,
        "z_real_m": flight_z_real(flight),
    }


# The bulletin.


def render_bulletin(summary: dict[str, Any], hook: dict[str, Any]) -> str:
    r = summary["ranges"]
    lines = [
        "# Track Lab data quality bulletin",
        "",
        "A calibration kit for anyone building on the two Track Lab bundles, not a "
        "verdict on SkillCorner: six checks, each one number (or its range) per match, "
        "read straight off `pipeline/reports/quality_*.csv`. `web/public/data/quality.json` "
        "carries the same figures for the `/quality` page, and every number below is one "
        "or the other.",
        "",
        "## Detection",
        "",
        "What it measures: how often the provider marks a tracked object as actually "
        "seen (`is_detected`), against extrapolated. Method: share of silver `frames` "
        "rows with `is_detected` true, by sport and entity kind.",
        "",
        f"Basketball ball: `{r['detection_ball_pct_basketball']}`% across all "
        f"{summary['basketball_matches']} matches. Basketball player: "
        f"{r['detection_player_pct_basketball']}%. Football ball: "
        f"{r['detection_ball_pct_football']}%. Football player: "
        f"{r['detection_player_pct_football']}%.",
        "",
        "For a consumer: `is_detected` is false for the basketball ball in all "
        f"matches ({r['detection_ball_pct_basketball']}%), so a pipeline that filters "
        "on it for the ball keeps nothing in basketball. Football detection is "
        "partial in both entity kinds and should be read per match, not assumed "
        "constant.",
        "",
        "## Gravity",
        "",
        "What it measures: the apparent gravity a ball's own vertical curve implies "
        "during free flight. Method: a parabola fit over the samples around each "
        "flight's apex (basketball: shots, +-10 frames around it; football: flights "
        "found in tracking, windows fully detected and clear of a player touch, "
        "+-6 frames around it), g = -2 times the fit's quadratic term.",
        "",
        f"Basketball calibration ({summary['basketball_calibration_matches']} matches): "
        f"median g of {r['gravity_g_calibration']} m/s², "
        f"{r['gravity_bias_calibration']}% below the standard 9.80665 m/s². "
        f"Basketball control ({summary['basketball_control_matches']} matches, scored "
        "with thresholds fixed on the calibration matches before this control group "
        f"was measured): {r['gravity_g_control']} m/s², {r['gravity_bias_control']}% below "
        "standard, confirming the calibration split rather than a filter tuned to it. "
        "Football: the number only, no verdict (its `z_ball_status` is `unverified`): "
        f"{r['gravity_g_football']} m/s², {r['gravity_bias_football']}% away from "
        "standard.",
        "",
        "For a consumer: any quantity derived from raw z during a basketball flight "
        "(release speed, hang time, apex height from timing alone) should expect a "
        "systematic low bias of the size above, not a random error. Football carries "
        "the same measurement with no calibration reference to grade it against.",
        "",
        "## Entry angle",
        "",
        "What it measures: a made shot's arrival angle at the rim from the bundle's "
        "own z curvature, against the angle true gravity requires given that same "
        "flight's horizontal speed and the bundle's own release height. Method: "
        "horizontal speed from the first samples after release, flight time from "
        "speed and distance to the rim (the only step of the two that does not use "
        "z), required vertical speed from projectile motion using the bundle's own "
        "release height, both angles compared at the same arrival frame.",
        "",
        f"Gap (required minus reported), median per match: {r['entry_angle_gap']} "
        f"degrees. Share of shot pairs the two angles order differently: "
        f"{r['entry_angle_reordered_pct']}%.",
        "",
        "For a consumer: the bundle's own entry angle is not just offset, it "
        "reorders shots against a geometry-only measure often enough that ranking "
        "shots by it (flat vs steep) will disagree with ranking them by the flight "
        "itself.",
        "",
        "## Noise",
        "",
        "What it measures: frame-to-frame jitter of the ball's horizontal position "
        "against a detected player's, while both are moving. Method: the second "
        "difference of x, y (a discrete acceleration), pooled per match, ball versus "
        "detected players, and their ratio.",
        "",
        f"Ball-to-player jitter ratio: basketball {r['noise_ratio_basketball']}×, "
        f"football {r['noise_ratio_football']}×. Football's ratio is bounded by how "
        f"its coordinates are stored, not by ball motion: {r['noise_grid_pct_football']}% "
        "of detected players' x, y sit exactly on a 1 cm grid.",
        "",
        "For a consumer: smoothing tuned on player tracks (window size, cutoff "
        "frequency) will under-smooth the basketball ball by roughly that factor if "
        "applied unchanged; the football ratio should not be used the same way, "
        "since it is capped by coordinate quantization rather than measuring motion.",
        "",
        "## Clock",
        "",
        "What it measures: whether the frame clock advances at the sport's declared "
        "rate, and, in basketball, whether the declared `speed` field matches a "
        "finite difference of consecutive positions. Method: exact-step share between "
        "native-frame-adjacent rows; for speed, the median of the per-pair ratio "
        "declared-over-measured.",
        "",
        f"Exact clock step: basketball {r['clock_step_exact_basketball']}%, football "
        f"{r['clock_step_exact_football']}% (football has no independent millisecond "
        f"field, so its number is contiguity, not a cross-check). Basketball declared "
        f"speed against measured: {r['clock_speed_mismatch']}% median mismatch.",
        "",
        "For a consumer: the clock step above is a real cross-check in basketball "
        "(against `wallClock`) and a contiguity count in football, where no "
        "independent field exists to check against. The declared `speed` field and "
        "a finite difference of positions differ by the median mismatch above; this "
        "bulletin makes no claim about which of the two is correct.",
        "",
        "## Partitions",
        "",
        "What it measures: four structural splits that run through the matches of "
        "one bundle without a single field of either bundle declaring them. None of "
        "the four is documented; each is read off an artefact this pipeline already "
        "built.",
        "",
        f"Football tracking layout: {summary['football_extra_footage_matches']} of "
        f"{summary['football_matches']} matches carry footage outside their periods "
        "well beyond a normal kickoff pause. Basketball frame loss: "
        f"{summary['basketball_high_frame_loss_matches']} of "
        f"{summary['basketball_matches']} matches drop native frames at a rate an "
        "order of magnitude above the rest. Football `players[]` shape and event-"
        f"coordinate precision: {summary['football_players_last_modified_matches']} of "
        f"{summary['football_matches']} matches on the modified side of each path, "
        f"and the two paths agree on all {summary['football_partitions_agree_matches']} "
        "of them.",
        "",
        "For a consumer: code that assumes one shape across a whole bundle will "
        "silently mishandle whichever partition it did not see first; branch on the "
        "measured split above, not on a hand-picked list of match ids.",
        "",
        "## The hook shot",
        "",
        f"`/quality` replays one basketball shot (`{hook['match_id']}`, native frame "
        f"`{hook['start_frame']}`) chosen by rule: of every accepted calibration "
        "flight, the one whose fitted g sits closest to the calibration's own median. "
        f"Its g is {hook['g_data']:.2f} m/s² against a calibration median of "
        f"{hook['median_calibration_g']:.2f} m/s²; the page falls a second ball from "
        "the same position and velocity the data's own fit has at that instant, but "
        f"at {hook['g_real']} m/s², the standard value, so the two are visibly not "
        "the same flight.",
        "",
        "## On the body pose bundle's own z axis",
        "",
        "Body pose is not part of this bulletin (P6 in the project plan), and its z "
        "is a different quantity from the one measured above (a joint's position "
        "relative to the player's own centroid, not a ball or player position on "
        "tracking). Its dataset card documents that axis as a known weak point in "
        "that other product; cited here as honest context, not as support for this "
        "bulletin's own gravity bias:",
        "",
        f"> {SKILLCORNER_BODYPOSE_Z_CAVEAT}",
        "",
        f"Source: [`SkillCorner/opendata-bodypose`]({SKILLCORNER_BODYPOSE_URL}) dataset "
        f"card, consulted {SKILLCORNER_BODYPOSE_CHECKED_ON}.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_bulletin(docs_dir: Path, summary: dict[str, Any], hook: dict[str, Any]) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = bulletin_path(docs_dir)
    path.write_text(render_bulletin(summary, hook), encoding="utf-8", newline="\n")
    return path


def run_publish_quality(data_dir: Path, reports_dir: Path, out_dir: Path, docs_dir: Path) -> int:
    missing = [c for c in sorted(CHECKS) if not report_path(reports_dir, c).is_file()]
    if missing:
        print(
            f"publish quality: missing report(s) {missing} under {reports_dir}; "
            "run `tracklab quality` first"
        )
        return 1

    checks = quality_rows(reports_dir)
    summary = build_summary(reports_dir)
    hook = build_hook(data_dir)
    payload = {"schema_version": 1, "checks": checks, "summary": summary, "hook": hook}

    out_dir.mkdir(parents=True, exist_ok=True)
    path = quality_path(out_dir)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    bulletin = write_bulletin(docs_dir, summary, hook)

    n_rows = sum(len(v) for v in checks.values())
    print(f"publish quality: {n_rows} rows across {len(checks)} checks, {path}")
    print(f"publish quality: {path} ({path.stat().st_size} bytes)")
    print(f"publish quality: {bulletin}")
    return 0
