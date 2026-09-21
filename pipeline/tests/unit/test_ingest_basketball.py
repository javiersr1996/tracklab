"""freeze_local and ingest_local: opendata-basketball's `--from-existing` path.

Basketball's raw bytes already live in a git clone outside this repo, so
there is no network fixture here (contrast test_ingest.py's FakeGitHub):
most tests build a small from-scratch git repo in tmp_path, shaped like the
real bundle including an LFS pointer whose worktree copy is later swapped
for its "real" bytes, exactly like git-lfs's smudge filter would leave it.
The last test is a contract check against the actual clone this task was
built against, skipped if that clone is not present on the machine.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tracklab.cli import main
from tracklab.ingest.fetch import RECEIPT_NAME
from tracklab.ingest.lfs import parse_pointer
from tracklab.ingest.local import freeze_local, ingest_local
from tracklab.ingest.manifest import (
    Manifest,
    Source,
    load_manifest,
    match_id_for,
    role_for,
    save_manifest,
)

REAL_CLONE = Path(
    r"C:\Users\javie\Desktop\proyectos\skillcorner_basket_data\data\raw\opendata-basketball"
)
REAL_MANIFEST = Path(__file__).resolve().parents[2] / "manifest" / "sources.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True)
    return result.stdout


def unfrozen_source() -> Source:
    repo = "SkillCorner/opendata-basketball"
    return Source(
        source_id="opendata-basketball",
        sport="basketball",
        kind="github",
        repo=repo,
        ref="main",
        commit=None,
        license="MIT",
        raw_url=f"https://raw.githubusercontent.com/{repo}/{{commit}}/",
        lfs_url=f"https://media.githubusercontent.com/media/{repo}/{{commit}}/",
        files=[],
    )


# --- role patterns (manifest.py) -----------------------------------------------------


@pytest.mark.parametrize(
    ("path", "role", "match_id"),
    [
        ("data/matches/114243/114243_tracking_data.jsonl.gz", "tracking", 114243),
        ("data/matches/114243/114243_game_data.json", "game_data", 114243),
        ("data/matches/114243/114243_dynamic_events.json", "events", 114243),
        ("data/aggregates/acb_drivesaggregates_20252026.csv", "aggregate", None),
        ("data/matches.json", "matches", None),
        ("data/player_id_aliases.csv", "player_aliases", None),
    ],
)
def test_basketball_role_patterns(path: str, role: str, match_id: int | None) -> None:
    assert role_for(path) == role
    assert match_id_for(path) == match_id


def test_docs_and_top_level_files_have_no_role() -> None:
    assert role_for("docs/data_dictionary/shots.md") is None
    assert role_for("README.md") is None
    assert role_for("data/unknown_extra.txt") is None  # inside data/, but nothing claims it


# --- a from-scratch local clone, no network, no real repo -----------------------------

TRACKING = "data/matches/999001/999001_tracking_data.jsonl.gz"
GAME_DATA = "data/matches/999001/999001_game_data.json"
EVENTS = "data/matches/999001/999001_dynamic_events.json"
MATCHES_JSON = "data/matches.json"
ALIASES = "data/player_id_aliases.csv"
AGGREGATE = "data/aggregates/acb_drivesaggregates_20252026.csv"
UNKNOWN = "data/unknown_extra.txt"  # inside data/, no role: must be skipped and logged
TRACKING_BLOB = b"fake gzip bytes for one match, big enough to not look like a pointer" * 20

SMALL_FILES: dict[str, bytes] = {
    GAME_DATA: b'{"gameId": 999001, "homeTeam": {"name": "Test"}}',
    EVENTS: b'{"passes": [], "shots": []}',
    MATCHES_JSON: b'[\n  {"id": 999001}\n]\n',
    ALIASES: b"player_id,alias_player_id\n1,1\n",
    AGGREGATE: b"player_id,total_drives\n1,4\n",
    UNKNOWN: b"not part of the bundle\n",
}
BUNDLE_SIZE = 6  # tracking + game_data + events + matches + aliases + aggregate


def pointer_for(blob: bytes) -> bytes:
    return (
        f"version https://git-lfs.github.com/spec/v1\noid sha256:{sha256(blob)}\nsize {len(blob)}\n"
    ).encode()


@pytest.fixture
def basketball_clone(tmp_path: Path) -> Path:
    """A git repo shaped like the real basketball bundle.

    The tracking file is committed as an LFS pointer, then overwritten on disk
    with its "real" bytes without touching git again: that gap between the git
    object and the worktree is exactly what git-lfs's smudge filter produces,
    and is what freeze_local/ingest_local must handle without ever calling it.
    core.autocrlf is pinned to false so the fixture is not at the mercy of
    whatever this machine's global git config happens to be (see the real
    clone's matches.json/aggregates/player_id_aliases.csv, which needed the
    same fix: autocrlf silently rewrites multi-line non-LFS text files on
    checkout, which is exactly the kind of thing sha256 verification must
    catch, not paper over).
    """
    repo = tmp_path / "clone"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    _git("config", "core.autocrlf", "false", cwd=repo)

    for path, content in SMALL_FILES.items():
        dest = repo / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    (repo / "README.md").write_text("outside data/, must not even be considered\n")
    (repo / TRACKING).parent.mkdir(parents=True, exist_ok=True)
    (repo / TRACKING).write_bytes(pointer_for(TRACKING_BLOB))

    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "seed", cwd=repo)

    (repo / TRACKING).write_bytes(TRACKING_BLOB)  # simulate git-lfs's smudge
    return repo


def test_freeze_local_reads_pointer_and_hashes_small_files(basketball_clone: Path) -> None:
    logs: list[str] = []
    frozen = freeze_local(basketball_clone, unfrozen_source(), log=logs.append)

    commit = _git("rev-parse", "HEAD", cwd=basketball_clone).strip()
    assert frozen.commit == commit
    assert len(frozen.files) == BUNDLE_SIZE
    assert logs == [f"skipped: {UNKNOWN} (no role in the bundle)"]

    by_path = {f.path: f for f in frozen.files}
    tracking = by_path[TRACKING]
    assert (tracking.lfs, tracking.bytes, tracking.sha256, tracking.role, tracking.match_id) == (
        True,
        len(TRACKING_BLOB),
        sha256(TRACKING_BLOB),
        "tracking",
        999001,
    )
    game_data = by_path[GAME_DATA]
    assert (game_data.lfs, game_data.bytes, game_data.sha256, game_data.role) == (
        False,
        len(SMALL_FILES[GAME_DATA]),
        sha256(SMALL_FILES[GAME_DATA]),
        "game_data",
    )
    assert {f.role for f in frozen.files} == {
        "tracking",
        "game_data",
        "events",
        "matches",
        "player_aliases",
        "aggregate",
    }


def test_ingest_local_verifies_in_place_and_records_source_path(
    basketball_clone: Path, tmp_path: Path
) -> None:
    frozen = freeze_local(basketball_clone, unfrozen_source(), log=lambda _: None)
    receipt_root = tmp_path / "data" / "raw" / "opendata-basketball"

    receipt = ingest_local(frozen, basketball_clone, receipt_root)

    assert (receipt.verified, receipt.downloaded, receipt.failed) == (BUNDLE_SIZE, 0, [])
    assert receipt.source_path == str(basketball_clone)
    saved = json.loads((receipt_root / RECEIPT_NAME).read_text())
    assert saved["source_path"] == str(basketball_clone)
    assert [p.name for p in receipt_root.iterdir()] == [RECEIPT_NAME], "nothing was copied"


def test_ingest_local_reports_a_mutated_file(basketball_clone: Path, tmp_path: Path) -> None:
    frozen = freeze_local(basketball_clone, unfrozen_source(), log=lambda _: None)
    receipt_root = tmp_path / "data" / "raw" / "opendata-basketball"
    target = basketball_clone / GAME_DATA
    target.write_bytes(target.read_bytes() + b"\ncorrupted")

    logs: list[str] = []
    receipt = ingest_local(frozen, basketball_clone, receipt_root, log=logs.append)

    assert receipt.failed == [GAME_DATA]
    assert receipt.verified == BUNDLE_SIZE - 1
    assert f"failed: {GAME_DATA}" in logs


def test_ingest_local_refuses_unfrozen_source(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not frozen"):
        ingest_local(unfrozen_source(), tmp_path, tmp_path)


# --- CLI wiring: --from-existing on both freeze and ingest ---------------------------


def test_cli_freeze_and_ingest_from_existing(
    basketball_clone: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "sources.json"
    save_manifest(Manifest(schema_version=1, sources=[unfrozen_source()]), manifest_path)

    rc = main(
        [
            "freeze",
            "opendata-basketball",
            "--manifest",
            str(manifest_path),
            "--from-existing",
            str(basketball_clone),
        ]
    )
    assert rc == 0
    freeze_out = capsys.readouterr().out.splitlines()[-1]
    assert freeze_out.startswith("commit=")
    assert f"files={BUNDLE_SIZE} lfs=1" in freeze_out

    rc = main(
        [
            "ingest",
            "opendata-basketball",
            "--manifest",
            str(manifest_path),
            "--data-dir",
            str(tmp_path / "data"),
            "--from-existing",
            str(basketball_clone),
        ]
    )
    assert rc == 0
    assert (
        capsys.readouterr().out.splitlines()[-1] == f"downloaded=0 verified={BUNDLE_SIZE} failed=0"
    )


# --- contract: the manifest's tracking sha256 match fresh git cat-file, on the real clone


@pytest.mark.skipif(
    not REAL_CLONE.is_dir(), reason=f"real basketball clone not present at {REAL_CLONE}"
)
def test_contract_tracking_sha256_matches_git_cat_file_pointers() -> None:
    """The 10 sha256 the manifest carries for basketball tracking files must be
    exactly the ``oid`` of the LFS pointer git has at HEAD, read fresh with
    ``git cat-file``, independent of whatever freeze_local itself computed."""
    source = load_manifest(REAL_MANIFEST).source("opendata-basketball")
    tracking = sorted((f for f in source.files if f.role == "tracking"), key=lambda f: f.path)
    assert len(tracking) == 10

    print(f"\n{'match_id':>10}  {'manifest sha256':<64}  {'git cat-file oid':<64}")
    mismatches = []
    for entry in tracking:
        content = subprocess.run(
            ["git", "cat-file", "-p", f"HEAD:{entry.path}"],
            cwd=REAL_CLONE,
            capture_output=True,
            check=True,
        ).stdout
        pointer = parse_pointer(content)
        assert pointer is not None, f"{entry.path} is not an LFS pointer at HEAD"
        print(f"{entry.match_id:>10}  {entry.sha256}  {pointer.oid}")
        if pointer.oid != entry.sha256:
            mismatches.append(entry.path)

    assert mismatches == []
