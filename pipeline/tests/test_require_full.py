"""TRACKLAB_REQUIRE_FULL (task 96): in full-build a `--check` that says PARTIAL must fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from tracklab import cli


def _says(verdict: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> int:
        print(f"learn speed --check: {verdict}")
        return 0

    monkeypatch.setattr(cli, "run_learn_speed", run)


@pytest.mark.parametrize(
    "verdict",
    [
        "PARTIAL 0/10: raw files not at hand",
        "football FULL 10/10; basketball PARTIAL 0/10",
        "PARTIAL: frames not at hand",
    ],
)
def test_partial_fails_when_full_is_required(
    verdict: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _says(verdict, monkeypatch)
    monkeypatch.setenv(cli.REQUIRE_FULL, "1")
    assert cli.main(["learn", "speed", "--check"]) == 1
    captured = capsys.readouterr()
    assert verdict in captured.out  # the verdict still reaches the log
    assert "PARTIAL" in captured.err


def test_partial_stays_green_when_full_is_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _says("PARTIAL 0/10: raw files not at hand", monkeypatch)
    monkeypatch.delenv(cli.REQUIRE_FULL, raising=False)
    assert cli.main(["learn", "speed", "--check"]) == 0


def test_full_passes_when_full_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _says(
        "FULL 10/10: the bytes of speed.json rebuilt from bronze (never PARTIAL here)", monkeypatch
    )
    monkeypatch.setenv(cli.REQUIRE_FULL, "1")
    assert cli.main(["learn", "speed", "--check"]) == 0


@pytest.mark.parametrize("value", ["", "0", "false", "False", " FALSE "])
def test_an_empty_zero_or_false_value_is_off(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """full-build sets the variable to "" for the pytest step, and "0" or "false" mean the same."""
    _says("PARTIAL 0/10: raw files not at hand", monkeypatch)
    monkeypatch.setenv(cli.REQUIRE_FULL, value)
    assert not cli.require_full()
    assert cli.main(["learn", "speed", "--check"]) == 0


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_any_other_value_is_on(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _says("PARTIAL 0/10: raw files not at hand", monkeypatch)
    monkeypatch.setenv(cli.REQUIRE_FULL, value)
    assert cli.require_full()
    assert cli.main(["learn", "speed", "--check"]) == 1


def test_only_require_full_reads_the_variable() -> None:
    """The Dagster assets and the CLI must agree on what "on" is: one function reads it."""
    src = Path(cli.__file__).parent
    readers = [
        path.relative_to(src).as_posix()
        for path in sorted(src.rglob("*.py"))
        if "environ.get(REQUIRE_FULL" in path.read_text(encoding="utf-8")
        or 'environ.get("TRACKLAB_REQUIRE_FULL"' in path.read_text(encoding="utf-8")
    ]
    assert readers == ["cli.py"]
