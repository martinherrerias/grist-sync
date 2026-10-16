"""Compare columns of several tables against a template table."""

import csv
import re
import shutil
import tempfile
from enum import Enum
from pathlib import Path

from grist_api import GristDocAPI

from .sync import _filter_names, set_formula

type TableID = str
type ColID = str
type Formula = str | None


class ColumnMatch(Enum):
    DATA = "D"  # do not check contents
    FORMULA_MATCH = "√"
    FORMULA_MISMATCH = "X"
    MISSING = "-"


def column_formulas(columns, wanted: set[str]) -> dict[ColID, Formula]:
    """Map column ID -> formula (None for data columns), for columns in WANTED."""
    return {
        c["id"]: (c["fields"].get("formula") or "")
        if c["fields"].get("isFormula")
        else None
        for c in columns
        if c["id"] in wanted
    }


def column_labels(columns, wanted: set[str]) -> dict[ColID, str]:
    """Map column ID -> label, for columns in WANTED."""
    return {
        c["id"]: c["fields"].get("label") or "" for c in columns if c["id"] in wanted
    }


_COMMENT_HEADER_RE = re.compile(r"\A(?:\s*(?:#[^\n]*)?)*")


def normalize_formula(formula: str) -> str:
    """Strip leading comment/blank lines and surrounding whitespace."""
    formula = formula.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "  ")
    formula = re.sub(r" +$", "", formula, flags=re.MULTILINE)
    return _COMMENT_HEADER_RE.sub("", formula).strip()


def classify(
    template: dict[ColID, Formula], other: dict[ColID, Formula], col_id: ColID
) -> ColumnMatch:
    if col_id not in other:
        return ColumnMatch.MISSING
    formula = other[col_id]
    if formula is None:
        return ColumnMatch.DATA
    reference = template.get(col_id)
    if reference is not None and normalize_formula(reference) == normalize_formula(
        formula
    ):
        return ColumnMatch.FORMULA_MATCH
    return ColumnMatch.FORMULA_MISMATCH


def comment_out(formula: str) -> str:
    return "\n".join(f"# {line}".rstrip() for line in formula.splitlines())


def plan_update(reference: Formula, current: Formula, force: bool = False) -> Formula:
    """
    Return the new formula for a target column, or None if it must be left alone.

    Data columns (current is None) are never modified, matching formulas are
    skipped, and non-empty targets are only replaced with FORCE, keeping the
    old formula as a comment above the new one.
    """
    if current is None or reference is None:
        return None
    new = normalize_formula(reference)
    old = normalize_formula(current)
    if not new or new == old:
        return None
    if old and not force:
        return None
    body = current.rstrip()
    header = body[: len(body) - len(old)]
    kept = header + comment_out(old) if old else body
    return f"{kept}\n{reference.strip()}" if kept else reference.strip()


def build_rows(
    columns: dict[TableID, dict[ColID, Formula]],
    template_id: TableID,
    labels: dict[TableID, dict[ColID, str]] | None = None,
):
    """Yield [col_id, *match symbols per table, (labels used across tables)]."""
    template = columns[template_id]
    col_ids = sorted({c for t in columns.values() for c in t})
    for col_id in col_ids:
        row = [col_id] + [
            classify(template, cols, col_id).value for cols in columns.values()
        ]
        if labels is not None:
            used = {t[col_id] for t in labels.values() if t.get(col_id)}
            row.append(" | ".join(sorted(used)))
        yield row


def main(
    api: GristDocAPI,
    table_id: TableID,
    other_tables: list[TableID],
    output: Path | None,
    filter: str | None = None,
    anti_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    **kwargs,
) -> None:

    template_id = table_id
    others = set(other_tables) - {template_id}
    if not others:
        raise ValueError(f"No other tables selected for comparison with {template_id}")
    picks = [template_id] + sorted(others)

    raw = {t: api.call(f"tables/{t}/columns").json()["columns"] for t in picks}
    col_ids = {c["id"] for cols in raw.values() for c in cols}
    col_ids = set(_filter_names(col_ids, filter, anti_filter))

    columns: dict[TableID, dict[ColID, Formula]] = {
        t: column_formulas(cols, col_ids) for t, cols in raw.items()
    }
    labels = {t: column_labels(cols, col_ids) for t, cols in raw.items()}

    if not dry_run:
        template = columns[template_id]
        for t in sorted(others):
            for col_id, current in columns[t].items():
                new = plan_update(template.get(col_id), current, force)
                if new is None:
                    continue
                set_formula(api, t, col_id, new)
                columns[t][col_id] = new
                print(f"Updated {t}.{col_id}" + (" (forced)" if current.strip() else ""))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpfile = Path(tmpdir) / "grist-sync-map.csv"
        with open(tmpfile, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["col_id"] + picks + ["labels"])
            writer.writerows(build_rows(columns, template_id, labels))

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tmpfile, output)
            print(f"Compared {len(others)} tables to {template_id}: {output}")
        else:
            with open(tmpfile) as f:
                print(f.read())
