"""Smoke test: tracklab must be importable and its CLI must expose all subcommands."""

import tracklab
from tracklab.cli import build_parser


def test_import() -> None:
    assert tracklab.__version__


def test_cli_lists_five_subcommands() -> None:
    help_text = build_parser().format_help()
    for name in ("ingest", "freeze", "bronze", "publish", "stats"):
        assert name in help_text
