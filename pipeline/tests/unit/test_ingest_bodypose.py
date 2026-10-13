"""Task 57: freeze and ingest of the HuggingFace body-pose dataset, against a fake HF served by
httpx.MockTransport. No network. The two zips are fabricated (three JSON lines each); the real
sizes and sha256 are checked against SkillCorner's own MANIFEST.json, kept as a fixture."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from tracklab.build import bytes_read
from tracklab.dagster_defs import defs
from tracklab.ingest.fetch import (
    IntegrityError,
    download_verified,
    freeze_source,
    ingest_source,
    make_client,
)
from tracklab.ingest.manifest import Source, load_manifest, match_id_for, role_for

REPO = "SkillCorner/opendata-bodypose"
REVISION = "a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "bodypose"
REAL_MANIFEST = Path(__file__).resolve().parents[2] / "manifest" / "sources.json"
LINES = [b'{"frame": 0}', b'{"frame": 1}', b'{"frame": 2}']


def make_zip(match_id: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{match_id}.jsonl", b"\n".join(LINES) + b"\n")
    return buffer.getvalue()


ZIPS = {f"raw/{m}.jsonl.zip": make_zip(m) for m in (1925299, 1996435)}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeHub:
    """huggingface.co: revision and tree APIs (tree paginated by a Link header) and resolve."""

    def __init__(self) -> None:
        self.zips = dict(ZIPS)
        self.auth_seen: list[str | None] = []
        self.tree_pages = 0

    def client(self) -> httpx.Client:
        return make_client(httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.auth_seen.append(request.headers.get("Authorization"))
        assert url.host == "huggingface.co", f"unexpected host {url.host}"
        if url.path == f"/api/datasets/{REPO}/revision/main":
            return httpx.Response(200, json={"sha": REVISION})
        if url.path == f"/api/datasets/{REPO}/tree/{REVISION}":
            self.tree_pages += 1
            first = [
                {"type": "directory", "path": "raw", "size": 0},
                {"type": "file", "path": "README.md", "size": 6408, "oid": "x"},
            ]
            lfs = [
                {
                    "type": "file",
                    "path": path,
                    "size": len(body),
                    "lfs": {"oid": sha256(body), "size": len(body)},
                }
                for path, body in self.zips.items()
            ]
            if url.params.get("page") == "2":
                return httpx.Response(200, json=lfs)
            next_url = f"https://huggingface.co{url.path}?recursive=1&page=2"
            return httpx.Response(200, json=first, headers={"Link": f'<{next_url}>; rel="next"'})
        prefix = f"/datasets/{REPO}/resolve/{REVISION}/"
        if url.path.startswith(prefix) and url.path.removeprefix(prefix) in self.zips:
            return httpx.Response(200, content=self.zips[url.path.removeprefix(prefix)])
        return httpx.Response(404, text=f"not found: {url}")


def unfrozen() -> Source:
    base = f"https://huggingface.co/datasets/{REPO}/resolve/{{commit}}/"
    return Source(
        "opendata-bodypose", "football", "huggingface", REPO, "main", None, "MIT", base, base, []
    )


@pytest.fixture
def hub() -> FakeHub:
    return FakeHub()


@pytest.fixture
def frozen(hub: FakeHub) -> Source:
    with hub.client() as client:
        return freeze_source(client, unfrozen(), log=lambda _: None)


def test_freeze_reads_sizes_and_oids_from_the_tree_without_a_download(
    hub: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    logs: list[str] = []
    with hub.client() as client:
        result = freeze_source(client, unfrozen(), log=logs.append)
    assert result.commit == REVISION
    assert logs == ["skipped: README.md (no role in the bundle)"]
    assert hub.tree_pages == 2, "the Link header must be followed"
    assert [(f.path, f.bytes, f.sha256, f.lfs, f.role, f.match_id) for f in result.files] == [
        (path, len(body), sha256(body), True, "bodypose_zip", int(path[4:11]))
        for path, body in sorted(ZIPS.items())
    ]
    assert hub.auth_seen and all(a is None for a in hub.auth_seen), "no token goes to HF"


def test_real_manifest_pins_what_skillcorner_publishes() -> None:
    published = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    source = load_manifest(REAL_MANIFEST).source("opendata-bodypose")
    assert source.kind == "huggingface" and source.license == "MIT"
    assert source.commit == REVISION
    assert [(f.path, f.bytes, f.sha256) for f in source.files] == [
        (path, meta["size_bytes"], meta["sha256"])
        for path, meta in sorted(published["files"].items())
    ]
    assert [f.bytes for f in source.files] == [623_408_231, 644_327_811]
    assert all(f.lfs and f.role == "bodypose_zip" for f in source.files)


def test_hf_fixtures_have_the_sizes_the_plan_names() -> None:
    assert (FIXTURES / "README.hf.md").stat().st_size == 6408
    assert (FIXTURES / "MANIFEST.json").stat().st_size == 1278


def test_role_and_match_id_of_a_zip() -> None:
    assert role_for("raw/1925299.jsonl.zip") == "bodypose_zip"
    assert match_id_for("raw/1925299.jsonl.zip") == 1925299
    assert role_for("raw/1925299.jsonl") is None
    assert role_for("data/raw/1925299.jsonl.zip") is None


def test_ingest_downloads_verifies_and_is_idempotent(
    hub: FakeHub, frozen: Source, tmp_path: Path
) -> None:
    with hub.client() as client:
        first = ingest_source(client, frozen, tmp_path / "raw", log=lambda _: None)
        assert first.summary == "downloaded=2 verified=2 failed=0"
        for path, body in ZIPS.items():
            assert (tmp_path / "raw" / path).read_bytes() == body
        second = ingest_source(client, frozen, tmp_path / "raw", log=lambda _: None)
    assert second.summary == "downloaded=0 verified=2 failed=0"
    assert not list((tmp_path / "raw").rglob("*.part"))


def test_a_wrong_sha_ends_in_integrity_error_and_failed_1(
    hub: FakeHub, frozen: Source, tmp_path: Path
) -> None:
    entry = frozen.files[0]
    entry.sha256 = ("0" if entry.sha256[0] != "0" else "1") + entry.sha256[1:]
    with hub.client() as client:
        with pytest.raises(IntegrityError):
            download_verified(client, frozen.lfs_url_for(entry.path), tmp_path / "x.zip", entry)
        receipt = ingest_source(client, frozen, tmp_path / "raw", log=lambda _: None)
    assert receipt.failed == [entry.path]
    assert receipt.summary == "downloaded=1 verified=1 failed=1"
    assert not (tmp_path / "raw" / entry.path).exists()


def test_bytes_read_of_a_zip_is_the_uncompressed_size_not_the_zip(tmp_path: Path) -> None:
    payload = b"0123456789" * 5000
    path = tmp_path / "1.jsonl.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("1.jsonl", payload)
    assert path.stat().st_size < len(payload) // 10
    assert bytes_read(path) == len(payload)


def test_the_bodypose_asset_is_named_by_source_and_the_others_keep_their_names() -> None:
    graph = defs.resolve_asset_graph()
    names = {key.to_user_string() for key in graph.get_all_asset_keys()}
    assert {"raw_football", "raw_basketball", "raw_football_bodypose"} <= names
