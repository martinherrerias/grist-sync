from grist_sync.map import (
    ColumnMatch,
    build_rows,
    classify,
    column_formulas,
    plan_update,
)


def col(id, formula=None):
    return {"id": id, "fields": {"isFormula": formula is not None, "formula": formula}}


def test_column_formulas_keeps_data_columns_and_applies_filter():
    cols = [col("A", "1"), col("B"), col("C", "3")]
    assert column_formulas(cols, {"A", "B", "C"}) == {"A": "1", "B": None, "C": "3"}
    assert column_formulas(cols, {"A"}) == {"A": "1"}


def test_classify_and_rows():
    tmpl = {"A": "1", "B": None, "C": "3"}
    other = {"A": "1\n", "B": "2", "C": "4", "D": None}
    assert classify(tmpl, other, "A") is ColumnMatch.FORMULA_MATCH
    assert classify(tmpl, other, "B") is ColumnMatch.FORMULA_MISMATCH
    assert classify(tmpl, other, "C") is ColumnMatch.FORMULA_MISMATCH
    assert classify(tmpl, other, "D") is ColumnMatch.DATA
    assert classify(tmpl, {}, "A") is ColumnMatch.MISSING
    rows = list(build_rows({"T": tmpl, "O": other}, "T"))
    assert rows[0] == ["A", "√", "√"]
    assert rows[3] == ["D", "-", "D"]


def test_classify_ignores_comment_header():
    tmpl: dict[str, str | None] = {"A": "1", "B": ""}
    other: dict[str, str | None] = {"A": "# comment\n1", "B": "# comment"}
    assert classify(tmpl, other, "A") is ColumnMatch.FORMULA_MATCH
    assert classify(tmpl, other, "B") is ColumnMatch.FORMULA_MATCH


def test_labels_column():
    labels = {"T": {"A": "Alpha"}, "O": {"A": "Beta", "B": "Bee"}}
    cols = {"T": {"A": "1"}, "O": {"A": "1", "B": None}}
    rows = list(build_rows(cols, "T", labels))
    assert rows == [["A", "√", "√", "Alpha | Beta"], ["B", "-", "D", "Bee"]]


def test_plan_update_is_safe():
    assert plan_update("1", None, force=True) is None  # data column
    assert plan_update("1", "# c\n1") is None  # already matches
    assert plan_update("1", "") == "1"  # empty target
    assert plan_update("1", "2") is None  # needs --force
    assert plan_update("1", "2\n\n3", force=True) == "# 2\n#\n# 3\n1"
    assert plan_update("", "2", force=True) is None
    assert plan_update("1", "# x = 1\n\nx = 1\n", force=True) == "# x = 1\n\n# x = 1\n1"
    assert plan_update("1", "# hdr\n", force=True) == "# hdr\n1"
