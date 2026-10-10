"""Command-line tool for synchronizing formulas with a Grist document."""

import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from collections.abc import Iterable
from pathlib import Path

import dotenv
from grist_api import GristDocAPI

from . import OutputName, render, sync


def parse_args(args: Iterable[str] | None = None):

    dotenv.load_dotenv(Path.cwd() / ".env")

    parser = ArgumentParser(prog="gr")
    parser.add_argument(
        "--server",
        default=os.getenv("GRIST_SYNC_SERVER", "https://docs.getgrist.com"),
        help="Grist server URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("GRIST_SYNC_API_KEY", ".secrets/.grist-api-key"),
        help="Grist API key or secret file path",
    )
    parser.add_argument(
        "-d",
        "--doc",
        default=os.getenv("GRIST_SYNC_DOC_ID"),
        help="Grist document ID",
    )
    parser.add_argument(
        "-t",
        "--table",
        default=os.getenv("GRIST_SYNC_TABLE_ID", "RUC"),
        help="Grist table ID",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=Path(os.getenv("GRIST_SYNC_OUTDIR", ".grist")),
        help="Output directory (default: %(default)s)",
    )
    parser.add_argument(
        "-w",
        "--basedir",
        type=Path,
        metavar="SOURCE",
        default=Path(os.getenv("GRIST_SYNC_SOURCE", "./formulas")),
        help="Source directory for render (default: %(default)s)",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Use `gr <command> --help` for more information",
    )
    _add_render_cmd(subparsers)
    _add_pull_cmd(subparsers)
    _add_push_cmd(subparsers)
    _add_sync_cmd(subparsers)
    _add_config_cmd(subparsers)

    args = parser.parse_args(args)

    if os.path.isfile(args.api_key):
        with open(args.api_key) as f:
            args.api_key = f.read().strip()

    api = GristDocAPI(args.doc, api_key=args.api_key, server=args.server)
    args.doc_name = api.call("").json()["name"]

    args.outdir = Path(
        str(args.outdir).format(doc=args.doc_name, table=args.table)
    ).resolve()

    return args


def _add_render_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "render",
        help=f"Render SOURCE/*.py files to {OutputName.RENDER.value}*.py files",
        # description="Render Grist-specific code blocks in source files",
        epilog=render.__doc__,
        formatter_class=RawDescriptionHelpFormatter,
    )
    _add_cmd_args(cmdparser, False)
    cmdparser.set_defaults(handler=render.main)


def _add_pull_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "pull",
        help="Pull (and reverse-render) formulas from Grist DOC/TABLE "
        f"to {OutputName.PULL.value}*.py files",
    )
    _add_cmd_args(cmdparser, False)
    cmdparser.set_defaults(handler=sync.main, operation="pull")


def _add_push_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "push",
        help="Check server changes and push rendered files to Grist",
        description="Check server changes and push rendered files to Grist",
        epilog=(
            "Unless --force is used, push checks for server-side changes "
            "and aborts if any are found."
        ),
    )
    _add_cmd_args(cmdparser, True)
    cmdparser.set_defaults(handler=sync.main, operation="push")


def _add_sync_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "sync", help="Pull, render, check for server-side changes, and push"
    )
    _add_cmd_args(cmdparser, True)
    cmdparser.set_defaults(handler=sync.main, operation="sync")


def _add_config_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "config", help="Print parsed settings (for debugging)"
    )
    _add_cmd_args(cmdparser, True)

    def print_args(args):
        if (
            args.api_key
            and args.api_key != ".secrets/.grist-api-key"
            and not Path(args.api_key).is_file()
        ):
            args.api_key = "*****"
        print(
            "\n".join(
                f"{k}={v}"
                for k, v in vars(args).items()
                if k not in ["handler", "command"]
            )
        )

    cmdparser.set_defaults(handler=print_args)


def _add_cmd_args(parser: ArgumentParser, edit_args=True):

    parser.add_argument(
        "-c",
        "--column-filter",
        default=os.getenv("GRIST_SYNC_COLUMN_FILTER", ".*"),
        help="Regex filter to select columns / SOURCE files "
        "(case-insensitive), e.g. 'foo|bar', (default: %(default)s)",
    )
    if not edit_args:
        return

    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force push data even if there are conflicts",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Do not actually push data",
    )


def main():
    args = parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
