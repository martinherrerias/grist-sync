"""Compare columns of several tables against a template table."""

import csv
import shutil
import tempfile
from enum import Enum
from pathlib import Path

from grist_api import GristDocAPI

from .sync import _filter_columns

type TableID = str
type ColID = str
type Formula = str | None


class ColumnMatch(Enum):
    DATA = "D"  # do not check contents
    FORMULA_MATCH = "✓"
    FORMULA_MISMATCH = "✗"
    MISSING = "-"


def column_formulas(columns, filter=None) -> dict[ColID, Formula]:
    """Map column ID -> formula (None for data columns), for columns matching FILTER."""
    wanted = set(_filter_columns(columns, filter))
    return {
        c["id"]: (c["fields"].get("formula") or "")
        if c["fields"].get("isFormula")
        else None
        for c in columns
        if c["id"] in wanted
    }


def classify(
    template: dict[ColID, Formula], other: dict[ColID, Formula], col_id: ColID
) -> ColumnMatch:
    if col_id not in other:
        return ColumnMatch.MISSING
    formula = other[col_id]
    if formula is None:
        return ColumnMatch.DATA
    reference = template.get(col_id)
    if reference is not None and reference.strip() == formula.strip():
        return ColumnMatch.FORMULA_MATCH
    return ColumnMatch.FORMULA_MISMATCH


def build_rows(columns: dict[TableID, dict[ColID, Formula]], template_id: TableID):
    template = columns[template_id]
    col_ids = sorted({c for t in columns.values() for c in t})
    for col_id in col_ids:
        yield [col_id] + [
            classify(template, cols, col_id).value for cols in columns.values()
        ]


def main(
    api: GristDocAPI,
    table_id: TableID,
    other_tables: list[TableID],
    output: Path,
    filter: str | None = None,
    **kwargs,
) -> None:
    template_id = table_id
    others = set(other_tables) - {template_id}
    if not others:
        raise ValueError(f"No other tables selected for comparison with {template_id}")
    picks = [template_id] + sorted(others)

    columns: dict[TableID, dict[ColID, Formula]] = {
        t: column_formulas(api.call(f"tables/{t}/columns").json()["columns"], filter)
        for t in picks
    }

    output = Path(str(output).format(table=template_id))
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpfile = Path(tmpdir) / output.name
        with open(tmpfile, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["COL_ID"] + picks)
            writer.writerows(build_rows(columns, template_id))
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmpfile, output)
    print(f"Compared {len(picks)} tables to {template_id}: {output}")
