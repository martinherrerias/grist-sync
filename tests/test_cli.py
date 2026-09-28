from pathlib import Path

from grist_sync.cli import parse_args


def test_parse_args_uses_grist_sync_environment(monkeypatch):
    settings = {
        "GRIST_SYNC_SERVER": "https://grist.example",
        "GRIST_SYNC_API_KEY": ".secrets/test-key",
        "GRIST_SYNC_DOC_ID": "document-id",
        "GRIST_SYNC_TABLE_ID": "Formulas",
        "GRIST_SYNC_OUTDIR": "build/grist",
        "GRIST_SYNC_SOURCE": "formulas",
        "GRIST_SYNC_COLUMN_FILTER": "Revenue|Expenses",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    args = parse_args(["config"])

    assert args.server == settings["GRIST_SYNC_SERVER"]
    assert args.api_key == settings["GRIST_SYNC_API_KEY"]
    assert args.doc == settings["GRIST_SYNC_DOC_ID"]
    assert args.table == settings["GRIST_SYNC_TABLE_ID"]
    assert args.outdir == Path(settings["GRIST_SYNC_OUTDIR"])
    assert args.basedir == Path(settings["GRIST_SYNC_SOURCE"])
    assert args.column_filter == settings["GRIST_SYNC_COLUMN_FILTER"]
