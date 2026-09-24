"""``raw_<sport>``: the provider's bytes, verified against the manifest.

Same two paths as ``tracklab ingest``: download and verify, or verify in place
inside an outside clone. Which one is decided by the previous receipt, so a
machine that ingested with ``--from-existing`` keeps doing it without a flag.
"""

# No `from __future__ import annotations`: Dagster reads the `context` hint at runtime.
import json
from pathlib import Path

from dagster import AssetExecutionContext, AssetsDefinition, AssetSpec, Failure, asset

from tracklab.ingest.fetch import RECEIPT_NAME, ingest_source, make_client
from tracklab.ingest.local import ingest_local
from tracklab.ingest.manifest import Source, load_manifest
from tracklab.paths import data_root

MANIFEST = Path("manifest/sources.json")

# The manifest is edited by `tracklab freeze`, not built here: a spec, not a step.
manifest_sources = AssetSpec(
    "manifest_sources",
    group_name="ingest",
    description="manifest/sources.json: each source's repo, pinned commit, files and sha256.",
)


def _previous_source_path(receipt_root: Path) -> Path | None:
    receipt_path = receipt_root / RECEIPT_NAME
    if not receipt_path.is_file():
        return None
    source_path = json.loads(receipt_path.read_text(encoding="utf-8")).get("source_path")
    return Path(source_path) if source_path else None


def _raw_asset(source: Source) -> AssetsDefinition:
    @asset(
        name=f"raw_{source.sport}",
        group_name="ingest",
        deps=[manifest_sources],
        description=f"{source.source_id}, every manifest file with the right sha256.",
    )
    def _raw(context: AssetExecutionContext) -> None:
        frozen = load_manifest(MANIFEST).source(source.source_id)
        receipt_root = data_root() / "raw" / source.source_id
        existing = _previous_source_path(receipt_root)
        if existing is not None:
            receipt = ingest_local(frozen, existing, receipt_root, log=context.log.info)
        else:
            with make_client() as client:
                receipt = ingest_source(client, frozen, receipt_root, log=context.log.info)
        context.log.info(receipt.summary)
        if receipt.failed:
            raise Failure(receipt.summary)
        context.add_output_metadata(
            {"verified": receipt.verified, "downloaded": receipt.downloaded}
        )

    return _raw


raw_assets = [_raw_asset(source) for source in load_manifest(MANIFEST).sources]
