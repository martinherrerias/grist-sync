from pathlib import Path
from unittest.mock import MagicMock

from grist_sync import cli
from grist_sync.cli import parse_args


def test_parse_args_uses_grist_sync_environment(monkeypatch):
    settings = {
        "GRIST_SYNC_SERVER": "https://grist.example",
        "GRIST_SYNC_API_KEY": ".secrets/test-key",
        "GRIST_SYNC_DOC_ID": "document-id",
        "GRIST_SYNC_TABLE_ID": "Form.*",
        "GRIST_SYNC_OUTDIR": "build/grist/{doc}/{table}",
        "GRIST_SYNC_SOURCE": "formulas",
        "GRIST_SYNC_COLUMN_FILTER": "Revenue|Expenses",
    }

    def _mock_api_call(self, endpoint, *args, **kwargs):
        if endpoint == "":
            return MagicMock(json=lambda: {"name": "Spoof"})
        elif endpoint == "tables":
            return MagicMock(
                json=lambda: {
                    "tables": [
                        {"id": "Formulas"},
                        {"id": "Another_Table"},
                    ]
                }
            )
        else:
            raise ValueError(f"Unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        cli.GristDocAPI,
        "call",
        _mock_api_call,
    )
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    args = parse_args(["config"])

    assert args.server == settings["GRIST_SYNC_SERVER"]
    assert args.api_key == settings["GRIST_SYNC_API_KEY"]
    assert args.doc == settings["GRIST_SYNC_DOC_ID"]
    assert args.table_id == "Formulas"
    assert args.outdir == Path("build/grist/Spoof/Formulas").resolve()
    assert args.doc_name == "Spoof"
    assert args.basedir == Path(settings["GRIST_SYNC_SOURCE"])
    assert args.filter == settings["GRIST_SYNC_COLUMN_FILTER"]
