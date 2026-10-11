"""`tracklab runs effect`: death probe 2 of P5, on the calibration half alone (task 50), and
`tracklab runs freeze`, which it prepares.

Writes the `effect` section of `reports/runs_calibration.json`, next to the probe's (task 49)
and never over it: the file is resealed over both, and `runs probe` keeps this section when it
rewrites its own. For the probable subtypes the probe found on the protocol's primary
quantity, and for no other:

* the effect: the marker displacement along the run, run minus placebo, per match (ten rows)
  and pooled, against the protocol's bar (same sign in at least 8 of 10 matches and the
  sign-flip permutation p over the units at most p_at_most); the line height alongside, as
  the secondary quantity, with its testability label, deciding nothing;
* the pre-trend: the same statistic with t_c replaced by t_c - W on both legs (M3: a defence
  already moving before the run is a reaction, not an effect);
* the effect with the marker detected in the whole window of both legs (M4: an effect that
  lives in extrapolated positions is extrapolation);
* the circularity control: a class of the run computed with information up to t_c alone
  (`windows.run_class`: the runner's direction against the ball, the line and the flank), its
  agreement with the subtype, and the effect by class (M3: the subtype's class must give the
  effect's sign; the provider's label reads the end of the run, which the defence's movement
  shapes);
* a control the review of task 49 left to this task: the permutation p with the units
  coarsened to link run legs that overlap in time (same team), the dependence no
  placebo-against-placebo check can see; reported, never deciding, the protocol's unit is
  fixed.

The verdict follows the criteria as the plan and the protocol wrote them before any effect
was looked at: a candidate passes the bar and survives M3 and M4; zero candidates is M5a and
P5 dies without the held-out half ever opening. `consistency_problems` recomputes every flag
from the figures as written, so a verdict edited by hand shows even on fixtures.

Every tracking is a `windows.MatchTracking` (guard as it is built); the ids are
`data.load_half("calibration")`. Write mode refuses while the code under `runs/` or the
protocol has uncommitted changes and records `head` and `code_tree_sha`. `--check`
regenerates the section where the warehouse holds the calibration matches (`FULL ...
recomputed and equal`), otherwise verifies the seal, the protocol and probe it answers to and
the verdict against the figures as written (`PARTIAL ... 0/10 recomputed`).

`runs freeze` turns the committed protocol to stage `frozen` with the candidates of this
section and the sha of the committed `runs/` tree (`protocol.freeze_payload`); it writes the
file and nothing else: the commit is the freeze, and Javier approves it first.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from tracklab.runs import placebo
from tracklab.runs.coverage import has_frames
from tracklab.runs.data import (
    Half,
    code_tree_sha,
    committed_protocol,
    dirty_code_paths,
    head_commit,
    load_half,
)
from tracklab.runs.probe import (
    PROBE_NAME,
    bar_verdict,
    protocol_problems,
    protocol_record,
)
from tracklab.runs.probe import (
    consistency_problems as probe_problems,
)
from tracklab.runs.protocol import (
    BAR_OF_MATCHES,
    BAR_P,
    BAR_SAME_SIGN_MATCHES,
    EFFECT_WINDOW_S,
    PRIMARY_QUANTITY,
    SECONDARY_QUANTITY,
    SEED,
    STAGE_DESIGN,
    SUBTYPES,
    TESTABILITY_MDE80_SD,
    freeze_payload,
    protocol_path,
    read_protocol,
    render,
    seal,
    sealed,
)
from tracklab.runs.windows import (
    EFFECT_FRAMES,
    PLACEBO_RULE,
    RUN_CLASSES,
    VELOCITY_FRAMES,
    MatchTracking,
    PairEffect,
    components,
    leg_marker_detected,
    load_runs,
    load_tracking,
    pair_effects,
    pair_unit_key,
    quantities,
    run_class,
    run_direction,
    unit_labels,
)

TASK = 50
WRITTEN = "2026-10-11"
HALF: Half = "calibration"
# M3: the pre-trend reaches this share of the effect -> the subtype leaves (the plan's 50 %).
M3_PRE_TREND_SHARE = 0.5
# M4: with the marker detected throughout, the effect falls below this share of the effect
# with every pair (a sign change is below it too) -> the subtype leaves (the plan's half).
M4_DETECTED_SHARE = 0.5
NOT_TESTABLE_ON_LINE = "not testable on the line with this sample"
TESTABLE_ON_LINE = "testable on the line"
# Seed streams, children of the protocol's seed, after the probe's 0 to 4: one per use, and
# each verdict draws from a child keyed by what it tests, so the order of the loops moves
# nothing.
STREAM_EFFECT, STREAM_CLASSES, STREAM_OVERLAP = 5, 6, 7

Array = NDArray[np.float64]


class EffectInputError(RuntimeError):
    """The calibration file at hand has no probe section the effect can answer to, or the
    warehouse cannot give it the ten calibration matches."""


# --- per-match loading: values, behind the guard ----------------------------------------


@dataclass(frozen=True)
class MatchEffects:
    """What the effect holds of one calibration match while it runs: the pairs, and per pair
    the pre-trend pair (NaN when either leg has no quantities at t - W), whether the marker
    of both legs is detected throughout, the class at t_c (None when unclassified) and the
    run's team, for the run-leg overlap control. Real-data instances are never printed or
    stored whole."""

    match_id: int
    pairs: tuple[PairEffect, ...]
    pre_trend_marker_m: Array
    marker_detected: NDArray[np.bool_]
    run_class: tuple[str | None, ...]
    team_id: NDArray[np.int64]


def effect_match(t: MatchTracking, data_dir: Path) -> MatchEffects:
    """Everything the effect needs of one match, from a tracking that passed the guard."""
    runs = load_runs(data_dir, t.match_id)
    instants = placebo.placebo_instants(data_dir, [t.match_id], PLACEBO_RULE)
    pairs = tuple(pair_effects(t, runs, instants))
    by_id = {r.event_id: r for r in runs}
    pre: list[float] = []
    detected: list[bool] = []
    classes: list[str | None] = []
    teams: list[int] = []
    for pair in pairs:
        run = by_id[pair.run_id]
        direction = run_direction(t, run)
        assert direction is not None  # the pair exists, so the run has a direction
        own = quantities(t, run, run.period, pair.t_c - EFFECT_FRAMES, direction)
        other = quantities(
            t, run, pair.placebo_period, pair.placebo_instant - EFFECT_FRAMES, direction
        )
        pre.append(math.nan if own is None or other is None else own[0] - other[0])
        detected.append(
            bool(leg_marker_detected(t, run, run.period, pair.t_c))
            and bool(leg_marker_detected(t, run, pair.placebo_period, pair.placebo_instant))
        )
        classes.append(run_class(t, run))
        teams.append(run.team_id)
    return MatchEffects(
        match_id=t.match_id,
        pairs=pairs,
        pre_trend_marker_m=np.array(pre, dtype=np.float64),
        marker_detected=np.array(detected, dtype=np.bool_),
        run_class=tuple(classes),
        team_id=np.array(teams, dtype=np.int64),
    )


# --- the half as arrays -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Collected:
    """Every pair of the half as parallel arrays: the protocol's units and the run-leg
    overlap units labelled per match and offset so they never cross a match; the class as an
    index in `RUN_CLASSES` (-1 unclassified)."""

    match_of_pair: NDArray[np.intp]
    subtype_of_pair: NDArray[np.intp]
    units: NDArray[np.intp]
    overlap_units: NDArray[np.intp]
    class_of_pair: NDArray[np.intp]
    marker_m: Array
    line_m: Array
    pre_trend_m: Array
    detected: NDArray[np.bool_]


def run_leg_overlap_keys(
    pair: PairEffect, team_id: int, velocity_frames: int, effect_frames: int
) -> tuple[Hashable, ...]:
    """The keys of the run-leg overlap control: the protocol's unit keys (possession, placebo
    instant) plus one key per frame of the run's leg [t_c - V, t_c + W] with the team, so two
    runs of a team whose legs overlap in time fall in one unit (the same defenders, the same
    seconds); `components` links them."""
    keys: tuple[Hashable, ...] = (("i", (pair.player_id, pair.placebo_instant)),)
    if pair.possession_id is not None:
        keys += (("p", pair.possession_id),)
    keys += tuple(
        ("f", team_id, f) for f in range(pair.t_c - velocity_frames, pair.t_c + effect_frames + 1)
    )
    return keys


def _collect(matches: Sequence[MatchEffects]) -> _Collected:
    match_of, subtype_of, units, overlap, classes = [], [], [], [], []
    unit_offset = overlap_offset = 0
    for m, me in enumerate(matches):
        labels = unit_labels([pair_unit_key(p) for p in me.pairs])
        coarse = components(
            [
                run_leg_overlap_keys(p, int(me.team_id[i]), VELOCITY_FRAMES, EFFECT_FRAMES)
                for i, p in enumerate(me.pairs)
            ]
        )
        for pair, label, block, cls in zip(me.pairs, labels, coarse, me.run_class, strict=True):
            match_of.append(m)
            subtype_of.append(SUBTYPES.index(pair.subtype))
            units.append(unit_offset + label)
            overlap.append(overlap_offset + block)
            classes.append(RUN_CLASSES.index(cls) if cls is not None else -1)
        unit_offset += len(set(labels))
        overlap_offset += len(set(coarse))
    pairs = [p for me in matches for p in me.pairs]
    return _Collected(
        match_of_pair=np.array(match_of, dtype=np.intp),
        subtype_of_pair=np.array(subtype_of, dtype=np.intp),
        units=np.array(units, dtype=np.intp),
        overlap_units=np.array(overlap, dtype=np.intp),
        class_of_pair=np.array(classes, dtype=np.intp),
        marker_m=np.array([p.marker_m for p in pairs], dtype=np.float64),
        line_m=np.array([p.line_m for p in pairs], dtype=np.float64),
        pre_trend_m=np.concatenate([me.pre_trend_marker_m for me in matches])
        if matches
        else np.zeros(0),
        detected=np.concatenate([me.marker_detected for me in matches])
        if matches
        else np.zeros(0, dtype=np.bool_),
    )


# --- the arithmetic of one table --------------------------------------------------------------


def _round(value: float, digits: int) -> float | None:
    return None if not math.isfinite(value) else round(float(value), digits)


def _compact(labels: NDArray[np.intp]) -> NDArray[np.intp]:
    return np.unique(labels, return_inverse=True)[1].astype(np.intp) if labels.size else labels


def _per_match(
    values: Array,
    mask: NDArray[np.bool_],
    match_of_pair: NDArray[np.intp],
    match_ids: Sequence[int],
    sd: float,
) -> list[dict[str, Any]]:
    """One row per match of the half: the pairs the mask keeps, their mean in metres and in
    placebo sd, and the standard error (NaN below two pairs)."""
    rows = []
    for m, match_id in enumerate(match_ids):
        mine = mask & (match_of_pair == m)
        v = values[mine]
        n = int(v.size)
        mean = float(v.mean()) if n else math.nan
        se = float(v.std(ddof=1) / math.sqrt(n)) if n > 1 else math.nan
        rows.append(
            {
                "match_id": match_id,
                "pairs": n,
                "mean_m": _round(mean, 4),
                "mean_sd": _round(mean / sd, 4),
                "se_m": _round(se, 4),
            }
        )
    return rows


def _pooled(
    values: Array,
    mask: NDArray[np.bool_],
    units: NDArray[np.intp],
    match_of_pair: NDArray[np.intp],
    n_matches: int,
    sd: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """The bar on the pairs the mask keeps: the pooled mean, the sign count over the matches
    and the sign-flip permutation p over the units, with `passes_bar` from the rounded p
    and the count, as `consistency_problems` recomputes it."""
    if not mask.any():
        return {
            "pairs": 0,
            "units": 0,
            "mean_m": None,
            "mean_sd": None,
            "same_sign_matches": 0,
            "of_matches": n_matches,
            "p": None,
            "passes_bar": False,
        }
    verdict = bar_verdict(values[mask], _compact(units[mask]), match_of_pair[mask], n_matches, rng)
    p = _round(verdict.p, 5)
    assert p is not None
    return {
        "pairs": verdict.pairs,
        "units": verdict.units,
        "mean_m": _round(verdict.mean, 4),
        "mean_sd": _round(verdict.mean / sd, 4),
        "same_sign_matches": verdict.same_sign_matches,
        "of_matches": n_matches,
        "p": p,
        "passes_bar": verdict.same_sign_matches >= BAR_SAME_SIGN_MATCHES and p <= BAR_P,
    }


def _ratio(part: float | None, whole: float | None) -> float | None:
    """`part / whole` on the rounded figures, None when either is missing or the whole is 0."""
    if part is None or whole is None or whole == 0.0:
        return None
    return round(part / whole, 4)


def _opposite_signs(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and a * b < 0.0


def subtype_verdict(
    *,
    passes_bar: bool,
    pre_trend_ratio: float | None,
    class_opposite_sign: bool,
    detected_ratio: float | None,
) -> dict[str, Any]:
    """M3, M4 and the candidate flag from the figures as written: the pre-trend ratio
    (pre-trend over the effect on the same pairs) reaching M3_PRE_TREND_SHARE, or the class
    at t_c giving the opposite sign, is M3; the fully-detected effect over the effect below
    M4_DETECTED_SHARE (a sign change included) is M4; a candidate passes the bar and
    survives both. A ratio that cannot be computed (no pairs) leaves the criterion silent
    and is printed as null."""
    pre_trend_reaches = pre_trend_ratio is not None and pre_trend_ratio >= M3_PRE_TREND_SHARE
    m3 = pre_trend_reaches or class_opposite_sign
    m4 = detected_ratio is not None and detected_ratio < M4_DETECTED_SHARE
    return {
        "passes_bar": passes_bar,
        "M3": {
            "pre_trend_ratio": pre_trend_ratio,
            "pre_trend_reaches_share": pre_trend_reaches,
            "class_at_tc_opposite_sign": class_opposite_sign,
            "leaves": m3,
        },
        "M4": {"detected_ratio": detected_ratio, "leaves": m4},
        "candidate": passes_bar and not m3 and not m4,
    }


# --- the section ------------------------------------------------------------------------------


def line_testability(rows: Sequence[dict[str, Any]], subtype: str) -> str:
    """The label of the secondary quantity for a subtype, from the probe's power rows: not
    testable when its line MDE80 is missing or above the threshold in any half."""
    mine = [r for r in rows if r["subtype"] == subtype]
    ok = bool(mine) and all(
        r[f"mde80_{SECONDARY_QUANTITY}_sd"] is not None
        and r[f"mde80_{SECONDARY_QUANTITY}_sd"] <= TESTABILITY_MDE80_SD
        for r in mine
    )
    return TESTABLE_ON_LINE if ok else NOT_TESTABLE_ON_LINE


def section_sha256(section: dict[str, Any]) -> str:
    """The sha256 of a section's canonical JSON: how the effect names the probe section it
    answered to, inside a file whose seal covers both."""
    canonical = json.dumps(section, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _class_rows(
    c: _Collected, match_ids: Sequence[int], sd: float, rngs: Sequence[np.random.Generator]
) -> list[dict[str, Any]]:
    """The effect of the marker by class, every pair of the half whatever its subtype."""
    n_matches = len(match_ids)
    rows = []
    for k, name in enumerate(RUN_CLASSES):
        mask = c.class_of_pair == k
        rows.append(
            {
                "class": name,
                "per_match": _per_match(c.marker_m, mask, c.match_of_pair, match_ids, sd),
                "pooled": _pooled(
                    c.marker_m, mask, c.units, c.match_of_pair, n_matches, sd, rngs[k]
                ),
            }
        )
    return rows


def _subtype_section(
    c: _Collected,
    k: int,
    match_ids: Sequence[int],
    sds: dict[str, float],
    by_class: Sequence[dict[str, Any]],
    testability: str,
) -> dict[str, Any]:
    subtype = SUBTYPES[k]
    n_matches = len(match_ids)
    mine = c.subtype_of_pair == k
    sd_m, sd_l = sds["marker"], sds["line"]

    def rng(stream: int, *key: int) -> np.random.Generator:
        return np.random.default_rng([SEED, stream, k, *key])

    marker_pooled = _pooled(
        c.marker_m, mine, c.units, c.match_of_pair, n_matches, sd_m, rng(STREAM_EFFECT, 0)
    )
    line_pooled = _pooled(
        c.line_m, mine, c.units, c.match_of_pair, n_matches, sd_l, rng(STREAM_EFFECT, 1)
    )
    effect_mean = marker_pooled["mean_m"]

    # the pre-trend, on the pairs with a leg at t - W on both sides, and the effect on them
    has_pre = mine & np.isfinite(c.pre_trend_m)
    pre_rows = _per_match(c.pre_trend_m, has_pre, c.match_of_pair, match_ids, sd_m)
    same_rows = _per_match(c.marker_m, has_pre, c.match_of_pair, match_ids, sd_m)
    pre_mean = _round(float(c.pre_trend_m[has_pre].mean()), 4) if has_pre.any() else None
    same_mean = _round(float(c.marker_m[has_pre].mean()), 4) if has_pre.any() else None
    pre_ratio = _ratio(pre_mean, same_mean)

    # the marker detected throughout both legs
    det = mine & c.detected
    det_rows = _per_match(c.marker_m, det, c.match_of_pair, match_ids, sd_m)
    det_mean = _round(float(c.marker_m[det].mean()), 4) if det.any() else None
    det_sums = np.bincount(c.match_of_pair[det], weights=c.marker_m[det], minlength=n_matches)
    det_signs = (
        int((np.sign(det_sums) == np.sign(det_mean)).sum())
        if det_mean is not None and det_mean != 0.0
        else 0
    )
    det_ratio = _ratio(det_mean, effect_mean)

    # the class at t_c: the subtype's distribution, its modal class, the effect of that class
    classified = mine & (c.class_of_pair >= 0)
    distribution = {
        name: int((c.class_of_pair[mine] == j).sum()) for j, name in enumerate(RUN_CLASSES)
    }
    modal: str | None = None
    if classified.any():
        counts = np.bincount(c.class_of_pair[classified], minlength=len(RUN_CLASSES))
        modal = RUN_CLASSES[int(np.argmax(counts))]  # ties to the first in RUN_CLASSES order
    modal_row = next((r for r in by_class if r["class"] == modal), None)
    modal_mean = None if modal_row is None else modal_row["pooled"]["mean_m"]
    in_modal = mine & (c.class_of_pair == (RUN_CLASSES.index(modal) if modal else -2))
    out_modal = classified & ~in_modal
    class_opposite = _opposite_signs(modal_mean, effect_mean)

    # the run-leg overlap control: the p with the coarser units
    overlap = _pooled(
        c.marker_m, mine, c.overlap_units, c.match_of_pair, n_matches, sd_m, rng(STREAM_OVERLAP)
    )
    overlap_sizes = np.bincount(_compact(c.overlap_units[mine])) if mine.any() else np.zeros(0)

    return {
        "subtype": subtype,
        "pairs": int(mine.sum()),
        "marker": {
            "per_match": _per_match(c.marker_m, mine, c.match_of_pair, match_ids, sd_m),
            "pooled": marker_pooled,
        },
        "line": {
            "testability": testability,
            "per_match": _per_match(c.line_m, mine, c.match_of_pair, match_ids, sd_l),
            "pooled": line_pooled,
        },
        "pre_trend": {
            "pairs": int(has_pre.sum()),
            "of_pairs": int(mine.sum()),
            "per_match": [
                {
                    "match_id": pre["match_id"],
                    "pairs": pre["pairs"],
                    "pre_trend_mean_m": pre["mean_m"],
                    "effect_mean_m": same["mean_m"],
                }
                for pre, same in zip(pre_rows, same_rows, strict=True)
            ],
            "pooled": {
                "pairs": int(has_pre.sum()),
                "pre_trend_mean_m": pre_mean,
                "pre_trend_mean_sd": _ratio(pre_mean, sd_m) if pre_mean is not None else None,
                "effect_mean_m": same_mean,
                "ratio": pre_ratio,
            },
        },
        "fully_detected": {
            "pairs": int(det.sum()),
            "of_pairs": int(mine.sum()),
            "fraction": _round(float(det.sum() / mine.sum()) if mine.any() else math.nan, 4),
            "per_match": det_rows,
            "pooled": {
                "pairs": int(det.sum()),
                "mean_m": det_mean,
                "mean_sd": _ratio(det_mean, sd_m) if det_mean is not None else None,
                "same_sign_matches": det_signs,
                "of_matches": n_matches,
                "effect_mean_m": effect_mean,
                "ratio": det_ratio,
            },
        },
        "class_at_tc": {
            "classified": int(classified.sum()),
            "unclassified": int((mine & (c.class_of_pair < 0)).sum()),
            "distribution": distribution,
            "modal_class": modal,
            "modal_share": _round(
                float(in_modal.sum() / classified.sum()) if classified.any() else math.nan, 4
            ),
            "modal_class_effect": None if modal_row is None else modal_row["pooled"],
            "subtype_effect_mean_m": effect_mean,
            "opposite_sign": class_opposite,
            "subtype_pairs_in_modal_class": {
                "pairs": int(in_modal.sum()),
                "mean_m": _round(float(c.marker_m[in_modal].mean()), 4) if in_modal.any() else None,
            },
            "subtype_pairs_outside_modal_class": {
                "pairs": int(out_modal.sum()),
                "mean_m": _round(float(c.marker_m[out_modal].mean()), 4)
                if out_modal.any()
                else None,
            },
        },
        "run_leg_overlap": {
            "units": int(overlap_sizes.size),
            "largest_unit": int(overlap_sizes.max()) if overlap_sizes.size else 0,
            "protocol_units": marker_pooled["units"],
            "p": overlap["p"],
            "same_sign_matches": overlap["same_sign_matches"],
            "passes_bar": overlap["passes_bar"],
        },
        "verdict": subtype_verdict(
            passes_bar=bool(marker_pooled["passes_bar"]),
            pre_trend_ratio=pre_ratio,
            class_opposite_sign=class_opposite,
            detected_ratio=det_ratio,
        ),
    }


def probe_inputs(current: dict[str, Any]) -> dict[str, Any]:
    """What the effect reads from the probe section: the primary quantity's probable list,
    the two placebo sds and the power rows (for the line's label). The probe section must be
    consistent with the protocol committed in HEAD (`probe.consistency_problems`)."""
    problems = probe_problems(current)
    if problems:
        raise EffectInputError("the probe section is not one to answer to: " + "; ".join(problems))
    probe = current["probe"]
    primary = str(committed_protocol()["design"]["quantities"]["primary"])
    if primary != PRIMARY_QUANTITY:
        raise EffectInputError(
            f"the committed protocol's primary quantity is {primary!r}, the code's "
            f"{PRIMARY_QUANTITY!r}"
        )
    return {
        "primary_quantity": primary,
        "secondary_quantity": SECONDARY_QUANTITY,
        "subtypes": list(probe["power"]["probable"][primary]),
        "placebo_sd_marker_m": float(probe["standardisation"]["placebo_sd_marker_m"]),
        "placebo_sd_line_m": float(probe["standardisation"]["placebo_sd_line_m"]),
        "line_testability": {
            s: line_testability(probe["power"]["rows"], s)
            for s in probe["power"]["probable"][primary]
        },
    }


def build_effect(
    data_dir: Path,
    current: dict[str, Any],
    head: str,
    code_tree: str,
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The `effect` section for the warehouse under `data_dir`, answering to the probe
    section of `current`: values of the calibration half through `MatchTracking`. `head`,
    `code_tree` and `protocol` (the record of the protocol answered to) are taken as given:
    the command passes HEAD, the sha of the committed `runs/` tree and the committed
    protocol's record, `--check` what the file says."""
    inputs = probe_inputs(current)
    calibration = load_half(HALF)
    matches = [effect_match(load_tracking(data_dir, m), data_dir) for m in calibration]
    c = _collect(matches)
    if int(c.marker_m.size) != int(current["probe"]["instrument"]["marker"]["pooled"]["pairs"]):
        raise EffectInputError(
            f"{c.marker_m.size} pairs against the probe's "
            f"{current['probe']['instrument']['marker']['pooled']['pairs']}"
        )
    sds = {"marker": inputs["placebo_sd_marker_m"], "line": inputs["placebo_sd_line_m"]}
    by_class = _class_rows(
        c,
        calibration,
        sds["marker"],
        [np.random.default_rng([SEED, STREAM_CLASSES, j]) for j in range(len(RUN_CLASSES))],
    )
    per_subtype = [
        _subtype_section(
            c,
            SUBTYPES.index(s),
            calibration,
            sds,
            by_class,
            inputs["line_testability"][s],
        )
        for s in inputs["subtypes"]
    ]
    candidates = [r["subtype"] for r in per_subtype if r["verdict"]["candidate"]]
    unclassified = int((c.class_of_pair < 0).sum())
    return {
        "task": TASK,
        "written": WRITTEN,
        "head": head,
        "code_tree_sha": code_tree,
        "half": HALF,
        "matches": calibration,
        "protocol": protocol_record() if protocol is None else dict(protocol),
        "probe_section_sha256": section_sha256(current["probe"]),
        "seed": SEED,
        "seed_streams": {
            "effect": STREAM_EFFECT,
            "classes": STREAM_CLASSES,
            "run_leg_overlap": STREAM_OVERLAP,
            "how": (
                "each permutation draws from the child [seed, stream, subtype index, "
                "quantity index] (classes: [seed, stream, class index]), so the loops' order "
                "moves nothing"
            ),
        },
        "inputs": inputs,
        "what": {
            "effect": (
                "the marker displacement along the run (the primary quantity), run minus "
                "placebo, mean per match and pooled over the half, in metres and in placebo "
                "sd, against the bar: same sign in at least "
                f"{BAR_SAME_SIGN_MATCHES} of {BAR_OF_MATCHES} matches and the sign-flip "
                f"permutation p over the protocol's units at most {BAR_P}; the line height "
                "alongside as the secondary quantity with its testability label, deciding "
                "nothing"
            ),
            "pre_trend": (
                "the same statistic with t_c replaced by t_c - W on both legs (the marker "
                "nearest at t - W, its velocity over [t - W - V, t - W], its displacement "
                "over [t - W, t]), on the pairs whose two legs have it; ratio is its pooled "
                "mean over the effect's on the same pairs; M3 when it reaches "
                f"{M3_PRE_TREND_SHARE}"
            ),
            "fully_detected": (
                "the effect on the pairs whose marker is is_detected at every frame from "
                "t - V to t + W on both legs; ratio is its pooled mean over the effect's "
                f"with every pair; M4 when it falls below {M4_DETECTED_SHARE} (a sign change "
                "is below it)"
            ),
            "class_at_tc": (
                "the class of the run from information up to t_c alone: the runner's "
                "velocity over [t_c - V, t_c] against the ball at t_c, the line L(t_c) and "
                "the nearer touchline; the subtype's distribution over the eight classes, "
                "its modal class and the effect of that class over every pair of the half "
                "whatever its subtype (by_class); M3 when that effect has the opposite sign "
                "to the subtype's; the subtype's pairs inside and outside the modal class "
                "are printed alongside and decide nothing"
            ),
            "run_leg_overlap": (
                "the bar's p with the units coarsened to link, inside the match, runs of a "
                "team whose legs [t_c - V, t_c + W] overlap in time, on top of the "
                "protocol's keys: the dependence a placebo-against-placebo null cannot see "
                "(review of task 49, inherited b); reported, never deciding, the protocol's "
                "unit is fixed"
            ),
            "verdict": (
                "a candidate passes the bar on the marker and survives M3 and M4; the line "
                "never adds or removes one; zero candidates is M5a: P5 dies and the "
                "held-out half is never opened"
            ),
        },
        "windows": {"effect_s": EFFECT_WINDOW_S, "pre_trend_s": [-EFFECT_WINDOW_S, 0.0]},
        "class_at_tc": {
            "classes": list(RUN_CLASSES),
            "pairs": int(c.marker_m.size),
            "unclassified": unclassified,
            "by_class": by_class,
        },
        "per_subtype": per_subtype,
        "candidates": candidates,
        "verdict": {
            "M5a": {
                "rule": "zero candidates -> P5 dies, the held-out half is never opened",
                "candidates": len(candidates),
                "dies": not candidates,
            },
            "alive": bool(candidates),
        },
    }


# --- the command ------------------------------------------------------------------------------


def calibration_path(reports_dir: Path) -> Path:
    return reports_dir / PROBE_NAME


def consistency_problems(current: dict[str, Any]) -> list[str]:
    """What a file with an effect section must satisfy whatever warehouse is at hand: the
    seal; a probe section consistent with the committed protocol, and the one the effect
    answered to (`probe_section_sha256`); the effect's own record of the protocol; the
    subtypes being the probe's probable list on the committed primary quantity, the sds the
    probe's and the line labels following its rows; and every flag following its figures:
    passes_bar from the sign count and the p, M3 and M4 from the ratios and the class sign,
    the candidates from the flags, M5a from the candidates."""
    problems: list[str] = []
    if not sealed(current):
        problems.append("content_sha256 does not cover the file")
    effect = current.get("effect")
    if not isinstance(effect, dict):
        return [*problems, "no effect section"]
    problems += [f"probe: {p}" for p in probe_problems(current)]
    problems += protocol_problems(effect.get("protocol") or {}, "effect.protocol")
    try:
        if effect["probe_section_sha256"] != section_sha256(current["probe"]):
            problems.append("probe_section_sha256 is not the probe section's")
        for key in ("head", "code_tree_sha"):
            if not isinstance(effect[key], str) or len(effect[key]) != 40:
                problems.append(f"{key} is not a git sha")
        if effect["matches"] != load_half(HALF):
            problems.append("matches are not the calibration half")
        probe = current["probe"]
        primary = str(committed_protocol()["design"]["quantities"]["primary"])
        inputs = effect["inputs"]
        if inputs["primary_quantity"] != primary:
            problems.append("inputs.primary_quantity is not the committed protocol's")
        if inputs["subtypes"] != probe["power"]["probable"][primary]:
            problems.append("inputs.subtypes are not the probe's probable list")
        if [r["subtype"] for r in effect["per_subtype"]] != inputs["subtypes"]:
            problems.append("per_subtype does not follow inputs.subtypes")
        for quantity in ("marker", "line"):
            if (
                inputs[f"placebo_sd_{quantity}_m"]
                != probe["standardisation"][f"placebo_sd_{quantity}_m"]
            ):
                problems.append(f"inputs.placebo_sd_{quantity}_m is not the probe's")
        for s, label in inputs["line_testability"].items():
            if label != line_testability(probe["power"]["rows"], s):
                problems.append(f"line_testability of {s} does not follow the probe's rows")
        candidates = []
        for row in effect["per_subtype"]:
            s = row["subtype"]
            pooled = row["marker"]["pooled"]
            passes = pooled["same_sign_matches"] >= BAR_SAME_SIGN_MATCHES and (
                pooled["p"] is not None and pooled["p"] <= BAR_P
            )
            if row["line"]["testability"] != inputs["line_testability"][s]:
                problems.append(f"line.testability of {s} is not inputs'")
            pre = row["pre_trend"]["pooled"]
            det = row["fully_detected"]["pooled"]
            cls = row["class_at_tc"]
            modal_mean = (
                None if cls["modal_class_effect"] is None else cls["modal_class_effect"]["mean_m"]
            )
            expected = subtype_verdict(
                passes_bar=passes,
                pre_trend_ratio=_ratio(pre["pre_trend_mean_m"], pre["effect_mean_m"]),
                class_opposite_sign=_opposite_signs(modal_mean, pooled["mean_m"]),
                detected_ratio=_ratio(det["mean_m"], pooled["mean_m"]),
            )
            if pooled["passes_bar"] != passes:
                problems.append(f"marker.pooled.passes_bar of {s} does not follow its figures")
            if row["verdict"] != expected:
                problems.append(f"verdict of {s} does not follow its figures")
            if expected["candidate"]:
                candidates.append(s)
        if effect["candidates"] != candidates:
            problems.append("candidates do not follow the per-subtype verdicts")
        m5a = effect["verdict"]["M5a"]
        if m5a["candidates"] != len(candidates) or m5a["dies"] != (not candidates):
            problems.append("verdict.M5a does not follow the candidates")
        if effect["verdict"]["alive"] != bool(candidates):
            problems.append("verdict.alive does not follow M5a")
    except (KeyError, TypeError) as exc:
        problems.append(f"the effect section is incomplete: {exc!r}")
    return problems


def _summary(section: dict[str, Any], status: str) -> str:
    rows = " ".join(
        f"{r['subtype']}=({r['marker']['pooled']['mean_m']}m,"
        f"{r['marker']['pooled']['same_sign_matches']}/{r['marker']['pooled']['of_matches']},"
        f"p={r['marker']['pooled']['p']},pre={r['verdict']['M3']['pre_trend_ratio']},"
        f"det={r['verdict']['M4']['detected_ratio']},class={r['class_at_tc']['modal_class']},"
        f"candidate={r['verdict']['candidate']})"
        for r in section["per_subtype"]
    )
    return (
        f"runs effect: warehouse={status} matches={len(section['matches'])} "
        f"subtypes={len(section['per_subtype'])} {rows} candidates={section['candidates']} "
        f"M5a_dies={section['verdict']['M5a']['dies']}"
    )


def run_runs_effect(data_dir: Path, reports_dir: Path, *, check: bool = False) -> int:
    calibration = load_half(HALF)
    at_hand = [m for m in calibration if has_frames(data_dir, m)]
    whole = len(at_hand) == len(calibration)
    path = calibration_path(reports_dir)
    if not path.is_file():
        print(f"runs effect: {path} missing: run `tracklab runs probe` first")
        return 1
    text = path.read_text(encoding="utf-8")
    current = json.loads(text)
    if not check:
        dirty = dirty_code_paths()
        if dirty:
            print(
                f"runs effect: {len(dirty)} path(s) of the code that computes the figures are "
                f"not committed (e.g. {dirty[0]!r}): commit them first, so head and "
                "code_tree_sha name the code that ran"
            )
            return 1
        if not whole:
            print(
                f"runs effect: silver frames for {len(at_hand)} of the {len(calibration)} "
                f"calibration matches under {data_dir}; the section is written from all of "
                "them or not at all"
            )
            return 1
        try:
            section = build_effect(data_dir, current, head_commit(), code_tree_sha())
        except EffectInputError as exc:
            print(f"runs effect: {exc}")
            return 1
        body = {k: v for k, v in current.items() if k != "content_sha256"}
        payload = seal({**body, "effect": section})
        path.write_text(render(payload), encoding="utf-8", newline="\n")
        print(_summary(section, status=f"FULL {len(calibration)}/{len(calibration)}"))
        print(f"runs effect: {path} ({path.stat().st_size} bytes)")
        return 2 if section["verdict"]["M5a"]["dies"] else 0
    problems = consistency_problems(current)
    if whole and not problems:
        try:
            expected = build_effect(
                data_dir,
                current,
                str(current["effect"]["head"]),
                str(current["effect"]["code_tree_sha"]),
                protocol=current["effect"]["protocol"],
            )
        except EffectInputError as exc:
            problems.append(str(exc))
        else:
            if render(expected) != render(current["effect"]):
                problems.append("differs from what the code writes")
        status = f"FULL {len(calibration)}/{len(calibration)} recomputed and equal"
    else:
        status = (
            f"PARTIAL {len(at_hand)}/{len(calibration)} at hand, 0/{len(calibration)} "
            "recomputed: seal, protocol, probe section, subtypes and verdict checked against "
            "the figures as written"
        )
    if problems:
        print(f"runs effect --check: {path} " + "; ".join(problems))
        return 1
    print(_summary(current["effect"], status=status))
    print(f"runs effect --check: {path} matches ({status})")
    return 0


def run_runs_freeze(reports_dir: Path, *, date: str) -> int:
    """Write the frozen protocol from the effect section at hand (the candidates) and the
    `runs/` tree committed in HEAD, which must be the one that computed the section. Writes
    the file and commits nothing; refuses with M5a (rc 2) when there is no candidate."""
    dirty = dirty_code_paths()
    if dirty:
        print(
            f"runs freeze: {len(dirty)} path(s) of the code or the protocol are not committed "
            f"(e.g. {dirty[0]!r}): the freeze records the committed runs/ tree"
        )
        return 1
    calibration = calibration_path(reports_dir)
    if not calibration.is_file():
        print(f"runs freeze: {calibration} missing: run `tracklab runs effect` first")
        return 1
    current = json.loads(calibration.read_text(encoding="utf-8"))
    problems = consistency_problems(current)
    if problems:
        print(f"runs freeze: {calibration} " + "; ".join(problems))
        return 1
    effect = current["effect"]
    tree = code_tree_sha()
    if effect["code_tree_sha"] != tree:
        print(
            f"runs freeze: the effect section was computed by runs/ tree "
            f"{effect['code_tree_sha'][:12]}, HEAD holds {tree[:12]}: regenerate it on this "
            "tree first (the freeze records the tree that computed the candidates)"
        )
        return 1
    if not effect["candidates"]:
        print(
            "runs freeze: zero candidates (M5a): P5 dies, the protocol stays in design and "
            "the held-out half is never opened"
        )
        return 2
    path = protocol_path(reports_dir)
    if not path.is_file():
        print(f"runs freeze: {path} missing")
        return 1
    try:
        frozen = freeze_payload(
            read_protocol(path),
            candidates=effect["candidates"],
            code_tree=tree,
            calibration_sha256=str(current["content_sha256"]),
            date=date,
        )
    except ValueError as exc:
        print(f"runs freeze: {exc}")
        return 1
    path.write_text(render(frozen), encoding="utf-8", newline="\n")
    print(
        f"runs freeze: {path} stage {frozen['stage']} candidates={frozen['frozen']['candidates']} "
        f"code_tree_sha={tree[:12]} fingerprint={frozen['fingerprint'][:12]} "
        f"(was {STAGE_DESIGN}; commit it alone, with the plan, to freeze)"
    )
    return 0
