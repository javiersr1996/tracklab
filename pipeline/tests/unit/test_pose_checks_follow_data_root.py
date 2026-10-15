"""Every `--check` of P6 follows `data_root()` (task 64).

With `TRACKLAB_DATA_ROOT` on an empty directory no bronze, raw or sample is under the root, so
each check can only verify the versioned files and says so: `PARTIAL 0/n`. A route that read a
fixed `data/` instead would find the machine's own bronze and say `FULL`, or find nothing and
fail: either way this test fails. The synthetic tests of P6 (the sweep, the gait estimator, the
criteria) read no data and run in the pytest of CI as they are.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tracklab.cli import main

CHECKS = [
    (["pose", "coverage", "--check"], "PARTIAL 0/2"),
    (["pose", "protocol", "--check"], "PARTIAL 0/2"),
    (["pose", "metric", "--check"], "PARTIAL 0/2"),
    (["publish", "pose", "--check"], "PARTIAL 0/3"),
]


@pytest.mark.parametrize(("argv", "expected"), CHECKS, ids=[" ".join(c[0][:2]) for c in CHECKS])
def test_a_check_on_an_empty_data_root_says_partial_and_passes(
    argv: list[str],
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("TRACKLAB_DATA_ROOT", str(empty))
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert expected in out, out
    assert "FULL" not in out, out
