import os
from glob import glob
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from grist_sync import OutputName, config
from grist_sync.cli import parse_args


@pytest.fixture
def setup_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in os.environ:
        if name.startswith("GRIST_SYNC_"):
            monkeypatch.delenv(name)
    (tmp_path / ".secrets").mkdir()

    calls = []

    def mock_api(doc, api_key, server, **kwargs):
        calls.append((doc, api_key, server))
        api = MagicMock()

        def call(endpoint):
            if endpoint == "":
                response = {"name": "Spoof"}
            elif endpoint == "tables":
                response = {"tables": [{"id": "Formulas"}, {"id": "Another_Table"}]}
            elif endpoint == "tables/Formulas/columns":
                response = {
                    "columns": [
                        {
                            "id": "foo",
                            "fields": {"isFormula": True, "formula": "42"},
                        },
                        {
                            "id": "bar",
                            "fields": {"isFormula": True, "formula": "Bar"},
                        },
                        {"id": "bam", "fields": {"isFormula": False}},
                        {
                            "id": "qux",
                            "fields": {"isFormula": True, "formula": "Qux"},
                        },
                    ]
                }
            else:
                raise ValueError(f"Unexpected endpoint: {endpoint}")
            return MagicMock(status_code=HTTPStatus.OK, json=lambda: response)

        api.call.side_effect = call
        return api

    monkeypatch.setattr(config, "GristDocAPI", mock_api)
    return calls


def test_parse_args_uses_grist_sync_environment(monkeypatch, setup_cli):
    settings = {
        "GRIST_SYNC_SERVER": "https://grist.example",
        "GRIST_SYNC_API_KEY": "verysecret",
        "GRIST_SYNC_DOC_ID": "document-id",
        "GRIST_SYNC_TABLE_ID": "Form.*",
        "GRIST_SYNC_OUTDIR": "build/grist/{doc}/{table}",
        "GRIST_SYNC_SOURCE": "formulas",
        "GRIST_SYNC_COLUMN_FILTER": "Revenue|Expenses",
    }

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
    assert not {"doc_id", "source", "column_filter"} & vars(args).keys()
    assert setup_cli == [("document-id", "verysecret", "https://grist.example")]


def test_cli_overrides_environment_and_dotenv(monkeypatch, tmp_path, setup_cli):
    (tmp_path / ".env").write_text(
        "GRIST_SYNC_DOC_ID=dotenv-doc\nGRIST_SYNC_TABLE_ID=Another_Table\n"
        "GRIST_SYNC_API_KEY=dotenv-key\nGRIST_SYNC_SOURCE=dotenv-source\n"
    )
    monkeypatch.setenv("GRIST_SYNC_DOC_ID", "env-doc")
    monkeypatch.setenv("GRIST_SYNC_TABLE_ID", "Form.*")

    args = parse_args(
        ["--doc", "cli-doc", "--basedir", "cli-source", "config", "-t", "another"]
    )

    assert args.doc == "cli-doc"
    assert args.table_id == "Another_Table"
    assert args.basedir == Path("cli-source")
    assert args.api_key == "dotenv-key"
    assert args.outdir == Path(".grist/Spoof/Another_Table")
    assert setup_cli == [("cli-doc", "dotenv-key", "https://docs.getgrist.com")]


def test_secret_files_and_config_output(monkeypatch, tmp_path, setup_cli, capsys):
    (tmp_path / ".secrets" / "GRIST_SYNC_API_KEY").write_text("file-secret\n")
    monkeypatch.setenv("GRIST_SYNC_DOC_ID", "doc")
    monkeypatch.setenv("GRIST_SYNC_TABLE_ID", "Formulas")
    monkeypatch.setitem(
        config.Settings.model_config, "secrets_dir", tmp_path / ".secrets"
    )

    args = parse_args(["config"])
    args.handler(**vars(args))
    assert setup_cli[0][1] == "file-secret"
    assert "file-secret" not in capsys.readouterr().out


def test_settings_directly_resolves_default_key_file(monkeypatch, tmp_path, setup_cli):
    (tmp_path / ".secrets" / "grist_sync_api_key").write_text("default-secret\n")
    monkeypatch.setenv("GRIST_SYNC_DOC_ID", "doc")
    monkeypatch.setenv("GRIST_SYNC_TABLE_ID", "Formulas")

    settings = config.Settings(_secrets_dir=tmp_path / ".secrets")

    assert settings.api_key.get_secret_value() == "default-secret"
    assert settings.source == Path("formulas")
    assert settings.outdir == Path(".grist/Spoof/Formulas")
    assert settings.doc_name == "Spoof"
    assert setup_cli[0][1] == "default-secret"
    assert "default-secret" not in repr(settings)


def test_table_selection_prefers_exact_match_and_rejects_ambiguity():
    assert config._select_tables(["Form", "Formulas"], "form") == "Form"
    with pytest.raises(ValueError, match="Found multiple tables"):
        config._select_tables(["Formulas", "Forms"], "Form")


def test_validation_precedes_api_and_does_not_expose_key(setup_cli):
    with pytest.raises(ValidationError):
        parse_args(["config"])
    assert not setup_cli

    with pytest.raises(ValidationError) as exc:
        parse_args(
            ["--doc", "doc", "--api-key", "secret-value", "config", "-t", "nope"]
        )
    assert "No tables match" in str(exc.value)
    assert "secret-value" not in str(exc.value)


def test_help_does_not_require_settings_or_api(setup_cli, capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--help"])
    assert exc.value.code == 0
    assert "Grist server URL" in capsys.readouterr().out
    assert not setup_cli


def test_pull_formulas_applies_column_skip_environment(
    monkeypatch, tmp_path, setup_cli
):
    settings = {
        "GRIST_SYNC_API_KEY": "key",
        "GRIST_SYNC_DOC_ID": "document-id",
        "GRIST_SYNC_SERVER": "https://grist.example",
        "GRIST_SYNC_TABLE_ID": "Formulas",
        "GRIST_SYNC_OUTDIR": str(tmp_path / "{doc}/{table}"),
        "GRIST_SYNC_COLUMN_FILTER": "foo|ba.*",
        "GRIST_SYNC_COLUMN_SKIP": "bar",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    args = parse_args(["pull"])
    args.handler(**vars(args))

    outdir = tmp_path / "Spoof/Formulas"
    for file in (
        OutputName.PULL.get(outdir, "foo"),
        OutputName.DERENDERED.get(outdir, "foo"),
    ):
        assert file.exists()

    for pattern in ("bar.py", "bam.py", "qux.py"):
        assert not glob(str(outdir / "**" / pattern), recursive=True)
