# Grist Sync

Command-line utility to maintain a version-controlled repository of [Grist](https://www.getgrist.com/) formulas in sync with a remote document. `gr sync` ["renders"](#formula-blocks) local source files for Grist, retrieves existing formulas, and checks for conflicting changes before pushing updates.

## Setup and Configuration

```sh
uv sync
cp .env.template .env
gr config
gr --help
```

Edit `.env` with the Grist server URL, document ID, and API key, etc. The template should be self documenting. Use `gr config` to check if your settings are being picked up as intended. See `gr --help` for further information, and available commands.

## Formula blocks

Local code might need mocks and import placeholders to keep linters/type-checkers happy, as some classes and formulas are not available from an importable library. Similarly, things like an end return-statement are required in Grist but make no sense on a local module.

We use commented blocks to keep Grist-specific quirks separate from local code, e.g.:

```python
# <GRIST>
# # This block will be un-commented in Grist
# import grist
# from grist import Record, UserTable
# </GRIST>

# <LOCAL>
# This block will be commented-out in Grist
from typing import TypeAlias
import re

record: TypeAlias = object
UserTable: TypeAlias = object

def REGEXREPLACE(s: str, pattern: str, replacement: str) -> str:
  return re.sub(pattern, replacement, s)
# </LOCAL>

# Code outside blocks stays the same
def my_function(record: Record, table: UserTable) -> str:

  return = sorted(
    table.lookupRecords(user=record.user),
      key=lambda r: REGEXREPLACE(record.user, r"[^a-zA-Z0-9]", "_"),
    )

# <GRIST>
# return my_function  # un-commented in Grist
# </GRIST>
```

## Command overview

`gr render` writes rendered copies, commenting out `<LOCAL>` blocks and uncommenting `<GRIST>` blocks. It adds a `git@TAG` header to record the source revision.

`gr pull` retrieves formulas from the configured document and table, then reverse-renders them for comparison with local files.

`gr push` sends rendered files to Grist after checking that local files are clean at the recorded Git revision and that server formulas have not changed since that revision.

`gr sync` runs the render and push steps. Use `gr sync --force` to push despite detected conflicts.


## Notes

- Rendering is meant to be reversible (so that, if there are conflicts, these can be resolved in the "local" scope).
- File / column-id match is case insensitive.

## TODO

- Better git integration, e.g. keep remotes on an orphan branch
- Helper commands (e.g. `status`, `clean`)
- Resolve `sandbox/grist` imports propperly
- Test rendered code on a mock sandbox?
