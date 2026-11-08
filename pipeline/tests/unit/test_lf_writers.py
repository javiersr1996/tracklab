"""Every text the pipeline writes is LF (P18, task 147).

Windows `Path.write_text` turns "\n" into "\r\n" unless `newline="\n"` is given, and `csv` ends rows
with "\r\n" unless `lineterminator` is: the same bytes then differ between the Windows laptop and
the Linux runner, and `git status` shows files that did not change. The bytes written are checked
for the two CSV reports; a scan of the source checks the rest, so a new writer cannot forget.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tracklab.formats import basketball, football_report

PIPELINE = Path(__file__).resolve().parents[2]
SCANNED = (PIPELINE / "src", PIPELINE / "tests" / "contracts")


def test_the_csv_reports_are_written_with_lf(tmp_path: Path) -> None:
    basket = tmp_path / "basketball.csv"
    basketball.write_report_csv([dict.fromkeys(basketball.REPORT_COLUMNS, "x")] * 2, basket)
    football = tmp_path / "football.csv"
    football_report.write_report_csv([{"a": 1, "b": None}, {"a": 2, "b": "y"}], football)

    for path in (basket, football):
        data = path.read_bytes()
        assert data.endswith(b"\n")
        assert b"\r" not in data, path.name


def _calls_without_lf(path: Path) -> list[str]:
    bad = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        keywords = {k.arg for k in node.keywords}
        text_write = name == "write_text" and "newline" not in keywords
        csv_write = name in {"DictWriter", "writer"} and "lineterminator" not in keywords
        if text_write or csv_write:
            bad.append(f"{path.relative_to(PIPELINE)}:{node.lineno} {name}")
    return bad


def test_no_writer_leaves_the_line_ending_to_the_platform() -> None:
    bad = [
        line
        for root in SCANNED
        for path in sorted(root.rglob("*.py"))
        for line in _calls_without_lf(path)
    ]
    assert bad == []
