from pathlib import Path
from unittest.mock import MagicMock

from grist_sync import cli
from grist_sync.cli import parse_args


def test_parse_args_uses_grist_sync_environment(monkeypatch):
    settings = {
        "GRIST_SYNC_SERVER": "https://grist.example",
        "GRIST_SYNC_API_KEY": ".secrets/test-key",
        "GRIST_SYNC_DOC_ID": "document-id",
        "GRIST_SYNC_TABLE_ID": "Formulas",
        "GRIST_SYNC_OUTDIR": "build/grist/{doc}/{table}",
        "GRIST_SYNC_SOURCE": "formulas",
        "GRIST_SYNC_COLUMN_FILTER": "Revenue|Expenses",
    }
    monkeypatch.setattr(
        cli.GristDocAPI,
        "call",
        lambda *a, **k: MagicMock(json=lambda: {"name": "Spoof"}),
    )
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    args = parse_args(["config"])

    assert args.server == settings["GRIST_SYNC_SERVER"]
    assert args.api_key == settings["GRIST_SYNC_API_KEY"]
    assert args.doc == settings["GRIST_SYNC_DOC_ID"]
    assert args.table == settings["GRIST_SYNC_TABLE_ID"]
    assert args.outdir == Path("build/grist/Spoof/Formulas").resolve()
    assert args.doc_name == "Spoof"
    assert args.basedir == Path(settings["GRIST_SYNC_SOURCE"])
    assert args.column_filter == settings["GRIST_SYNC_COLUMN_FILTER"]
