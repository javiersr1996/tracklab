"""The P5 protocol as code (task 47).

`tracklab runs protocol` writes `reports/runs_protocol.json` before any outcome is computed:
the split rule and its two lists, the cause instant, the windows, the placebo rule, the
instrument and the effect, the null, the bar, the testability threshold, the held-out bar
and the death criteria M1 to M5b of tasks/todo.md (P5). `--check` regenerates it in memory
and compares the bytes, so a threshold moved by hand after looking shows as a diff (D13 of
the sister repo: a preregistered threshold that fails is reported, never moved). On a file
in stage `frozen` (task 50) `--check` verifies instead what the freeze must keep: the design
and its fingerprint, the evidence, the seal and the history; what the freeze adds (the
candidates, a sha of the code tree) is task 50's to check. Write mode never overwrites a
frozen file.

The status line says how much of the warehouse backed the check: `FULL 20/20` when every
match was at hand and the counts recomputed, `PARTIAL n/20` when the rows travelled in the
file and the counts were taken as written (the CI fixtures hold one match). A PARTIAL pass
is a pass on the file's consistency, never on the data.

Three sections:

* `design`: every rule, from the constants below; its sha256 is `fingerprint`, which task 50
  records when it freezes and task 51's `--check` compares against.
* `design.split`: the only part computed from data. The football matches of `silver/dim_match`
  with their `event_coords_exact` flag from `reports/quality_partitions.csv`, ordered by
  kickoff inside each flag group, alternating and starting with calibration (decision 3,
  split A). The 20 rows travel in the JSON so CI, whose fixtures hold one match, can
  regenerate the split from a committed artefact.
* `evidence`: coverage counts and never an outcome. Today, the placebo candidates per rule on
  the calibration half (`placebo.py`), which decided whether teammates' runs exclude a placebo.

Every path defaults to `tracklab.paths.data_root()` through the CLI; nothing here reads the
held-out half beyond ids, kickoffs and flags.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb

from tracklab.runs import placebo

PROTOCOL_NAME = "runs_protocol.json"
SCHEMA_VERSION = 1
WRITTEN = "2026-10-09"
REVISED = "2026-10-11"  # the review of task 49: history gains its entry, the stage stays design
STAGE_DESIGN = "design"
STAGE_FROZEN = "frozen"


def z_two_sided(p: float) -> float:
    """The |z| whose two-sided normal tail is `p`, by bisection on `math.erf`: the z the bar's
    p is equivalent to, and the normal approximation of the sign-flip null the power uses."""
    lo, hi = 0.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 2.0 * (1.0 - 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0)))) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


SEED = 20261009
N_PERMUTATIONS = 2000
SAMPLE_RATE_HZ = placebo.SAMPLE_RATE_HZ
EFFECT_WINDOW_S = 2.0
VELOCITY_WINDOW_S = 0.5
PRE_TREND_WINDOW_S = 2.0
COVERAGE_BEFORE_START_S = 1.0
COVERAGE_AFTER_END_S = 3.0
MIN_RUN_LENGTH_M = 1.0
BAR_SAME_SIGN_MATCHES = 8
BAR_OF_MATCHES = 10
BAR_P = 0.00135
BAR_Z = z_two_sided(BAR_P)  # derived, never a second literal: 3.205 for a two-sided 0.00135
TESTABILITY_MDE80_SD = 0.3
HELD_OUT_P = 0.01
NULL_AT_LEAST_ONE_MAX_PCT = 5.0
# The installed numpy, which `uv sync --locked` pins to pyproject.toml (a test ties the two).
NUMPY_VERSION = importlib.metadata.version("numpy")

# Decision 2 left one choice to this task: whether a teammate's run near the placebo instant
# excludes it. Decided with the counts in `evidence` (coverage, never an outcome): excluded.
PLACEBO_EXCLUDES_TEAMMATES_RUNS = True


@dataclass(frozen=True)
class MatchRow:
    """One football match as the split sees it: id, kickoff and the two partition flags."""

    match_id: int
    kickoff_utc: str
    event_coords_exact: bool
    layout_extra_footage: bool


class ProtocolInputError(RuntimeError):
    """The warehouse or the reports cannot give the split its 20 rows."""


# --- inputs ---------------------------------------------------------------------------


def partition_flags(reports_dir: Path) -> dict[int, dict[str, bool]]:
    """`event_coords_exact` and `layout_extra_footage` per football match, from
    `quality_partitions.csv` (task 29)."""
    path = reports_dir / "quality_partitions.csv"
    flags: dict[int, dict[str, bool]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["sport"] != "football" or row["metric"] not in (
                "event_coords_exact",
                "layout_extra_footage",
            ):
                continue
            match_id = int(row["match_id"].removeprefix("fb:"))
            flags.setdefault(match_id, {})[row["metric"]] = float(row["value"]) == 1.0
    incomplete = sorted(m for m, f in flags.items() if len(f) != 2)
    if incomplete:
        raise ProtocolInputError(f"{path}: matches missing one of the two flags: {incomplete}")
    return flags


def warehouse_kickoffs(data_dir: Path) -> dict[int, str]:
    """Kickoff (UTC, ISO) per football match of `silver/dim_match`; empty when silver is not
    built, which `--check` reports instead of failing."""
    glob = (data_dir / "silver" / "dim_match" / "**" / "*.parquet").as_posix()
    if not (data_dir / "silver" / "dim_match").is_dir():
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT native_match_id, strftime(kickoff_utc, '%Y-%m-%dT%H:%M:%SZ') "
            "FROM read_parquet($glob) WHERE sport = 'football' ORDER BY 1",
            {"glob": glob},
        ).fetchall()
    finally:
        con.close()
    return {int(match_id): str(kickoff) for match_id, kickoff in rows}


def match_rows(kickoffs: dict[int, str], flags: dict[int, dict[str, bool]]) -> list[MatchRow]:
    """The 20 rows: every match of `quality_partitions.csv` with its kickoff from the warehouse.
    A match the warehouse lacks is an error: the split needs all of them."""
    missing = sorted(set(flags) - set(kickoffs))
    if missing:
        raise ProtocolInputError(
            f"dim_match holds {len(set(flags) & set(kickoffs))} of the {len(flags)} football "
            f"matches of quality_partitions.csv; missing {missing}"
        )
    return [
        MatchRow(
            match_id=m,
            kickoff_utc=kickoffs[m],
            event_coords_exact=f["event_coords_exact"],
            layout_extra_footage=f["layout_extra_footage"],
        )
        for m, f in sorted(flags.items())
    ]


# --- the split (decision 3, A) -----------------------------------------------------------


def split_matches(rows: list[MatchRow]) -> tuple[list[int], list[int]]:
    """Inside each `event_coords_exact` group, by kickoff (then id), alternating and starting
    with calibration. Returns (calibration, held_out), each sorted by match id."""
    calibration: list[int] = []
    held_out: list[int] = []
    for exact in (True, False):
        group = sorted(
            (r for r in rows if r.event_coords_exact is exact),
            key=lambda r: (r.kickoff_utc, r.match_id),
        )
        for i, row in enumerate(group):
            (calibration if i % 2 == 0 else held_out).append(row.match_id)
    return sorted(calibration), sorted(held_out)


# --- the design ---------------------------------------------------------------------------


def design(rows: list[MatchRow]) -> dict[str, Any]:
    calibration, held_out = split_matches(rows)
    exclusion = (
        "no run of the runner's team overlapping [t' - 3 s, t' + 3 s], teammates included"
        if PLACEBO_EXCLUDES_TEAMMATES_RUNS
        else "no run of the runner himself overlapping [t' - 3 s, t' + 3 s]"
    )
    return {
        "question": (
            "Which off-ball run subtypes displace the defence, measured on the tracking in the "
            "window after the run starts, against a placebo of the same runner at another "
            "instant of a possession of his team."
        ),
        "outcome": {
            "is": "displacement of the defence in the tracking (decision 1)",
            "never": [
                "EPV (absent from the runs; the possession that carries it is shared)",
                "lead_to_shot",
                "lead_to_goal",
                "dangerous",
                "targeted",
                "received",
                "xthreat",
                "any other provider label or measure",
            ],
            "provider_measures_are_for": (
                "contrasting the instrument only: last_defensive_line_height_start in task 49"
            ),
        },
        "split": {
            "rule": (
                "inside each group of event_coords_exact, by kickoff_utc then match_id, "
                "alternating and starting with calibration (decision 3, split A)"
            ),
            "sources": ["silver/dim_match", "reports/quality_partitions.csv"],
            "matches": [asdict(r) for r in rows],
            "calibration": calibration,
            "held_out": held_out,
        },
        "cause": {
            "instant": (
                "t_c = frame_start of the off_ball_run event, the provider's frame, which is "
                "frame_native of silver frames"
            ),
            "rule": (
                "every cause is measured at t_c or before it; the effect, after it, as the "
                "residual of what the defence's velocity at t_c already predicted"
            ),
        },
        "windows": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "effect_s": [0.0, EFFECT_WINDOW_S],
            "velocity_s": VELOCITY_WINDOW_S,
            "pre_trend_s": [-PRE_TREND_WINDOW_S, 0.0],
            "coverage_s": {
                "before_frame_start": COVERAGE_BEFORE_START_S,
                "after_frame_end": COVERAGE_AFTER_END_S,
                "clipped_to": "the period",
            },
            "effect_window_rule": (
                f"{EFFECT_WINDOW_S} s is a hypothesis until task 49 measures the cadence of the "
                "football tracking; 49 may replace it only by the minimum window that cadence "
                "admits, once, before any per-subtype effect, and writes the change in history"
            ),
            "velocity_window_rule": (
                f"{VELOCITY_WINDOW_S} s has no measured source: a hypothesis, like W, until "
                "task 49 measures the cadence; 49 may replace it once, before any per-subtype "
                "effect, and writes the change in history"
            ),
        },
        "frames": {
            "coordinates": (
                "silver frames (x_m, y_m: the venue frame, metres), every player row of the "
                "match, turned to the attack frame of the runner's team with "
                "dim_team_period.attack_sign of (the period the frame belongs to, runner's "
                "team): x_att = attack_sign * x_m and y_att = attack_sign * y_m, so the "
                "runner's team attacks towards +x in every frame of a window whichever team "
                "has the ball, and a placebo taken in the other half of the match is turned by "
                "the sign of its own period, never by the run's; never the frames_attacking "
                "view, which turns by the team in possession and drops the frames no "
                "possession claims"
            ),
            "runner": "entity fb:<player_id> of dim_entity, the player_id of the event",
            "opponents": "entities of kind player of the other team of the match",
            "goalkeeper": "bronze match_players.player_role_name = 'Goalkeeper'",
            "detection": (
                "is_detected per frame; extrapolated positions are used as the provider gives "
                "them and flagged, and task 50 (M4) repeats every effect with the marker "
                "detected in the whole window"
            ),
        },
        "instrument": {
            "run_direction": (
                "d = unit vector from the runner's tracked position at frame_start to his "
                f"position at frame_end; runs shorter than {MIN_RUN_LENGTH_M} m are excluded"
            ),
            "min_run_length_rule": (
                f"{MIN_RUN_LENGTH_M} m has no measured source: a hypothesis until task 49 "
                "reports the tracked lengths of the runs against it; 49 may replace it once, "
                "before any per-subtype effect, and writes the change in history"
            ),
            "marker": "the opponent nearest to the runner at t_c, goalkeeper included",
            "marker_displacement_m": (
                "projection on d of [p(t_c + W) - p(t_c)] - v(t_c) * W, with "
                "v(t_c) = [p(t_c) - p(t_c - V)] / V, W the effect window and V the velocity "
                "window; positive means the marker moved with the run"
            ),
            "line_height_m": (
                "L(t) = mean x_att of the two deepest outfield opponents (largest x_att, "
                "goalkeepers excluded); residual [L(t_c + W) - L(t_c)] - v_L(t_c) * W with "
                "v_L(t_c) = [L(t_c) - L(t_c - V)] / V; positive means the line dropped "
                "towards its own goal"
            ),
            "forced_direction_check": (
                "task 49, every run together: the marker displacement beats the placebo in the "
                "run's direction, per match and pooled, against the bar; the line height "
                "against the provider's last_defensive_line_height_start, correlation and "
                "median difference per match"
            ),
            "standardisation": (
                "each quantity divided by the sd of its placebo values pooled over the "
                "calibration half, fixed in task 49 and never recomputed"
            ),
        },
        "placebo": {
            "candidate": (
                "a player_possession of a teammate (never the runner), in another team phase "
                "(phase_index), with the run's team_in_possession_phase_type"
            ),
            "instant": (
                "t' = candidate.frame_start + (run.frame_start - "
                "run.associated_player_possession_frame_start), inside the candidate's phase "
                "window of phases_of_play so the team still has the ball"
            ),
            "exclusion": exclusion,
            "exclusion_s": placebo.EXCLUSION_S,
            "choice": (
                "among the admissible candidates, the instant nearest in time to t_c; ties go "
                "to the earlier one"
            ),
            "direction": "the placebo inherits d of its run, in the attack frame of the team",
            "windows": (
                "the same W and V around t' as around t_c; each leg, from t - V to t + W, lies "
                "inside the period of its own instant"
            ),
            "teammates_runs": {
                "excluded": PLACEBO_EXCLUDES_TEAMMATES_RUNS,
                "alternative": "exclude the runner's own runs only",
                "why": (
                    "the placebo stands for the defence with nobody running; a teammate's run "
                    "inside its window would put a run in the placebo (a trap the review list "
                    "names); the price is the coverage in evidence.placebo_counts_calibration, "
                    "team_overlap against runner_overlap"
                ),
            },
        },
        "effect": {
            "pair": "quantity(run) - quantity(placebo), one pair per run",
            "per_match": (
                "mean of the pairs of the subtype in the match: one row per match, ten per half, "
                "always before any aggregate"
            ),
            "pooled": (
                "mean of every pair of the subtype in the half, matches weighted by their pairs"
            ),
            "unit_of_independence": (
                "the unit: the connected component, inside the match, of the pairs that share "
                "associated_player_possession_event_id or a placebo instant (same runner, same "
                "t', so the same placebo quantity); the pairs of a unit move together in the "
                "null (task 49: the possession alone left the shared instants apart)"
            ),
            "pre_trend": (
                "the same statistic with t_c replaced by t_c - W, which must stay flat (task 50, "
                "M3)"
            ),
            "grouping": (
                "by provider subtype, and again by a class computed only with information up "
                "to t_c (task 50): the label groups, it does not cause"
            ),
            "analysis_set": (
                "clean runs (task 48: complete window, runner detected throughout) with an "
                "admissible placebo and a direction of at least the minimum length"
            ),
        },
        "null": {
            "kind": "permutation inside each match, never across matches",
            "how": (
                "sign flip of the paired differences per unit (effect.unit_of_independence) "
                "inside each match; to compare subtypes, subtype labels shuffled inside each "
                "match"
            ),
            "n_permutations": N_PERMUTATIONS,
            "seed": SEED,
            "p_value": (
                "two-sided, (1 + count of |stat*| >= |stat|) / (1 + n_permutations), on the "
                "pooled statistic"
            ),
            "real_null_check": (
                "task 49: placebo 1 minus placebo 2 per pair, the second placebo being the next "
                "nearest admissible instant of the same rule whose window is disjoint from the "
                "first's, centred per subtype over the calibration half (placebo quantities, "
                "never an outcome); sign-flipped by blocks that nest the units, the connected "
                "components of possession, placebo instants and (runner, period) inside the "
                "match; on every draw the whole bar with its units and its permutation p; how "
                "often it fires per subtype and for at least one subtype, against bar.hardening"
            ),
        },
        "bar": {
            "calibration": {
                "same_sign_matches_at_least": BAR_SAME_SIGN_MATCHES,
                "of_matches": BAR_OF_MATCHES,
                "p_at_most": BAR_P,
                "z_equivalent": round(BAR_Z, 4),
            },
            "testability": {
                "mde80_sd_at_most": TESTABILITY_MDE80_SD,
                "in": (
                    "both halves, with the design effect measured in task 49 and the bar "
                    "simulated as it is applied: the sign count over the matches and a "
                    "permutation count drawn as Binomial(n_permutations, two-sided normal tail "
                    "of the z of the draw), passing when (1 + count) / (1 + n_permutations) is "
                    "at most p_at_most; a subtype that fails is said untestable with this "
                    "sample, never noise"
                ),
            },
            "held_out": {
                "same_sign_matches_at_least": BAR_SAME_SIGN_MATCHES,
                "of_matches": BAR_OF_MATCHES,
                "p_at_most": HELD_OUT_P,
                "multiplicity": "Holm over the candidates frozen in task 50",
            },
            "hardening": (
                f"if the real null fires 'at least one subtype' above {NULL_AT_LEAST_ONE_MAX_PCT} "
                "%, the bar hardens once, in task 49, with the figure written in history; it "
                "never loosens (D13)"
            ),
        },
        "death_criteria": {
            "M1": (
                "task 49: fewer than 2 probable subtypes (testability) -> P5 dies: the sample "
                "does not pay for the question"
            ),
            "M2": (
                "task 49: the instrument does not pass the bar in calibration -> P5 dies: the "
                "instrument does not see even what is forced, and the null of a deaf "
                "instrument says nothing about the runs"
            ),
            "M3": (
                "task 50: the pre-trend reaches 50 % of the effect, or the class at t_c gives "
                "the opposite sign to the subtype -> that subtype leaves (reaction or "
                "circularity)"
            ),
            "M4": (
                "task 50: with the marker detected in the whole window the effect changes sign "
                "or falls below half -> that subtype leaves (extrapolation)"
            ),
            "M5a": (
                "task 50: zero candidates -> P5 dies, the held-out half is never opened, and "
                "the page says so"
            ),
            "M5b": (
                "task 51: no candidate replicates in the held-out half -> the negative is "
                "published, with the two halves side by side"
            ),
            "if_dead": (
                "published dead, same route and title, with the probe's per-match figures, the "
                "funnel, the power, the null, the protocol with the sha of every stage and what "
                "was never opened (decision 7)"
            ),
        },
        "scope": {
            "sport": "football",
            "matches": len(rows),
            "player_rankings": False,
            "intent_claims": False,
            "page_says": (
                "how many metres the defence moved against the placebo, never that a player "
                "drags or fools anyone"
            ),
        },
        "dependencies": {"numpy": NUMPY_VERSION},
    }


def fingerprint(design_payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        design_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    """The payload with `content_sha256` over everything else, last. Task 50 reseals the file
    it freezes with this; the guard (`data.committed_protocol`) verifies it with `sealed`."""
    body = {k: v for k, v in payload.items() if k != "content_sha256"}
    return {**body, "content_sha256": fingerprint(body)}


def sealed(payload: dict[str, Any]) -> bool:
    body = {k: v for k, v in payload.items() if k != "content_sha256"}
    return payload.get("content_sha256") == fingerprint(body)


def build_protocol(rows: list[MatchRow], counts: list[placebo.PlaceboCount]) -> dict[str, Any]:
    design_payload = design(rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE_DESIGN,
        "written": WRITTEN,
        "plan": "tasks/todo.md, P5 'The run that moves nobody', task 47",
        "fingerprint": fingerprint(design_payload),
        "design": design_payload,
        "evidence": {
            "placebo_counts_calibration": {
                "what": (
                    "runs of the calibration half with at least one admissible placebo under "
                    "each rule, from dynamic_events and phases_of_play only; a coverage count, "
                    "never an outcome; task 48 bounds it with the tracking"
                ),
                "columns": list(placebo.COLUMNS),
                "per_match": placebo.as_rows(counts),
                "total": placebo.total(counts),
            }
        },
        "history": [
            {"stage": STAGE_DESIGN, "task": 47, "date": WRITTEN},
            {
                "stage": STAGE_DESIGN,
                "task": 49,
                "date": REVISED,
                "note": (
                    "review of task 49, before any effect per subtype: the unit of the null is "
                    "the connected component of shared possession or shared placebo instant, "
                    "not the possession alone; the real-null check is placebo 1 minus placebo "
                    "2 sign-flipped by blocks that nest the units; the power simulates the "
                    "bar's permutation count instead of a normal quantile; z_equivalent is "
                    "derived from p_at_most (3.205 two-sided, where 3.0 was written). No "
                    "threshold, window, seed or list moved."
                ),
            },
        ],
    }
    # Over everything above: a hand edit of the evidence shows even where `--check` cannot
    # recount it (the CI fixtures hold one match).
    return seal(payload)


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def protocol_path(reports_dir: Path) -> Path:
    return reports_dir / PROTOCOL_NAME


def read_protocol(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def rows_from_protocol(payload: dict[str, Any]) -> list[MatchRow]:
    return [MatchRow(**r) for r in payload["design"]["split"]["matches"]]


# --- the command --------------------------------------------------------------------------


def run_runs_protocol(data_dir: Path, reports_dir: Path, *, check: bool = False) -> int:
    path = protocol_path(reports_dir)
    flags = partition_flags(reports_dir)
    kickoffs = warehouse_kickoffs(data_dir)
    complete = set(flags) <= set(kickoffs)

    if not check:
        if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("stage") == (
            STAGE_FROZEN
        ):
            print(f"runs protocol: {path} is frozen and is not rewritten (D13); use --check")
            return 1
        try:
            rows = match_rows(kickoffs, flags)
        except ProtocolInputError as exc:
            print(f"runs protocol: {exc}")
            return 1
        counts = placebo.placebo_counts(data_dir, split_matches(rows)[0])
        payload = build_protocol(rows, counts)
        if len(counts) != len(payload["design"]["split"]["calibration"]):
            print(
                f"runs protocol: dynamic_events for {len(counts)} of the "
                f"{len(payload['design']['split']['calibration'])} calibration matches"
            )
            return 1
        reports_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(render(payload), encoding="utf-8", newline="\n")
        print(_summary(payload, status=f"FULL {len(rows)}/{len(rows)}"))
        print(f"runs protocol: {path} ({path.stat().st_size} bytes)")
        return 0

    if not path.is_file():
        print(f"runs protocol --check: {path} missing")
        return 1
    current_text = path.read_text(encoding="utf-8")
    current = json.loads(current_text)
    stage = current.get("stage")
    if stage not in (STAGE_DESIGN, STAGE_FROZEN):
        print(f"runs protocol --check: unknown stage {stage!r}")
        return 1
    if complete:
        rows = match_rows(kickoffs, flags)
        counts = placebo.placebo_counts(data_dir, split_matches(rows)[0])
        status = f"FULL {len(rows)}/{len(rows)}"
    else:
        # The warehouse at hand holds fewer matches than the split (CI fixtures): the rows
        # travel in the file, what is at hand is compared, and the counts are kept as written.
        rows = rows_from_protocol(current)
        problems = _rows_against(rows, kickoffs, flags)
        if problems:
            print("runs protocol --check: " + "; ".join(problems))
            return 1
        counts = [
            placebo.PlaceboCount(**r)
            for r in current["evidence"]["placebo_counts_calibration"]["per_match"]
        ]
        at_hand = len(set(kickoffs) & {r.match_id for r in rows})
        status = f"PARTIAL {at_hand}/{len(rows)}"
    expected = build_protocol(rows, counts)
    print(_summary(expected, status=status))
    if stage == STAGE_DESIGN:
        problems = [] if render(expected) == current_text else ["differs from what the code writes"]
    else:
        problems = frozen_problems(current, expected)
    if problems:
        print(f"runs protocol --check: {path} " + "; ".join(problems))
        return 1
    print(f"runs protocol --check: {path} matches ({status}, stage {stage})")
    return 0


FROZEN_KEEPS = ("schema_version", "written", "plan", "fingerprint", "design", "evidence")


def frozen_problems(current: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """What a frozen file must keep from the design the code writes, and what the freeze must
    leave verifiable: the seal, the design entries opening the history and a frozen one after
    them. What task 50 adds on top (its candidates, a sha of the code tree) is checked there."""
    problems: list[str] = []
    if not sealed(current):
        problems.append("content_sha256 does not cover the file")
    for key in FROZEN_KEEPS:
        if current.get(key) != expected[key]:
            problems.append(f"{key} differs from what the code writes")
    history = current.get("history") or []
    opening = expected["history"]
    if history[: len(opening)] != opening:
        problems.append("history does not open with the design entries")
    if not any(h.get("stage") == STAGE_FROZEN for h in history[len(opening) :]):
        problems.append("history has no frozen entry")
    return problems


def _rows_against(
    rows: list[MatchRow], kickoffs: dict[int, str], flags: dict[int, dict[str, bool]]
) -> list[str]:
    """What the committed rows say against the warehouse rows at hand and every flag."""
    problems: list[str] = []
    if sorted(r.match_id for r in rows) != sorted(flags):
        problems.append("the committed matches are not those of quality_partitions.csv")
    for row in rows:
        f = flags.get(row.match_id)
        if f is not None and (
            f["event_coords_exact"] != row.event_coords_exact
            or f["layout_extra_footage"] != row.layout_extra_footage
        ):
            problems.append(f"flags of {row.match_id} differ from quality_partitions.csv")
        kickoff = kickoffs.get(row.match_id)
        if kickoff is not None and kickoff != row.kickoff_utc:
            problems.append(f"kickoff of {row.match_id} differs from dim_match")
    return problems


def _summary(payload: dict[str, Any], *, status: str) -> str:
    """`status` is `FULL n/n` (every match at hand, counts recomputed) or `PARTIAL k/n`
    (rows from the file, counts as written)."""
    split = payload["design"]["split"]
    counts = payload["evidence"]["placebo_counts_calibration"]["total"]
    rule = "team_overlap" if PLACEBO_EXCLUDES_TEAMMATES_RUNS else "runner_overlap"
    return (
        f"runs protocol: warehouse={status} matches={len(split['matches'])} "
        f"calibration={len(split['calibration'])} held_out={len(split['held_out'])} "
        f"placebo_rule={rule} placebo_runs={counts[rule]}/{counts['runs']} "
        f"(counts {'recomputed' if status.startswith('FULL') else 'as written'}) "
        f"fingerprint={payload['fingerprint'][:12]}"
    )
