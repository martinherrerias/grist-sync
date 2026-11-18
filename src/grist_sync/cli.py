"""Command-line tool for synchronizing formulas with a Grist document."""

import os
import sys
from argparse import SUPPRESS, ArgumentParser, RawDescriptionHelpFormatter
from collections.abc import Iterable
from pathlib import Path

import dotenv

from . import OutputName, map, render, sync
from .config import Settings


def parse_args(cli_args: Iterable[str] = ["config"]):

    dotenv.load_dotenv(Path.cwd() / ".env")

    parser = ArgumentParser(prog="gr")
    parser.add_argument(
        "--server",
        default=SUPPRESS,
        help="Grist server URL",
    )
    parser.add_argument(
        "--api-key",
        default=SUPPRESS,
        help="Grist API key or secret file path",
    )
    parser.add_argument(
        "-d",
        "--doc",
        dest="doc_id",
        default=SUPPRESS,
        help="Grist document ID",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=SUPPRESS,
        help="Output directory (default: .grist/{doc}/{table})",
    )
    parser.add_argument(
        "-w",
        "--basedir",
        dest="source",
        type=Path,
        metavar="SOURCE",
        default=SUPPRESS,
        help="Source directory for render (default: formulas)",
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
    _add_map_cmd(subparsers)
    _add_config_cmd(subparsers)

    args = parser.parse_args(cli_args)
    values = vars(args)
    settings = Settings(
        **{name: values.pop(name) for name in Settings.model_fields if name in values}
    )
    values.update(
        settings.model_dump(by_alias=True, exclude={"api_key"}),
        api_key=settings.api_key.get_secret_value(),
        api=settings.api,
        doc_name=settings.doc_name,
    )

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
    cmdparser.set_defaults(handler=sync.pull_formulas)


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
    cmdparser.set_defaults(handler=sync.push_formulas)


def _add_sync_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "sync", help="Pull, render, check for server-side changes, and push"
    )
    _add_cmd_args(cmdparser, True)
    cmdparser.set_defaults(handler=sync.sync)


def _add_map_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "map",
        help="Map columns to other tables (-n: compare only)",
        description="Map TABLE columns to OTHER_TABLES (-n: compare only)",
    )
    _add_cmd_args(cmdparser, True)

    cmdparser.add_argument(
        "-T",
        "--other-tables",
        help="Regex matching tables to compare",
    )
    cmdparser.add_argument(
        "-O",
        "--output",
        default="",
        type=str,
        help=(
            "Optional output CSV file (e.g. '{outdir}_compare.csv'). "
            "If empty (default), results will be printed to stdout."
        ),
    )
    cmdparser.set_defaults(handler=map.main)


def _add_config_cmd(subparsers):
    cmdparser = subparsers.add_parser(
        "config", help="Print parsed settings (for debugging)"
    )
    _add_cmd_args(cmdparser, True)

    def print_args(**args):
        if args["api_key"]:
            args["api_key"] = "*****"
        print(
            "\n".join(
                f"{k}={v}"
                for k, v in args.items()
                if k not in ["handler", "command", "api"]
            )
        )

    cmdparser.set_defaults(handler=print_args)


def _add_cmd_args(parser: ArgumentParser, edit_args=True):

    parser.add_argument(
        "-t",
        "--table",
        dest="table_id",
        default=SUPPRESS,
        help="Grist table ID (can be a regex that matches a single existing table)",
    )
    parser.add_argument(
        "-c",
        "--column-filter",
        dest="column_filter",
        default=SUPPRESS,
        help="Regex filter to select columns / SOURCE files "
        "(case-insensitive), e.g. 'foo|bar', (default: .*)",
    )
    parser.add_argument(
        "-C",
        "--column-skip",
        dest="anti_filter",
        default=os.getenv("GRIST_SYNC_COLUMN_SKIP", ""),
        help="Regex filter to skip columns / SOURCE files",
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
        "--dryrun",
        action="store_true",
        help="Do not actually push data",
    )


def main():
    args = parse_args(sys.argv[1:])
    args.handler(**vars(args))


if __name__ == "__main__":
    main()
