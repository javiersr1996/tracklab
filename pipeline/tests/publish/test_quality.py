"""`web/public/data/quality.json` against `tracklab.publish.quality`, the module
it is built from (task 30), and the hook shot's selection rule on fabricated
flights (no data directory needed for that half).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tracklab.publish.quality import (
    Flight,
    build_hook,
    build_summary,
    quality_rows,
    select_hook_flight,
)

PIPELINE = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE.parent
DATA = PIPELINE / "data"
REPORTS = PIPELINE / "reports"
QUALITY_JSON = REPO_ROOT / "web" / "public" / "data" / "quality.json"

pytestmark = pytest.mark.skipif(
    not REPORTS.is_dir() or not QUALITY_JSON.is_file(),
    reason="pipeline/reports or web/public/data/quality.json missing; "
    "run `tracklab quality` then `tracklab publish quality`",
)


def _payload() -> dict[str, Any]:
    return json.loads(QUALITY_JSON.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_checks_match_what_tracklab_publish_quality_computes() -> None:
    assert _payload()["checks"] == quality_rows(REPORTS)


def test_summary_matches_too() -> None:
    assert _payload()["summary"] == build_summary(REPORTS)


@pytest.mark.skipif(not DATA.is_dir(), reason="pipeline/data missing")
def test_hook_matches_the_real_calibration_flights() -> None:
    assert _payload()["hook"] == build_hook(DATA)


# `select_hook_flight` on fabricated flights: the rule itself, not the reader.


def _flight(match_id: str, start: int, g: float) -> Flight:
    return Flight(
        match_id=match_id,
        shot_id=f"shot-{match_id}-{start}",
        start_frame=start,
        g=g,
        t_s=[],
        z_m=[0.0],
    )


def test_picks_the_flight_exactly_on_the_median() -> None:
    flights = [_flight("bb:1", 10, 7.5), _flight("bb:1", 20, 8.0), _flight("bb:2", 5, 9.0)]
    best, median = select_hook_flight(flights)
    assert median == 8.0
    assert (best.match_id, best.start_frame) == ("bb:1", 20)


def test_ties_break_on_match_id_first() -> None:
    # median of [6, 8, 10, 12] is 9; the g=8 and g=10 flights are both 1.0 away.
    flights = [
        _flight("bb:2", 1, 8.0),
        _flight("bb:1", 5, 10.0),
        _flight("bb:3", 1, 6.0),
        _flight("bb:4", 1, 12.0),
    ]
    best, median = select_hook_flight(flights)
    assert median == 9.0
    assert best.match_id == "bb:1"  # "bb:1" sorts before "bb:2", the other tied flight


def test_ties_break_on_start_frame_within_the_same_match() -> None:
    # Median of two flights is their mean, 10.0: both 8.0 and 12.0 sit 2.0 away.
    flights = [_flight("bb:1", 5, 8.0), _flight("bb:1", 3, 12.0)]
    best, median = select_hook_flight(flights)
    assert median == 10.0
    assert best.start_frame == 3  # the earlier of the two equidistant flights wins


def test_no_flights_raises() -> None:
    with pytest.raises(ValueError):
        select_hook_flight([])


def test_mutation_picking_the_smallest_g_instead_of_the_closest_breaks_the_rule() -> None:
    """A rule that returned the smallest g (or the largest, or the first) would
    also be deterministic; it would just be the wrong rule. On this fixture it
    disagrees with the real one, which is the point of the check."""
    flights = [_flight("bb:1", 1, 6.0), _flight("bb:1", 2, 8.0), _flight("bb:1", 3, 8.1)]
    best, median = select_hook_flight(flights)
    assert median == 8.0
    assert best.start_frame == 2
    smallest_g = min(flights, key=lambda f: f.g)
    assert smallest_g.start_frame != best.start_frame
