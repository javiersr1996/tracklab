"""The queries of "Run it here" (task 86, `tracklab.learn.browser`), on the published files.

`web/public/data` is in git, so these run on the real files everywhere, CI included. The two
mutations of the plan are tests here: a wrong coefficient of the closed form changes lesson 1's
g past its tolerance, and a view on a file the lesson does not declare is caught before the
browser's `allowed_paths` would refuse it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tracklab.learn.browser import (
    EXPECT,
    LESSONS,
    compare,
    parse,
    read,
    run,
    run_learn_browser,
    undeclared,
)

PUBLIC = Path(__file__).resolve().parents[3] / "web" / "public"


def test_every_query_agrees_with_the_published_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_learn_browser(PUBLIC, check=True) == 0
    assert f"FULL {len(LESSONS)}/{len(LESSONS)}" in capsys.readouterr().out


@pytest.mark.parametrize("slug", LESSONS)
def test_each_lesson_compares_at_least_one_row_with_its_files(slug: str) -> None:
    sql = read(slug)
    assert sql.files and undeclared(sql) == []
    rows = run(sql, PUBLIC)
    expected = EXPECT[slug](PUBLIC)
    assert expected and set(expected) <= set(rows)
    assert compare(rows, expected) == []


def test_a_wrong_coefficient_of_the_closed_form_fails() -> None:
    sql = read("gravity")
    assert sql.query.count("-2 * sum(") == 1
    wrong = parse(
        (Path(__file__).resolve().parents[2] / "src" / "tracklab" / "learn" / "gravity.browser.sql")
        .read_text("utf-8")
        .replace("-2 * sum(", "-1 * sum(")
    )
    problems = compare(run(wrong, PUBLIC), EXPECT["gravity"](PUBLIC))
    assert [p.split(":")[0] for p in problems] == ["learn.fit_g"]


def test_a_view_on_an_undeclared_file_is_caught() -> None:
    text = (
        "-- files: /data/learn/speed.json\n"
        "CREATE VIEW a AS SELECT * FROM read_json('/data/learn/speed.json');\n"
        "CREATE VIEW b AS SELECT * FROM read_json('/data/quality.json');\n"
        "SELECT 'x' AS figure, '1' AS value\n"
    )
    assert undeclared(parse(text)) == ["/data/quality.json"]


def test_the_file_must_be_views_then_one_query() -> None:
    with pytest.raises(ValueError):
        parse("-- files: /data/a.json\nSELECT 1;\nSELECT 2\n")
    with pytest.raises(ValueError):
        parse("CREATE VIEW a AS SELECT 1;\nSELECT 2\n")
    sql = parse("-- files: /data/a.json\nCREATE VIEW a AS SELECT 1;\nSELECT 2;\n")
    assert (sql.files, len(sql.views), sql.query) == (["/data/a.json"], 1, "SELECT 2")
