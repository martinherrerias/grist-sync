"""
Tools to pull, check for server-side changes, and push formulas
"""

import re
import subprocess
from pathlib import Path

from grist_api import GristDocAPI

from . import OutputName
from .render import grist_to_local
from .render import main as render


def main(args):

    if args.operation == "pull" or not args.dry_run:
        args.outdir.mkdir(parents=True, exist_ok=True)

    api = GristDocAPI(args.doc, api_key=args.api_key, server=args.server)

    if args.operation == "sync":
        render(args)

    if args.operation == "pull":
        pull_formulas(
            api,
            table_id=args.table,
            outdir=args.outdir,
            filter=args.column_filter,
        )
    elif args.operation in ["push", "sync"]:
        push_formulas(
            api,
            table_id=args.table,
            basedir=args.basedir,
            outdir=args.outdir,
            filter=args.column_filter,
            force=args.force,
            dry_run=args.dry_run,
        )
    else:
        raise ValueError(f"Unknown operation: {args.operation}")


def _filter_columns(columns, filter=None) -> list[str]:

    col_ids = [c["id"] for c in columns]
    if not filter or filter == ".*":
        return col_ids
    return [c for c in col_ids if re.search(filter, c, flags=re.IGNORECASE)]


def pull_formulas(api, table_id, outdir, filter=None, col_ids=None):

    columns = api.call(f"tables/{table_id}/columns").json()["columns"]
    if col_ids is None:
        col_ids = _filter_columns(columns, filter)
        if not col_ids:
            print(f"No columns found in {table_id} matching filter '{filter}'")
            return

    assert outdir.is_dir()
    for col_id in col_ids:
        try:
            formula = get_formula(columns, col_id)
        except ValueError as exc:
            print(f"Skipping column '{col_id}': {exc}")
            continue

        out_file = OutputName.PULL.get(outdir, col_id)
        out_file.write_text(formula)

        dr_file = OutputName.DERENDERED.get(outdir, col_id)
        dr_formula = grist_to_local(formula)
        dr_file.write_text(dr_formula)

        print(f"Wrote '{col_id}' formula to {out_file}\n  and rendered to {dr_file}")


def push_formulas(
    api, table_id, basedir, outdir, filter=None, force=False, dry_run=False
):
    assert outdir.is_dir()
    prefix = OutputName.RENDER.value
    keys = [f.name[:-3] for f in outdir.glob(prefix + "*.py")]
    if filter and filter != ".*":
        keys = [k for k in keys if re.search(filter, k, flags=re.IGNORECASE)]

    if not keys:
        print(f"No renderd files found in {outdir} matching filter '{filter}'")
        return

    columns = api.call(f"tables/{table_id}/columns").json()["columns"]
    col_map = _file_column_map(outdir, keys, columns)

    problems = []
    for file, col_id in col_map.items():
        formula = file.read_text()
        try:
            # make sure not to overwrite server-side changes
            check_for_changes(columns, col_id, outdir, basedir)

            # make sure not to push "dirty" tags
            tag = check_git_tag(formula, basedir)
            status = f"@ {tag}"

        except ValueError as exc:
            if not force:
                print(f"Aborting push of '{col_id}': {exc}")
                problems.append(col_id)
                continue
            else:
                status = f"ignoring ERROR: {exc}"

        if dry_run:
            print(f"Dry-run: would push formula for '{col_id}' {status}")
            continue

        try:
            set_formula(api, table_id, col_id, formula)
            print(f"Pushed '{col_id}' formula from {file} {status}")
        except Exception as exc:  # noqa: BLE001
            problems.append(col_id)
            print(f"Failed to push '{col_id}' formula: {exc}")

    if problems:
        print(
            f"\nFailed to push {len(problems)} of {len(col_map)} formulas: "
            f"{', '.join(problems)}. \nUse --force to override and push anyway"
        )

    pull_formulas(api, table_id, outdir, col_ids=col_map.values())


def _file_column_map(outdir: Path, keys: list[str], columns) -> dict[Path, str]:

    cols = {}
    for k in keys:
        f = OutputName.RENDER.get(outdir, k)
        try:
            cols[f] = next(c["id"] for c in columns if (c["id"].lower() == k.lower()))
        except StopIteration:
            cols[f] = k
    return cols


def get_formula(columns, col_id):

    try:
        col = next(c for c in columns if c["id"] == col_id)
    except StopIteration:
        raise ValueError(f"Failed to find column with ID: '{col_id}'")

    if not col["fields"]["isFormula"]:
        raise ValueError(f"Column: '{col_id}' is not a formula")

    return col["fields"]["formula"]


def set_formula(api, table_id, col_id, formula):

    payload = {
        "columns": [
            {
                "id": col_id,
                "fields": {
                    "formula": formula,
                },
            }
        ]
    }
    api.call(f"tables/{table_id}/columns", payload, "PATCH")


def check_git_tag(formula: str, basedir: Path) -> str:
    """Try return git rev-parse TAG for TAG in header # git@TAG"""
    match = re.search(r"^# git@(\S+).*", formula, flags=re.MULTILINE)
    if not match:
        raise ValueError("Formula does not have a git@TAG")
    tag = match.group(1)

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", tag],
            cwd=basedir,
            check=True,
            capture_output=True,
        )
        tag = out.stdout.decode().strip()
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        raise ValueError(f"Unknown git tag '{tag}'")

    return tag


def check_for_changes(columns, col_id, outdir: Path, basedir: Path):
    """
    Verify formula for COL_ID has not been changed through the UI

    Checks that local `git show TAG:FILE` contents match the reported
    git@TAG in the remote formula header.
    """

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=basedir,
            check=True,
            capture_output=True,
        )
        git_root = Path(out.stdout.decode().strip())
        prefix = basedir.resolve().relative_to(git_root)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Not a git repository? '({basedir})': {exc}")

    formula = get_formula(columns, col_id)
    try:
        tag = check_git_tag(formula, git_root)
        src = prefix / (col_id.lower() + ".py")
        out = subprocess.run(
            ["git", "show", f"{tag}:{src}"],
            cwd=git_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Failed to parse git tag for '{col_id}': {exc}")

    old_script = out.stdout.decode()
    formula = grist_to_local(formula)

    if old_script != formula:
        old = OutputName.OLD.get(outdir, col_id)
        old.write_text(old_script)
        pull = OutputName.PULL.get(outdir, col_id)
        pull.write_text(formula)
        raise ValueError(f"Formula has changed since {tag}. Check: diff {old} {pull}")
