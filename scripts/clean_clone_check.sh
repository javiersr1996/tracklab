#!/usr/bin/env bash
# Run the README's "Run from a clean clone" block, as written, in a temporary clone of
# this repository's HEAD, then check that the build left the clone exactly as committed
# (every generated report and doc byte-identical, modulo git's line-ending
# normalization). Prints CLEAN CLONE OK and the total time.
#
#   bash scripts/clean_clone_check.sh                  # downloads both bundles (task 24)
#   bash scripts/clean_clone_check.sh --from-existing  # basketball verified in place (task 16)
#
# --from-existing points the clone's basketball ingest at the outside clone this checkout
# verified in place (its receipt's source_path), so only football is downloaded.
set -euo pipefail

repo=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)
readme="$repo/README.md"
url="https://github.com/javiersr1996/tracklab.git"

from_existing=""
if [[ "${1:-}" == "--from-existing" ]]; then
  receipt="$repo/pipeline/data/raw/opendata-basketball/_receipt.json"
  from_existing=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_path"])' "$receipt")
fi

block=$(sed -n '/<!-- clean-clone:begin -->/,/<!-- clean-clone:end -->/p' "$readme" | sed '/^<!--/d;/^```/d')
if [[ $(grep -c . <<<"$block") -ne 5 ]]; then
  echo "README clean-clone block has $(grep -c . <<<"$block") commands, expected 5" >&2
  exit 1
fi
[[ $block == *"$url"* ]] || { echo "README clean-clone block does not clone $url" >&2; exit 1; }

# The clone comes from this checkout's HEAD, not from GitHub: it checks what is committed.
block=${block//"$url"/"$repo"}
if [[ -n $from_existing ]]; then
  ingest="uv run tracklab ingest opendata-basketball --from-existing '$from_existing'"
  block=$(sed "/^uv sync/a $ingest" <<<"$block")
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
start=$SECONDS
echo "clean clone in $tmp"
(cd "$tmp" && bash -euxo pipefail -c "$block")

changes=$(git -C "$tmp/tracklab" status --porcelain)
if [[ -n $changes ]]; then
  echo "the build changed committed files:" >&2
  echo "$changes" >&2
  exit 1
fi
echo "CLEAN CLONE OK in $((SECONDS - start)) s"
