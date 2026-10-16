from glob import glob
from pathlib import Path
from unittest.mock import MagicMock

from grist_sync import OutputName, cli
from grist_sync.cli import main as cli_main
from grist_sync.cli import parse_args


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
    elif endpoint == "tables/Formulas/columns":
        return MagicMock(
            json=lambda: {
                "columns": [
                    {"id": "foo", "fields": {"isFormula": True, "formula": "42"}},
                    {"id": "bar", "fields": {"isFormula": True, "formula": "Bar"}},
                    {"id": "bam", "fields": {"isFormula": False}},
                    {"id": "qux", "fields": {"isFormula": True, "formula": "Qux"}},
                ]
            }
        )
    else:
        raise ValueError(f"Unexpected endpoint: {endpoint}")


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
    assert args.outdir == Path("build/grist/Spoof/Formulas")
    assert args.doc_name == "Spoof"
    assert args.basedir == Path(settings["GRIST_SYNC_SOURCE"])
    assert args.filter == settings["GRIST_SYNC_COLUMN_FILTER"]


def test_pull_formulas(tmp_path, monkeypatch):
    settings = {
        "GRIST_SYNC_SERVER": "https://grist.example",
        "GRIST_SYNC_TABLE_ID": "Formulas",
        "GRIST_SYNC_OUTDIR": tmp_path / "{doc}/{table}",
        "GRIST_SYNC_COLUMN_FILTER": "foo|ba.*",  # should filter out qux
        "GRIST_SYNC_COLUMN_SKIP": "bar",  # should skip bar, leaving only foo
    }

    monkeypatch.setattr(
        cli.GristDocAPI,
        "call",
        _mock_api_call,
    )
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr("sys.argv", ["gr", "pull"])
    cli_main()

    expected_files = [
        OutputName.PULL.get(tmp_path / "Spoof/Formulas", "foo"),
        OutputName.DERENDERED.get(tmp_path / "Spoof/Formulas", "foo"),
    ]
    for f in expected_files:
        assert f.exists(), f"Expected file {f} does not exist"

    should_not_exist = [
        tmp_path / "Spoof/Formulas" / "**/bar.py",
        tmp_path / "Spoof/Formulas" / "**/bam.py",
        tmp_path / "Spoof/Formulas" / "**/qux.py",
    ]
    for f in should_not_exist:
        matches = glob(str(f), recursive=True)
        assert not matches, f"Unexpected file(s) {matches} exist for pattern {f}"
