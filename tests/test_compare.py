from grist_sync.compare import (
    ColumnMatch,
    build_rows,
    classify,
    column_formulas,
)


def col(id, formula=None):
    return {"id": id, "fields": {"isFormula": formula is not None, "formula": formula}}


def test_column_formulas_keeps_data_columns_and_applies_filter():
    cols = [col("A", "1"), col("B"), col("C", "3")]
    assert column_formulas(cols) == {"A": "1", "B": None, "C": "3"}
    assert column_formulas(cols, "^a") == {"A": "1"}


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


def test_labels_column():
    labels = {"T": {"A": "Alpha"}, "O": {"A": "Beta", "B": "Bee"}}
    cols = {"T": {"A": "1"}, "O": {"A": "1", "B": None}}
    rows = list(build_rows(cols, "T", labels))
    assert rows == [["A", "√", "√", "Alpha | Beta"], ["B", "-", "D", "Bee"]]
