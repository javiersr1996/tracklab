"""euroleague sweep on a synthetic download and a synthetic web/: a planted UTC must fail it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracklab import cli
from tracklab.euroleague.sweep import run_euroleague_sweep, signatures

# Three field goals and a free throw, each with its UTC, its coordinates and its NUM_ANOT.
SHOTS = (
    {"NUM_ANOT": 7, "ID_ACTION": "2FGM", "COORD_X": -312, "COORD_Y": 415, "UTC": "20250101120000"},
    {"NUM_ANOT": 18, "ID_ACTION": "3FGA", "COORD_X": 641, "COORD_Y": -207, "UTC": "20250101120001"},
    {"NUM_ANOT": 33, "ID_ACTION": "2FGA", "COORD_X": 150, "COORD_Y": 233, "UTC": "20250101120002"},
)
FREE_THROW = {
    "NUM_ANOT": 9,
    "ID_ACTION": "FTM       ",
    "COORD_X": -1,
    "COORD_Y": -1,
    "UTC": "20250101129999",
}
PUBLISHED = Path(__file__).resolve().parents[3] / "web" / "public" / "data" / "euroleague"


@pytest.fixture
def data(tmp_path: Path) -> Path:
    season = tmp_path / "data" / "euroleague" / "raw" / "E2025"
    (season / "Points").mkdir(parents=True)
    rows = [*SHOTS, FREE_THROW]
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


def test_the_signatures_are_every_utc_and_the_triple_of_each_field_goal(data: Path) -> None:
    sig = signatures(data / "euroleague" / "raw", ["E2025"])
    assert sig.utcs == {s["UTC"].encode() for s in (*SHOTS, FREE_THROW)}
    assert sig.shots == len(SHOTS)  # the free throw has no place on the court
    assert (-312, 415, 7) in sig.orderings and (7, 415, -312) in sig.orderings


def test_a_clean_build_passes(data: Path, web: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sweep(data, web) == 0
    out = capsys.readouterr().out
    assert "FULL 4 UTC and 3 shot triples" in out and "3 files" in out and "0 hits" in out


def _plant(web: Path, where: str, text: str) -> None:
    (web / where).parent.mkdir(parents=True, exist_ok=True)
    (web / where).write_text(text, "utf-8")


@pytest.mark.parametrize(
    ("where", "text"),
    [
        ("public/data/euroleague/teams/AAA.json", f'{{"UTC":"{SHOTS[0]["UTC"]}"}}'),
        (".next/static/chunks/page.js", f"var t={SHOTS[1]['UTC']};"),
        (".next/server/app/page.js", f"x9{SHOTS[2]['UTC']}7"),  # inside a longer run of digits
        (
            "out/static/page.js.map",
            f'{{"sourcesContent":["{SHOTS[0]["UTC"]}"]}}',
        ),  # a map elsewhere
        ("public/ft.json", FREE_THROW["UTC"]),  # every row's UTC, not a sample
    ],
)
def test_a_real_utc_fails(
    data: Path, web: Path, where: str, text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(web, where, text)
    assert _sweep(data, web) == 1
    assert f"hit: {where}" in capsys.readouterr().out


def test_a_raw_row_fails(data: Path, web: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _plant(web, "public/data/row.json", json.dumps(SHOTS[2]))
    assert _sweep(data, web) == 1
    assert "hit: public/data/row.json" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        '{"x":-312,"y":415,"n":7}',  # renamed keys, no UTC
        "const s={n:7,x:-312,y:415,made:true};",  # a minified object, anot first
        "[-312,415,7]",
        "[415,-312,7,1]",
        "[[1,2,3],[7,-312,415]]",
        "-312,415,7\n",  # a CSV line
        "x;y;n\n641;-207;18\n",
    ],
)
def test_the_coordinates_and_number_of_a_shot_fail_without_its_utc(
    data: Path, web: Path, text: str
) -> None:
    _plant(web, "public/data/copy.json", text)
    assert _sweep(data, web) == 1


def test_a_whole_points_file_fails(
    data: Path, web: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = (data / "euroleague" / "raw" / "E2025" / "Points" / "1.json").read_text("utf-8")
    _plant(web, ".next/static/chunks/points.js", f"export default {raw}")
    assert _sweep(data, web) == 1
    assert "hit: .next/static/chunks/points.js" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        "[150,233,7]",  # a pair of coordinates with another shot's number
        "[0,0,7]",  # the hoop: coordinates too small to tell a shot from a count
        "[1,2,3,4,5,-312,415,7]",  # a series of samples, not a record
        '{"a":-312,"b":9,"c":415,"d":7}',  # not side by side
        "-312, 415",
    ],
)
def test_what_is_not_a_shot_does_not_fail(data: Path, web: Path, text: str) -> None:
    _plant(web, "public/data/other.json", text)
    assert _sweep(data, web) == 0


@pytest.mark.skipif(not PUBLISHED.is_dir(), reason="no published aggregates in this checkout")
def test_the_published_aggregates_do_not_fail(data: Path, web: Path) -> None:
    for path in PUBLISHED.rglob("*.json"):
        target = web / "public" / "data" / "euroleague" / path.relative_to(PUBLISHED)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    assert _sweep(data, web) == 0


def test_what_is_not_swept(data: Path, web: Path) -> None:
    (web / "node_modules" / "x").mkdir(parents=True)
    (web / "node_modules" / "x" / "a.js.map").write_text(SHOTS[0]["UTC"], "utf-8")
    assert _sweep(data, web) == 0


def test_in_the_compilers_cache_only_a_utc_fails(data: Path, web: Path) -> None:
    # Its logs list file numbers, where three in a row match a shot by chance; a UTC does not.
    _plant(web, ".next/cache/turbopack/v1/LOG", "| 00000007 -312 415 META DELETED\n")
    assert _sweep(data, web) == 0
    _plant(web, ".next/cache/turbopack/v1/LOG", f"| {SHOTS[0]['UTC']} META\n")
    assert _sweep(data, web) == 1
    _plant(web, ".next/cache/turbopack/v1/LOG", "")
    _plant(web, ".next/server/LOG", "| 00000007 -312 415 META DELETED\n")
    assert _sweep(data, web) == 1


def test_a_binary_file_is_not_read_for_shots(data: Path, web: Path) -> None:
    (web / "public" / "a.wasm").write_bytes(b"\x00asm[-312,415,7]")
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
