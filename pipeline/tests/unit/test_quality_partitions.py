"""`tracklab quality partitions` on fabricated versions of the four source
artefacts: `reports/football_format.csv` (task 4), bronze basketball
`tracking_frames` (task 5, no report of its own -- see `quality.partitions`'s
module docstring for why it is read from bronze instead), and
`reports/orientation_football.csv` (tasks 7 and 9).

Two football matches: one where `players_last_modified` and `attack_median_m`
agree (both "exact"), one deliberately made to disagree, so the
`partitions_agree` metric and the mutation below both have something to catch.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from tracklab.quality import partitions
from tracklab.quality.common import report_path
from tracklab.quality.run import run_quality

FOOTBALL_FORMAT_COLUMNS = ("match_id", "n_frames", "frames_outside_periods")
ORIENTATION_COLUMNS = ("match_id", "players_last_modified", "attack_median_m", "pp_matched")


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _write_basketball_frames(data_dir: Path, rows: dict[int, int]) -> None:
    """`rows`: native match id -> number of frames dropped out of a span of 1,000."""
    con = duckdb.connect()
    con.execute("CREATE TABLE frames (match_id BIGINT, frameIdx BIGINT)")
    values = []
    for native, missing in rows.items():
        present = [f for f in range(1000) if f >= missing]  # drop the first `missing` frames
        values += [(native, f) for f in present]
    literal = ", ".join(repr(v) for v in values)
    con.execute(f"INSERT INTO frames VALUES {literal}")
    path = data_dir / "bronze" / "basketball" / "tracking_frames"
    path.mkdir(parents=True)
    for native in rows:
        con.execute(
            f"COPY (SELECT * FROM frames WHERE match_id = {native}) "
            f"TO '{(path / f'{native}.parquet').as_posix()}'"
        )


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], dict[str, float]]:
    root = tmp_path_factory.mktemp("partitions")
    reports = root / "reports"
    # Football layout: match 10 has heavy out-of-period footage (well above the
    # 1,000-frame threshold), match 11 only a normal kickoff pause.
    _write_csv(
        reports / "football_format.csv",
        FOOTBALL_FORMAT_COLUMNS,
        [(10, 60000, 12000), (11, 59000, 20)],
    )
    # Orientation: match 10 agrees on both paths (exact); match 11 is engineered
    # to disagree, so `partitions_agree` has a real 0 to report.
    _write_csv(
        reports / "orientation_football.csv",
        ORIENTATION_COLUMNS,
        [(10, "yes", 0.0, 500), (11, "yes", 0.2, 500)],
    )
    # Basketball frame loss: match 900 drops 5% of a 1,000-frame span (well above
    # the 0.5% threshold), match 901 drops 0.1% (well below it).
    _write_basketball_frames(root / "data", {900: 50, 901: 1})
    assert run_quality(["partitions"], data_dir=root / "data", reports_dir=reports) == 0
    with report_path(reports, "partitions").open(encoding="utf-8", newline="") as handle:
        out: dict[tuple[str, str], dict[str, float]] = {}
        for r in csv.DictReader(handle):
            out.setdefault((r["sport"], r["match_id"]), {})[r["metric"]] = float(r["value"])
        return out


def test_football_layout_splits_on_the_frames_outside_periods_gap(
    report: dict[tuple[str, str], dict[str, float]],
) -> None:
    assert report[("football", "fb:10")]["layout_extra_footage"] == 1.0
    assert report[("football", "fb:11")]["layout_extra_footage"] == 0.0


def test_basketball_frame_loss_splits_on_the_measured_gap(
    report: dict[tuple[str, str], dict[str, float]],
) -> None:
    assert report[("basketball", "bb:900")]["frame_loss_pct"] == pytest.approx(5.0, abs=1e-6)
    assert report[("basketball", "bb:900")]["frame_loss_regime_high"] == 1.0
    assert report[("basketball", "bb:901")]["frame_loss_pct"] == pytest.approx(0.1, abs=1e-6)
    assert report[("basketball", "bb:901")]["frame_loss_regime_high"] == 0.0


def test_the_two_football_paths_agree_and_disagree_as_engineered(
    report: dict[tuple[str, str], dict[str, float]],
) -> None:
    m10, m11 = report[("football", "fb:10")], report[("football", "fb:11")]
    assert m10["players_last_modified"] == 1.0
    assert m10["event_coords_exact"] == 1.0
    assert m10["partitions_agree"] == 1.0
    assert m11["players_last_modified"] == 1.0
    assert m11["event_coords_exact"] == 0.0  # attack_median_m = 0.2, above the threshold
    assert m11["partitions_agree"] == 0.0


def test_both_paths_agree_on_every_match_of_the_real_bundle() -> None:
    """The property task 9 measured: in the real 20-match bundle, `players_last_modified`
    and `attack_median_m` always land on the same side. Skipped if the report this
    task depends on is not present (a fresh checkout that has not run `orientation` yet)."""
    real_reports = Path(__file__).resolve().parents[2] / "reports"
    path = real_reports / "orientation_football.csv"
    if not path.is_file():
        pytest.skip("reports/orientation_football.csv not built in this checkout")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 20
    for row in rows:
        players_flag = row["players_last_modified"] == "yes"
        event_flag = float(row["attack_median_m"]) < partitions.FOOTBALL_EVENT_COORD_THRESHOLD
        assert players_flag == event_flag, row["match_id"]


def test_lowering_the_frame_loss_threshold_flips_the_low_loss_match(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: match 901 drops exactly 0.1% of its frames. Lowering
    `BASKETBALL_FRAME_LOSS_THRESHOLD` below that flips its regime flag -- proof
    the flag is actually read off the threshold, not hard-coded."""
    root = tmp_path_factory.mktemp("partitions_mutated")
    _write_basketball_frames(root / "data", {901: 1})
    monkeypatch.setattr(partitions, "BASKETBALL_FRAME_LOSS_THRESHOLD", 0.05)

    results = partitions._basketball_frame_loss(root / "data")
    by_metric = {r.metric: r.value for r in results if r.match_id == "bb:901"}
    assert by_metric["frame_loss_regime_high"] == 1.0
