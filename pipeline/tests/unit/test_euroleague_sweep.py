"""euroleague sweep on a synthetic download and a synthetic web/: a planted UTC must fail it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracklab import cli
from tracklab.euroleague.sweep import run_euroleague_sweep, signatures

UTCS = ("20250101120000", "20250101120001", "20250101120002")
FREE_THROW_UTC = "20250101129999"


@pytest.fixture
def data(tmp_path: Path) -> Path:
    season = tmp_path / "data" / "euroleague" / "raw" / "E2025"
    (season / "Points").mkdir(parents=True)
    rows = [{"NUM_ANOT": i, "ID_ACTION": "2FGA", "UTC": utc} for i, utc in enumerate(UTCS, start=1)]
    rows.append({"NUM_ANOT": 9, "ID_ACTION": "FTM       ", "UTC": FREE_THROW_UTC})
    (season / "Points" / "1.json").write_text(json.dumps({"Rows": rows}), "utf-8")
    manifest = {"games": [{"gamecode": 1, "files": {"Points": "Points/1.json"}}]}
    (season / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return tmp_path / "data"


@pytest.fixture
def web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    for name, text in {
        ".next/static/chunks/app.js": "const a=1;",
        ".next/static/chunks/app.js.map": '{"mappings":"AAAA"}',
        "public/data/euroleague/league.json": '{"cells":[[0,0,200,101,202]]}',
        "next.config.ts": "const nextConfig: NextConfig = {};\n",
    }.items():
        (web / name).parent.mkdir(parents=True, exist_ok=True)
        (web / name).write_text(text, "utf-8")
    return web


def _sweep(data: Path, web: Path) -> int:
    return run_euroleague_sweep(data, web, ["E2025"])


def test_the_sample_is_the_field_goals_with_a_fixed_seed(data: Path) -> None:
    raw = data / "euroleague" / "raw"
    assert sorted(signatures(raw, ["E2025"])) == sorted(UTCS)
    assert signatures(raw, ["E2025"], sample=2) == signatures(raw, ["E2025"], sample=2)
    assert len(signatures(raw, ["E2025"], sample=2)) == 2


def test_a_clean_build_passes(data: Path, web: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sweep(data, web) == 0
    out = capsys.readouterr().out
    assert "FULL 3 signatures" in out and "3 files" in out and "0 hits" in out


@pytest.mark.parametrize(
    ("where", "text"),
    [
        ("public/data/euroleague/teams/AAA.json", f'{{"UTC":"{UTCS[0]}"}}'),
        (".next/static/chunks/page.js", f"var t={UTCS[1]};"),
        (".next/server/app/page.js", f"x9{UTCS[2]}7"),  # inside a longer run of digits
        ("out/static/page.js.map", f'{{"sourcesContent":["{UTCS[0]}"]}}'),  # a map elsewhere
    ],
)
def test_a_real_signature_fails(
    data: Path, web: Path, where: str, text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (web / where).parent.mkdir(parents=True, exist_ok=True)
    (web / where).write_text(text, "utf-8")
    assert _sweep(data, web) == 1
    assert f"hit: {where}" in capsys.readouterr().out


def test_what_is_not_swept(data: Path, web: Path) -> None:
    (web / "node_modules" / "x").mkdir(parents=True)
    (web / "node_modules" / "x" / "a.js.map").write_text(UTCS[0], "utf-8")
    (web / "public" / "ft.json").write_text(FREE_THROW_UTC, "utf-8")  # not in the sample
    assert _sweep(data, web) == 0


def test_browser_source_maps_fail(data: Path, web: Path) -> None:
    (web / "next.config.ts").write_text(
        "const nextConfig: NextConfig = { productionBrowserSourceMaps: true };\n", "utf-8"
    )
    assert _sweep(data, web) == 1


def test_no_build_is_partial(data: Path, web: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for path in sorted((web / ".next").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (web / ".next").rmdir()
    assert _sweep(data, web) == 0
    assert "PARTIAL:" in capsys.readouterr().out


def test_no_data_is_partial_and_fails_when_full_is_required(
    tmp_path: Path, web: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["euroleague", "sweep", "--data-dir", str(tmp_path / "none"), "--web-dir", str(web)]
    monkeypatch.delenv(cli.REQUIRE_FULL, raising=False)
    assert cli.main(argv) == 0
    assert "PARTIAL:" in capsys.readouterr().out
    monkeypatch.setenv(cli.REQUIRE_FULL, "1")
    assert cli.main(argv) == 1
