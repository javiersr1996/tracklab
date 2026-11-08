"""TRACKLAB_REQUIRE_DATA (P18, task 146): in full-build a skip for missing data is a failure.

Runs pytest on a throwaway tree with a copy of tests/conftest.py, so the hook is tested the way it
runs: through the plugin, on a real skip.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
SKIPPED = (
    'import pytest\n\n@pytest.mark.skipif(True, reason="data not built")\ndef test_x():\n    pass\n'
)


def _run(tmp_path: Path, folder: str, require: str | None) -> subprocess.CompletedProcess[str]:
    tests = tmp_path / "tests"
    (tests / folder).mkdir(parents=True)
    shutil.copy(CONFTEST, tests / "conftest.py")
    (tests / folder / "test_x.py").write_text(SKIPPED, encoding="utf-8", newline="\n")
    env = {"PATH": "", "SYSTEMROOT": "C:/Windows"}
    if require is not None:
        env["TRACKLAB_REQUIRE_DATA"] = require
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(tests), "-q", "-p", "no:cacheprovider", "-rs"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("folder", ["contracts", "publish"])
def test_a_data_skip_fails_when_the_data_is_required(tmp_path: Path, folder: str) -> None:
    result = _run(tmp_path, folder, "1")
    assert result.returncode == 1, result.stdout
    assert "data not built" in result.stdout
    assert "TRACKLAB_REQUIRE_DATA is set" in result.stdout
    assert "1 skipped" not in result.stdout


@pytest.mark.parametrize("require", [None, "", "0", "false"])
def test_a_data_skip_stays_a_skip_when_the_data_is_not_required(
    tmp_path: Path, require: str | None
) -> None:
    result = _run(tmp_path, "contracts", require)
    assert result.returncode == 0, result.stdout
    assert "1 skipped" in result.stdout


def test_a_skip_outside_the_data_folders_stays_a_skip(tmp_path: Path) -> None:
    result = _run(tmp_path, "postgres", "1")
    assert result.returncode == 0, result.stdout
    assert "1 skipped" in result.stdout
