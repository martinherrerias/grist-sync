import re
from http import HTTPStatus
from pathlib import Path
from typing import Literal, Self, overload

from grist_api import GristDocAPI
from pydantic import Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from requests.exceptions import HTTPError


class _SettingsMeta[Cls](type(BaseSettings)):
    """Work around type checkers flagging ``Settings()`` as missing required args.
    See: https://github.com/astral-sh/ty/issues/1070#issuecomment-3889179747
    """

    def __call__(cls, **kwargs) -> Cls:
        return super().__call__(**kwargs)


class Settings(BaseSettings, metaclass=_SettingsMeta["Settings"]):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir=".secrets",
        extra="ignore",
        env_prefix="GRIST_SYNC_",
        hide_input_in_errors=True,
    )

    server: str = "https://docs.getgrist.com"
    api_key: SecretStr
    doc_id: str = Field(serialization_alias="doc")
    dryrun: bool = False
    verify_ssl: bool = True

    table_id: str = "RUC"
    outdir: Path = Path(".grist/{doc}/{table}")
    source: Path = Field(default=Path("formulas"), serialization_alias="basedir")
    column_filter: str = Field(default=".*", serialization_alias="filter")

    other_tables: list[str] | str | None = None
    output: Path | None = None

    _api: GristDocAPI = PrivateAttr()
    _doc_name: str = PrivateAttr()

    @model_validator(mode="after")
    def resolve_document(self) -> Self:
        self._api = GristDocAPI(
            self.doc_id,
            api_key=self.api_key.get_secret_value(),
            server=self.server,
            dryrun=self.dryrun,
            verify_ssl=self.verify_ssl,
        )
        self._doc_name = _api_safe_get(self._api, "", "name")
        table_ids = [t["id"] for t in _api_safe_get(self._api, "tables")]
        self.table_id = _select_tables(table_ids, self.table_id, False)

        self.outdir = Path(
            str(self.outdir).format(doc=self._doc_name, table=self.table_id)
        )

        if isinstance(self.other_tables, str):
            self.other_tables = _select_tables(
                table_ids, self.other_tables, multiple=True
            )
        if self.output:
            self.output = Path(
                str(self.output).format(
                    doc=self.doc_name, table=self.table_id, outdir=str(self.outdir)
                )
            )

        return self

    @property
    def api(self) -> GristDocAPI:
        return self._api

    @property
    def doc_name(self) -> str:
        return self._doc_name


def _api_safe_get(api, endpoint, what=None):
    """
    `api.call(endpoint).json()[what]` without type warnings.
    `what` defaults to the last part of the endpoint.
    """
    response = api.call(endpoint)
    if response is None:
        raise HTTPError("Grist returned no response")
    if response.status_code != HTTPStatus.OK:
        raise HTTPError(f"Grist returned HTTP {response.status_code}")

    if what is None:
        what = endpoint.split("/")[-1]
    return response.json()[what]


@overload
def _select_tables(
    table_ids: list[str], pattern: str, multiple: Literal[False] = False, regex=True
) -> str: ...


@overload
def _select_tables(
    table_ids: list[str], pattern: str, multiple: Literal[True], regex=True
) -> list[str]: ...


def _select_tables(
    table_ids: list[str], pattern: str, multiple=False, regex=True
) -> str | list[str]:
    if regex:
        picks = [t for t in table_ids if re.search(pattern, t, flags=re.IGNORECASE)]
    else:
        picks = [t for t in table_ids if t.lower() == pattern.lower()]
    if not picks:
        raise ValueError(f"No tables match {pattern!r}")
    if len(picks) > 1 and not multiple:
        if regex:
            try:
                return _select_tables(table_ids, pattern, regex=False, multiple=False)
            except ValueError:
                pass
        raise ValueError(f"Found multiple tables matching {pattern!r}: {picks}")

    return picks if multiple else picks[0]
