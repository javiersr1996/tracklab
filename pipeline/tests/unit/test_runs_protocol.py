"""`tracklab runs protocol` and the held-out guard (task 47, hardened in the review of 47-48).

The split regenerates from the 20 rows the committed protocol carries, so it runs on the CI
fixtures (one match) as on the real warehouse; where the warehouse at hand holds every
match, `--check` also regenerates the rows and the placebo counts from it and says
`FULL 20/20`, otherwise `PARTIAL n/20`: a pass on the file's consistency, never on the data.
What a partial check cannot see (a kickoff of an absent match moved and the file re-rendered)
is pinned here as literals: decision 3's two lists and the design's fingerprint.

The guard reads the protocol committed in HEAD of the repository the code lives in, verifies
its seal and regenerates the lists from its rows; it takes no path. It is exercised on
throwaway git repositories (`data.repo_root` monkeypatched, the one way to point it
elsewhere, which a test greps `src/` for) and on this repository's own HEAD.

Mutations recorded in tasks/todo.md: the guard removed from `load_half` fails the
closed-half tests; the alternation parity flipped in `split_matches` fails the regeneration
and the fabricated-rows tests; `_rows_against` returning `[]` fails the partial-warehouse
test; each of five placebo SQL mutants fails the hand-counted match.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.cli import _cmd_runs_protocol, build_parser
from tracklab.paths import data_root
from tracklab.runs import data
from tracklab.runs.data import (
    HeldOutLocked,
    counting_match_ids,
    head_stage,
    load_half,
    match_halves,
    require_readable,
)
from tracklab.runs.placebo import PlaceboCount, placebo_counts, placebo_instants
from tracklab.runs.protocol import (
    CALIBRATION_IN_REPO,
    FREEZE_NOTE,
    FREEZE_TASK,
    NUMPY_VERSION,
    STAGE_DESIGN,
    STAGE_FROZEN,
    MatchRow,
    build_protocol,
    fingerprint,
    freeze_payload,
    frozen_problems,
    partition_flags,
    read_protocol,
    render,
    rows_from_protocol,
    run_runs_protocol,
    seal,
    sealed,
    split_matches,
    warehouse_kickoffs,
    z_two_sided,
)

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
PROTOCOL = REPORTS / "runs_protocol.json"
FIXTURES = PIPELINE / "tests" / "fixtures" / "data"
CI_FIXTURE_MATCH = 1874553
HELD_OUT_MATCH = 1899585

# Decision 3, split A, as Javier confirmed it on 2026-10-09, and the fingerprint of the design
# regenerated in the review of task 49 (the unit of the null, the real-null check, the power
# simulating the bar and z_equivalent derived; before it, the second review of tasks 47-48).
# A change of either is a change of the preregistration and must show as a diff of this
# file, never only of the JSON.
CALIBRATION = [
    1874553,
    1886347,
    1925299,
    1959846,
    1996435,
    1996436,
    2007448,
    2010085,
    2011166,
    2015213,
]
HELD_OUT = [
    1899585,
    1927964,
    1953632,
    1986691,
    2006229,
    2006363,
    2007721,
    2013725,
    2016236,
    2017461,
]
FINGERPRINT = "83630615f86297318d519692a0b2ace271a00b485913540eceb285a56cb5b1aa"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(render(payload), encoding="utf-8", newline="\n")


def _as_design(payload: dict[str, Any]) -> dict[str, Any]:
    """The committed protocol as tasks 47 and 49 wrote it, whatever stage it is in now: the
    tests below start from the design file so that task 50's freeze cannot flip them."""
    return seal(
        {
            **payload,
            "stage": STAGE_DESIGN,
            "history": [h for h in payload["history"] if h["stage"] == STAGE_DESIGN],
        }
    )


def _design() -> dict[str, Any]:
    return _as_design(read_protocol(PROTOCOL))


def _freeze(
    payload: dict[str, Any], note: str | None = None, code_tree: str = "0" * 40
) -> dict[str, Any]:
    """A freeze as task 50 commits it, through the code's own path: stage, the candidates and
    the sha of the `runs/` tree in `frozen`, a history entry and the seal recomputed. The
    guard tests pass HEAD's tree of their throwaway repository; a file-only test any sha."""
    return freeze_payload(
        _as_design(payload),
        candidates=["support"],
        code_tree=code_tree,
        calibration_sha256="c" * 64,
        date="2026-10-12",
        **({} if note is None else {"note": note}),
    )


# --- the split -------------------------------------------------------------------------


def test_split_regenerates_from_the_committed_rows() -> None:
    payload = read_protocol(PROTOCOL)
    rows = rows_from_protocol(payload)
    assert len(rows) == 20
    calibration, held_out = split_matches(rows)
    split = payload["design"]["split"]
    assert (calibration, held_out) == (split["calibration"], split["held_out"])
    assert len(calibration) == 10
    assert len(held_out) == 10
    assert not set(calibration) & set(held_out)
    by_id = {r.match_id: r for r in rows}
    for half in (calibration, held_out):
        assert sum(by_id[m].event_coords_exact for m in half) == 5
    assert CI_FIXTURE_MATCH in calibration


def test_the_split_is_decision_3s_and_the_fingerprint_is_pinned() -> None:
    """Literals, because a partial `--check` cannot see a kickoff of an absent match moved
    and the file re-rendered: the lists and the fingerprint would change, and this would not."""
    payload = read_protocol(PROTOCOL)
    assert payload["design"]["split"]["calibration"] == CALIBRATION
    assert payload["design"]["split"]["held_out"] == HELD_OUT
    assert split_matches(rows_from_protocol(payload)) == (CALIBRATION, HELD_OUT)
    assert payload["fingerprint"] == FINGERPRINT


def test_the_earliest_match_of_each_group_opens_calibration() -> None:
    rows = rows_from_protocol(read_protocol(PROTOCOL))
    calibration, _ = split_matches(rows)
    for exact in (True, False):
        group = [r for r in rows if r.event_coords_exact is exact]
        first = min(group, key=lambda r: (r.kickoff_utc, r.match_id))
        assert first.match_id in calibration


def test_split_alternates_by_kickoff_inside_each_group_and_breaks_ties_by_id() -> None:
    rows = [
        MatchRow(5, "2025-01-01T00:00:00Z", True, False),
        MatchRow(1, "2025-01-02T00:00:00Z", True, False),
        MatchRow(3, "2025-01-03T00:00:00Z", True, True),
        MatchRow(9, "2024-12-01T00:00:00Z", False, False),
        MatchRow(8, "2024-12-01T00:00:00Z", False, False),
    ]
    assert split_matches(rows) == ([3, 5, 8], [1, 9])


def test_the_committed_rows_carry_the_flags_of_quality_partitions() -> None:
    flags = partition_flags(REPORTS)
    rows = rows_from_protocol(read_protocol(PROTOCOL))
    assert {r.match_id for r in rows} == set(flags)
    for row in rows:
        assert row.event_coords_exact == flags[row.match_id]["event_coords_exact"]
        assert row.layout_extra_footage == flags[row.match_id]["layout_extra_footage"]


# --- the committed file against the code ------------------------------------------------


def test_the_committed_protocol_is_what_the_code_writes() -> None:
    assert run_runs_protocol(data_root(), REPORTS, check=True) == 0


def test_the_protocol_carries_the_plans_bar() -> None:
    """Decision 4 and the null, as Javier confirmed them; a change here is a change of the
    preregistration and must show as a diff of this test, never only of the JSON."""
    payload = read_protocol(PROTOCOL)
    assert payload["stage"] in (STAGE_DESIGN, STAGE_FROZEN)
    bar = payload["design"]["bar"]
    assert bar["calibration"] == {
        "same_sign_matches_at_least": 8,
        "of_matches": 10,
        "p_at_most": 0.00135,
        "z_equivalent": round(z_two_sided(0.00135), 4),
    }
    # the z of the plan's decision 4 (3.0) is the one-sided quantile of 0.00135; the p is
    # two-sided, so the z it is equivalent to is 3.205 (review of task 49, derived not written)
    assert bar["calibration"]["z_equivalent"] == pytest.approx(3.2051, abs=1e-3)
    assert bar["testability"]["mde80_sd_at_most"] == 0.3
    assert "Binomial(n_permutations" in bar["testability"]["in"]
    null = payload["design"]["null"]
    assert "per unit (effect.unit_of_independence)" in null["how"]
    assert "placebo 1 minus placebo 2" in null["real_null_check"]
    assert "shared placebo instant" in payload["history"][1]["note"]
    assert [h["task"] for h in payload["history"][:2]] == [47, 49]
    assert payload["design"]["effect"]["unit_of_independence"].startswith("the unit: the conn")
    # the primary quantity, decided by Javier in the review of task 49 after the corrected
    # power split the lists (marker 3, line 1): literals, so a field removed or set to the
    # line shows here and not only in the JSON
    quantities = payload["design"]["quantities"]
    assert quantities["primary"] == "marker" and quantities["secondary"] == "line"
    assert quantities["primary_is_for"].startswith("the marker displacement, the forced-dir")
    for task in ("M1", "task 50", "task 51", "Holm"):
        assert task in quantities["primary_is_for"]
    assert "not testable on the line with this sample" in quantities["secondary_rule"]
    assert "never adds or removes a candidate" in quantities["secondary_rule"]
    assert "before any per-subtype effect exists" in quantities["decided"]
    assert [h["task"] for h in payload["history"][:3]] == [47, 49, 49]
    assert payload["history"][2]["date"] == "2026-10-11"
    assert payload["history"][2]["note"].startswith("primary quantity: marker (design.quant")
    assert "in another period, or more than V + W" in null["real_null_check"]
    assert bar["held_out"]["same_sign_matches_at_least"] == 8
    assert bar["held_out"]["p_at_most"] == 0.01
    assert payload["design"]["null"]["n_permutations"] == 2000
    assert set(payload["design"]["death_criteria"]) >= {"M1", "M2", "M3", "M4", "M5a", "M5b"}
    assert payload["design"]["placebo"]["teammates_runs"]["excluded"] is True


def test_the_unsourced_constants_are_marked_as_hypotheses_for_task_49() -> None:
    """W, V and the minimum run length have no measured source: the protocol says so and
    hands each to task 49, which may replace it once, in history."""
    design = read_protocol(PROTOCOL)["design"]
    for text in (
        design["windows"]["effect_window_rule"],
        design["windows"]["velocity_window_rule"],
        design["instrument"]["min_run_length_rule"],
    ):
        assert "hypothesis" in text and "task 49" in text and "history" in text


def test_fingerprint_follows_the_design_and_nothing_else() -> None:
    payload = read_protocol(PROTOCOL)
    assert payload["fingerprint"] == fingerprint(payload["design"])
    moved = json.loads(json.dumps(payload["design"]))
    moved["bar"]["calibration"]["p_at_most"] = 0.05
    assert fingerprint(moved) != payload["fingerprint"]
    assert sealed(payload)
    assert seal({k: v for k, v in payload.items() if k != "content_sha256"}) == payload
    assert not sealed({**payload, "written": "1999-01-01"})
    assert _as_design(_design()) == _design()


def test_protocol_names_no_local_machine(assert_no_local_traces: Callable[[object], None]) -> None:
    assert_no_local_traces(read_protocol(PROTOCOL))


def test_the_numpy_the_protocol_names_is_the_pin_of_pyproject() -> None:
    """`NUMPY_VERSION` is read from the installed package; the pin in pyproject.toml (and so
    uv.lock, audited by `uv sync --locked`) must be that version, or the protocol would name a
    numpy the code does not run with."""
    pyproject = (PIPELINE / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"numpy=={NUMPY_VERSION}"' in pyproject
    assert read_protocol(PROTOCOL)["design"]["dependencies"] == {"numpy": NUMPY_VERSION}


@pytest.fixture
def reports_copy(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    reports.mkdir()
    shutil.copy(REPORTS / "quality_partitions.csv", reports)
    shutil.copy(PROTOCOL, reports)
    return reports


def test_check_passes_on_an_untouched_copy(reports_copy: Path) -> None:
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 0


# The fixture silver is not versioned: the `ci` workflow builds it with `tracklab build`
# before the tests, `full-build` and a clean clone with the real data root do not have it.
needs_the_fixture_silver = pytest.mark.skipif(
    not (FIXTURES / "silver" / "dim_match").is_dir(),
    reason="the fixture silver is not built (only `tracklab build` on the fixtures writes it)",
)


@needs_the_fixture_silver
def test_check_says_how_much_of_the_warehouse_backed_it(
    reports_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`FULL 20/20` only when every match of the split is in the warehouse at hand and the
    counts were recomputed; the fixtures (one match) always say `PARTIAL 1/20`."""
    complete = set(partition_flags(REPORTS)) <= set(warehouse_kickoffs(data_root()))
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 0
    out = capsys.readouterr().out
    assert ("warehouse=FULL 20/20" in out) is complete
    assert ("counts recomputed" in out) is complete
    assert run_runs_protocol(FIXTURES, reports_copy, check=True) == 0
    out = capsys.readouterr().out
    assert "warehouse=PARTIAL 1/20" in out and "counts as written" in out
    assert "FULL" not in out


def _move_a_threshold(p: dict[str, Any]) -> None:
    p["design"]["bar"]["calibration"]["p_at_most"] = 0.05


def _swap_a_match(p: dict[str, Any]) -> None:
    split = p["design"]["split"]
    split["held_out"].append(split["calibration"].pop(0))


def _flip_a_flag(p: dict[str, Any]) -> None:
    row = p["design"]["split"]["matches"][0]
    row["event_coords_exact"] = not row["event_coords_exact"]


def _change_the_seed(p: dict[str, Any]) -> None:
    p["design"]["null"]["seed"] += 1


def _edit_a_count(p: dict[str, Any]) -> None:
    p["evidence"]["placebo_counts_calibration"]["per_match"][0]["team_overlap"] += 1


def _flip_the_stage_by_hand(p: dict[str, Any]) -> None:
    """`design` to `frozen` or back, without resealing: the seal and the history give it away."""
    p["stage"] = STAGE_FROZEN if p["stage"] == STAGE_DESIGN else STAGE_DESIGN


@pytest.mark.parametrize(
    "edit",
    [
        _move_a_threshold,
        _swap_a_match,
        _flip_a_flag,
        _change_the_seed,
        _edit_a_count,
        _flip_the_stage_by_hand,
    ],
)
def test_check_fails_when_the_protocol_is_edited_by_hand(
    reports_copy: Path, edit: Callable[[dict[str, Any]], None]
) -> None:
    path = reports_copy / PROTOCOL.name
    payload = read_protocol(path)
    edit(payload)
    _write(path, payload)
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 1


def test_check_fails_when_the_protocol_is_missing(reports_copy: Path) -> None:
    (reports_copy / PROTOCOL.name).unlink()
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 1


def _move_the_fixture_kickoff(rows: list[MatchRow]) -> list[MatchRow]:
    return [
        MatchRow(r.match_id, "2024-11-23T07:00:00Z", r.event_coords_exact, r.layout_extra_footage)
        if r.match_id == CI_FIXTURE_MATCH
        else r
        for r in rows
    ]


def _flip_the_fixture_flag(rows: list[MatchRow]) -> list[MatchRow]:
    return [
        MatchRow(r.match_id, r.kickoff_utc, not r.event_coords_exact, r.layout_extra_footage)
        if r.match_id == CI_FIXTURE_MATCH
        else r
        for r in rows
    ]


def _rename_the_fixture_match(rows: list[MatchRow]) -> list[MatchRow]:
    return [
        MatchRow(r.match_id + 1, r.kickoff_utc, r.event_coords_exact, r.layout_extra_footage)
        if r.match_id == CI_FIXTURE_MATCH
        else r
        for r in rows
    ]


@needs_the_fixture_silver
@pytest.mark.parametrize(
    "doctor", [_move_the_fixture_kickoff, _flip_the_fixture_flag, _rename_the_fixture_match]
)
def test_check_on_a_partial_warehouse_compares_the_rows_at_hand(
    reports_copy: Path, doctor: Callable[[list[MatchRow]], list[MatchRow]]
) -> None:
    """The file re-rendered by the code from doctored rows is self-consistent (fingerprint and
    seal included), so only the comparison with the warehouse and the flags at hand can see
    it: `_rows_against` returning `[]` passes all three. Run on the fixtures on purpose, where
    the warehouse holds the fixture match alone and the partial path is the one taken."""
    path = reports_copy / PROTOCOL.name
    current = read_protocol(path)
    counts = [
        PlaceboCount(**r) for r in current["evidence"]["placebo_counts_calibration"]["per_match"]
    ]
    _write(path, build_protocol(doctor(rows_from_protocol(current)), counts))
    assert run_runs_protocol(FIXTURES, reports_copy, check=True) == 1


def test_check_verifies_a_frozen_file_and_sees_a_threshold_moved_after_the_freeze(
    reports_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """After task 50 the V gate still runs `--check`: a freeze that keeps the design, the
    evidence and the seal passes; a threshold moved and resealed after it fails (the mutation
    task 51 names); a stage flipped without resealing fails on the seal."""
    path = reports_copy / PROTOCOL.name
    payload = read_protocol(path)
    _write(path, _freeze(payload, note="frozen with the candidates of task 50"))
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 0
    assert "stage frozen" in capsys.readouterr().out
    moved = _freeze(payload)
    moved["design"]["bar"]["calibration"]["p_at_most"] = 0.05
    moved["fingerprint"] = fingerprint(moved["design"])
    _write(path, seal(moved))
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 1
    assert "design differs" in capsys.readouterr().out
    _write(path, {**_as_design(payload), "stage": STAGE_FROZEN})  # the design seal, flipped
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 1
    out = capsys.readouterr().out
    assert "content_sha256" in out and "no frozen entry" in out


def test_write_mode_refuses_to_overwrite_a_frozen_file(reports_copy: Path) -> None:
    path = reports_copy / PROTOCOL.name
    _write(path, _freeze(read_protocol(path)))
    before = path.read_bytes()
    assert run_runs_protocol(data_root(), reports_copy, check=False) == 1
    assert path.read_bytes() == before


def test_write_mode_reproduces_the_committed_design_or_refuses_a_partial_warehouse(
    reports_copy: Path,
) -> None:
    (reports_copy / PROTOCOL.name).unlink()
    code = run_runs_protocol(data_root(), reports_copy, check=False)
    if set(partition_flags(REPORTS)) <= set(warehouse_kickoffs(data_root())):
        assert code == 0
        committed = read_protocol(PROTOCOL)
        written = read_protocol(reports_copy / PROTOCOL.name)
        for key in ("fingerprint", "design", "evidence"):
            assert written[key] == committed[key], key
        if committed["stage"] == STAGE_DESIGN:
            assert (reports_copy / PROTOCOL.name).read_bytes() == PROTOCOL.read_bytes()
    else:
        assert code == 1
        assert not (reports_copy / PROTOCOL.name).exists()


def test_cli_wires_runs_protocol() -> None:
    args = build_parser().parse_args(["runs", "protocol", "--check"])
    assert args.func is _cmd_runs_protocol
    assert args.check is True
    assert args.data_dir == data_root()


# --- placebo counts: coverage only ------------------------------------------------------


def _football_events_at_hand() -> bool:
    return any((data_root() / "bronze" / "football" / "dynamic_events").glob("*.parquet"))


needs_football_events = pytest.mark.skipif(
    not _football_events_at_hand(), reason="no football dynamic_events under the data root"
)


@needs_football_events
def test_placebo_counts_nest_from_runs_down_to_the_strictest_rule() -> None:
    """On the data root at hand (the fixture match in CI): the rules are nested, so the counts
    must be too, and every run finds its possession. The fixture slice has no candidate, so
    the hand-counted match below is what exercises the SQL."""
    rows = placebo_counts(data_root(), [CI_FIXTURE_MATCH])
    assert [r.match_id for r in rows] == [CI_FIXTURE_MATCH]
    r = rows[0]
    assert r.runs > 0
    assert r.runs_without_possession == 0
    assert r.runs >= r.with_candidate >= r.runner_overlap >= r.team_overlap >= 0
    assert r.with_candidate >= r.runner_start >= r.team_start >= 0
    assert r.runner_start >= r.runner_overlap
    assert r.team_start >= r.team_overlap


@needs_football_events
def test_placebo_counts_of_an_absent_match_are_no_row() -> None:
    assert placebo_counts(data_root(), [1]) == []


def _parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _hand_counted_match(root: Path) -> None:
    """Match 1, period 1, team 10 (runner R = 1, teammates 2 and 3). Phases 0 [0, 199],
    1 [200, 299], 2 [400, 499] and 3 [600, 699]. The run starts 10 frames before its own
    possession (offset -10); a teammate's run at 250-260 is the only exclusion and carries no
    possession, so it produces no candidates of its own.

    Candidates of run_1 and their fate under the committed SQL (margin 30 frames):
      pp_1a  player 2, phase 1, starts 220 -> t' = 210, window [180, 240]: no run -> admissible
             under every rule
      pp_1b  player 3, phase 1, starts 290 -> t' = 280, window [250, 310]: run_t2 overlaps and
             starts exactly 30 away -> admissible under the runner rules only
      pp_2   player 2, phase 2, starts 405 -> t' = 395, outside [400, 499] -> no candidate
      pp_0b  player 2, phase 0 (the run's own phase) -> no candidate
      pp_3   player 1 (the runner), phase 3 -> no candidate
      pp_3c  player 2, phase 3, another phase type -> no candidate
    """
    football = root / "bronze" / "football"
    _parquet(
        football / "phases_of_play" / "1.parquet",
        [
            {"match_id": 1, "index": i, "period": 1, "frame_start": a, "frame_end": b}
            for i, (a, b) in enumerate([(0, 199), (200, 299), (400, 499), (600, 699)])
        ],
    )

    def event(
        event_id: str,
        kind: str,
        player: int,
        start: int,
        phase: int,
        phase_type: str = "build_up",
        possession_start: int | None = None,
    ) -> dict[str, object]:
        return {
            "match_id": 1,
            "event_id": event_id,
            "event_type": kind,
            "player_id": player,
            "team_id": 10,
            "frame_start": start,
            "frame_end": start + (20 if kind == "off_ball_run" else 5),
            "phase_index": phase,
            "team_in_possession_phase_type": phase_type,
            "associated_player_possession_frame_start": possession_start,
        }

    _parquet(
        football / "dynamic_events" / "1.parquet",
        [
            event("run_1", "off_ball_run", 1, 50, 0, possession_start=60),
            {**event("run_t2", "off_ball_run", 3, 250, 1), "frame_end": 260},
            event("pp_0", "player_possession", 1, 60, 0),
            event("pp_0b", "player_possession", 2, 160, 0),
            event("pp_1a", "player_possession", 2, 220, 1),
            event("pp_1b", "player_possession", 3, 290, 1),
            event("pp_2", "player_possession", 2, 405, 2),
            event("pp_3", "player_possession", 1, 650, 3),
            event("pp_3c", "player_possession", 2, 620, 3, phase_type="counter"),
        ],
    )


def test_placebo_rules_on_a_hand_counted_match(tmp_path: Path) -> None:
    """Each of five SQL mutants changes the `team_overlap` instants: the offset sign flipped
    (t' = 230 and 415, not 210), the team rule written as the runner rule (280 admitted), the
    phase window dropped (395 admitted), the run's own phase allowed (150 admitted), the
    runner admitted as his own candidate (640 admitted)."""
    _hand_counted_match(tmp_path)
    key = (1, "run_1")
    assert placebo_instants(tmp_path, [1], "team_overlap") == {key: [(1, 210)]}
    assert placebo_instants(tmp_path, [1], "runner_overlap") == {key: [(1, 210), (1, 280)]}
    assert placebo_instants(tmp_path, [1], "team_start") == {key: [(1, 210)]}
    assert placebo_instants(tmp_path, [1], "runner_start") == {key: [(1, 210), (1, 280)]}
    assert placebo_counts(tmp_path, [1]) == [
        PlaceboCount(
            match_id=1,
            runs=2,
            runs_without_possession=1,
            with_candidate=1,
            runner_overlap=1,
            team_overlap=1,
            runner_start=1,
            team_start=1,
        )
    ]


# --- the guard on the held-out half -----------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository the guard is pointed at. Monkeypatching `data.repo_root` is the
    only way to do so (there is no path argument), and nothing under src/ does."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "ci@example.invalid")
    _git(tmp_path, "config", "user.name", "ci")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "status.showUntrackedFiles", "no")  # the guard must not care
    # a code tree at the probe's path, committed first: the freeze records its sha, and the
    # guard compares HEAD's against it
    code = tmp_path / data.CODE_IN_REPO / "windows.py"
    code.parent.mkdir(parents=True)
    code.write_text("# the code tree of the throwaway repository\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "code")
    monkeypatch.setattr(data, "repo_root", lambda: tmp_path)
    return tmp_path


def _frozen_here() -> dict[str, Any]:
    """The committed design frozen with the `runs/` tree HEAD of the throwaway holds."""
    return _freeze(read_protocol(PROTOCOL), code_tree=data.code_tree_sha())


def _protocol_path(repo: Path) -> Path:
    path = repo / data.PROTOCOL_IN_REPO
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _commit(repo: Path, payload: dict[str, Any], message: str) -> Path:
    path = _protocol_path(repo)
    _write(path, payload)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)
    return path


def test_held_out_is_closed_while_the_committed_protocol_is_in_design(repo: Path) -> None:
    _commit(repo, _design(), "protocol in stage design")
    with pytest.raises(HeldOutLocked, match="'design'"):
        load_half("held_out")


def test_held_out_is_closed_in_a_dirty_tree_even_when_frozen(repo: Path) -> None:
    _commit(repo, _frozen_here(), "frozen")
    (repo / "pipeline" / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(HeldOutLocked, match="dirty"):
        load_half("held_out")


def test_held_out_is_closed_when_a_tracked_file_is_edited(repo: Path) -> None:
    (repo / "pipeline" / "code.py").parent.mkdir(parents=True, exist_ok=True)
    (repo / "pipeline" / "code.py").write_text("x = 1\n", encoding="utf-8")
    _commit(repo, _frozen_here(), "frozen with code")
    assert load_half("held_out") == HELD_OUT
    (repo / "pipeline" / "code.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(HeldOutLocked, match="dirty"):
        load_half("held_out")


def test_held_out_is_closed_when_head_has_no_protocol(repo: Path) -> None:
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "no protocol yet")
    _write(_protocol_path(repo), _frozen_here())  # the working copy only
    with pytest.raises(HeldOutLocked, match="holds no"):
        load_half("held_out")
    with pytest.raises(HeldOutLocked, match="holds no"):
        load_half("calibration")


def test_held_out_opens_only_frozen_in_a_clean_tree(repo: Path) -> None:
    """The blob is decoded as UTF-8 whatever the console code page: the note carries an Á."""
    _commit(
        repo,
        _freeze(read_protocol(PROTOCOL), note="congelado: Álvaro", code_tree=data.code_tree_sha()),
        "frozen",
    )
    assert load_half("held_out") == HELD_OUT
    assert load_half("calibration") == CALIBRATION
    require_readable(HELD_OUT_MATCH)


def test_held_out_is_closed_after_a_code_commit_following_the_freeze(repo: Path) -> None:
    """The plan's mutation for `code_tree_sha` (task 50): the freeze committed and opening,
    then a change in `runs/windows.py` committed, the tree clean: the `runs/` tree of HEAD is
    not the one the freeze recorded, and the held-out half closes again. With the sha
    comparison removed from the guard it stays open and this test fails."""
    _commit(repo, _frozen_here(), "frozen")
    assert load_half("held_out") == HELD_OUT
    code = repo / data.CODE_IN_REPO / "windows.py"
    code.write_text("# a change after the freeze\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "code after the freeze")
    assert data.dirty_paths(repo) == []
    with pytest.raises(HeldOutLocked, match="not the one the freeze recorded"):
        load_half("held_out")
    with pytest.raises(HeldOutLocked, match="not the one the freeze recorded"):
        require_readable(HELD_OUT_MATCH)
    assert load_half("calibration") == CALIBRATION  # the calibration half needs no freeze


def test_held_out_is_closed_when_frozen_has_no_frozen_history_entry(repo: Path) -> None:
    """The plan's mutation for the history (task 50): `stage: "frozen"` with `history` cut to
    the design entries, resealed and committed, is refused; so is a frozen entry placed
    before the design ones. A guard that looks at `stage` alone opens both and this test
    fails."""
    frozen = _frozen_here()
    cut = seal({**frozen, "history": [h for h in frozen["history"] if h["stage"] == STAGE_DESIGN]})
    _commit(repo, cut, "frozen without the entry")
    assert data.head_stage() == STAGE_FROZEN
    with pytest.raises(HeldOutLocked, match="history has no frozen entry"):
        load_half("held_out")
    first = seal({**frozen, "history": [frozen["history"][-1], *frozen["history"][:-1]]})
    _commit(repo, first, "frozen entry before the design ones")
    with pytest.raises(HeldOutLocked, match="history has no frozen entry"):
        load_half("held_out")
    _commit(repo, frozen, "frozen")
    assert load_half("held_out") == HELD_OUT


def test_freeze_payload_keeps_the_design_and_records_what_the_guard_reads() -> None:
    """The code path of the freeze (task 50, prepared and not run on this repository): the
    design and its fingerprint untouched, `frozen` with the candidates (in the subtypes'
    order), the tree sha and the calibration file's seal, a frozen entry after the design
    ones carrying the two texts the second review of task 49 left to the freeze; it refuses
    a frozen file, an unsealed one, no candidate or an unknown one; `frozen_problems` sees
    the block, the candidates and the sha."""
    design = _design()
    frozen = freeze_payload(
        design,
        candidates=["support", "coming_short"],
        code_tree="a" * 40,
        calibration_sha256="b" * 64,
        date="2026-10-12",
    )
    assert frozen["stage"] == STAGE_FROZEN and sealed(frozen)
    assert frozen["design"] == design["design"] and frozen["fingerprint"] == FINGERPRINT
    assert frozen["frozen"] == {
        "task": FREEZE_TASK,
        "date": "2026-10-12",
        "candidates": ["coming_short", "support"],
        "code_tree_sha": "a" * 40,
        "candidates_from": {"file": CALIBRATION_IN_REPO, "content_sha256": "b" * 64},
    }
    assert frozen["history"][:-1] == design["history"]
    assert frozen["history"][-1] == {
        "stage": STAGE_FROZEN,
        "task": FREEZE_TASK,
        "date": "2026-10-12",
        "note": FREEZE_NOTE,
    }
    assert "with the real null" in FREEZE_NOTE and "same team sharing t'" in FREEZE_NOTE
    assert [k for k in frozen if k not in design] == ["frozen"]
    with pytest.raises(ValueError, match="only a protocol in stage"):
        freeze_payload(
            frozen,
            candidates=["support"],
            code_tree="a" * 40,
            calibration_sha256="b" * 64,
            date="d",
        )
    with pytest.raises(ValueError, match="candidates"):
        freeze_payload(
            design, candidates=[], code_tree="a" * 40, calibration_sha256="b" * 64, date="d"
        )
    with pytest.raises(ValueError, match="candidates"):
        freeze_payload(
            design, candidates=["nope"], code_tree="a" * 40, calibration_sha256="b" * 64, date="d"
        )
    with pytest.raises(ValueError, match="seal"):
        freeze_payload(
            {**design, "plan": "edited"},
            candidates=["support"],
            code_tree="a" * 40,
            calibration_sha256="b" * 64,
            date="d",
        )
    with pytest.raises(ValueError, match="tree sha"):
        freeze_payload(
            design, candidates=["support"], code_tree="abc", calibration_sha256="b" * 64, date="d"
        )
    assert frozen_problems(frozen, design) == []
    assert "no frozen block" in frozen_problems(
        seal({k: v for k, v in frozen.items() if k != "frozen"}), design
    )
    bad = seal({**frozen, "frozen": {**frozen["frozen"], "candidates": []}})
    assert any("candidates" in p for p in frozen_problems(bad, design))
    bad = seal({**frozen, "frozen": {**frozen["frozen"], "code_tree_sha": "x"}})
    assert any("code_tree_sha" in p for p in frozen_problems(bad, design))


def test_held_out_is_closed_when_frozen_was_flipped_by_hand(repo: Path) -> None:
    """A committed `frozen` with the seal of the design file: the stage string alone opens
    nothing."""
    _commit(repo, {**_design(), "stage": STAGE_FROZEN}, "flipped by hand")
    with pytest.raises(HeldOutLocked, match="content_sha256"):
        load_half("held_out")


def test_held_out_is_closed_when_the_committed_lists_disagree_with_the_rows(repo: Path) -> None:
    """The lists are regenerated from the rows and never trusted: a held-out id moved into the
    committed calibration list, fingerprint and seal recomputed, is refused for both halves."""
    payload = _frozen_here()
    split = payload["design"]["split"]
    split["held_out"].remove(HELD_OUT_MATCH)
    split["calibration"] = sorted([*split["calibration"], HELD_OUT_MATCH])
    payload["fingerprint"] = fingerprint(payload["design"])
    _commit(repo, seal(payload), "doctored lists")
    with pytest.raises(HeldOutLocked, match="regenerate"):
        load_half("calibration")
    with pytest.raises(HeldOutLocked, match="regenerate"):
        load_half("held_out")


def test_the_working_copy_cannot_move_a_match_into_calibration(repo: Path) -> None:
    """What the guard reads is HEAD: the file on disk, with a held-out id added to the
    calibration list, changes nothing."""
    path = _commit(repo, _design(), "protocol in stage design")
    doctored = read_protocol(path)
    doctored["design"]["split"]["calibration"].append(HELD_OUT_MATCH)
    _write(path, doctored)
    assert load_half("calibration") == CALIBRATION
    assert match_halves()[HELD_OUT_MATCH] == "held_out"
    with pytest.raises(HeldOutLocked):
        require_readable(HELD_OUT_MATCH)
    require_readable(CI_FIXTURE_MATCH)
    assert counting_match_ids() == sorted(CALIBRATION + HELD_OUT)


def test_calibration_needs_no_guard() -> None:
    assert load_half("calibration") == CALIBRATION
    assert len(load_half("calibration")) == 10


def test_this_repositorys_head_keeps_the_held_out_closed() -> None:
    """Until task 50 commits the freeze, HEAD's protocol is in design (or absent, before the
    commit of task 47) and the real guard refuses; task 50 rewrites this test."""
    assert head_stage() != STAGE_FROZEN
    with pytest.raises(HeldOutLocked):
        load_half("held_out")


def test_the_split_lists_are_read_only_in_data_and_protocol() -> None:
    """`held_out` and `["split"]` live in `runs/data.py` and `runs/protocol.py` alone, so no
    other module can read a half from a file; `repo_root` in `data.py` alone, and nothing
    under src/ monkeypatches it, the one way to point the guard at another repository. P6's
    guard on 1996435 (`pose/data.py`, task 60) is the one other module allowed `["split"]`
    and `repo_root`, for its own protocol."""
    src = PIPELINE / "src" / "tracklab"
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel not in ("runs/data.py", "runs/protocol.py"):
            assert "held_out" not in text, rel
        if rel not in ("runs/data.py", "runs/protocol.py", "pose/data.py"):
            assert '["split"]' not in text, rel
        if rel not in ("runs/data.py", "pose/data.py"):  # their docstrings name it for tests
            assert "repo_root" not in text, rel
            assert "monkeypatch" not in text, rel
        assert "setattr(" not in text, rel
