#! /usr/bin/env python
# ruff: noqa: E501
"""
Comments/uncomments code blocks to support Grist-specific code patterns.
Code in SOURCE is expected to document required changes using:

```
# <GRIST>
# grist-specific code
# </GRIST>
# <LOCAL>
local (live) code for IDE
# </LOCAL>
```

Running this script will replace these blocks with:

```
# git@xxxxxxx
...
# <GRIST>
grist-specific code
# </GRIST>
# <LOCAL>
# local (live) code for IDE
# </LOCAL>
```

The `git@tag` header is inserted at the beginning of each file, to "version-control" the Grist code
"""

import re
import subprocess
from pathlib import Path
from warnings import warn

from . import OutputName


def local_to_grist(text, basedir=None):

    text = _comment_chunks(text, "LOCAL")
    text = _uncomment_chunks(text, "GRIST")
    text = _add_git_tag(text, basedir)
    return text


def grist_to_local(text):

    text = _uncomment_chunks(text, "LOCAL")
    text = _comment_chunks(text, "GRIST")
    text = _remove_git_tag(text)
    return text


def _add_git_tag(text, basedir=None):
    tag = subprocess.check_output(
        ["git", "describe", "--tags", "--dirty", "--always"], cwd=basedir
    ).decode()
    return f"# git@{tag}" + text


def _remove_git_tag(text):
    return re.sub(r"^# git@[^\n]+\n", "", text, flags=re.DOTALL)


def _uncomment_chunks(lines, tag):
    lines = re.sub(
        rf"(# ?<{tag}>\s*\n)(.*?)(# ?</{tag}>)",
        lambda m: (
            m.group(1)
            + re.sub(r"^# ?", "", m.group(2), flags=re.MULTILINE)
            + m.group(3)
        ),
        lines,
        flags=re.DOTALL,
    )
    return lines


def _comment_chunks(lines, tag):
    lines = re.sub(
        rf"(# ?<{tag}>\n)(.*?)(# ?</{tag}>)",
        lambda m: (
            m.group(1)
            + "".join(
                [
                    f"# {line}" if not line.startswith("\n") else "#\n"
                    for line in m.group(2).splitlines(keepends=True)
                ]
            )
            + m.group(3)
        ),
        lines,
        flags=re.DOTALL,
    )
    return lines


def _parse_files(basedir: Path, filter: str | None = None) -> list[Path]:

    assert basedir.is_dir()
    names = [f.name.rstrip(".py") for f in basedir.glob("*.py")]
    if not filter:
        filter = ".*"

    files = [n for n in names if re.search(filter, n, flags=re.IGNORECASE)]
    paths = [basedir / f"{n}.py" for n in files]
    return paths


def main(args):

    files = _parse_files(args.basedir, args.column_filter)
    if not files:
        warn(f"No files found in {args.basedir} matching filter '{args.column_filter}'")
        return

    args.outdir.mkdir(exist_ok=True)
    for src in files:
        tgt = OutputName.RENDER.get(args.outdir, src.name)
        print(f"Rendering {src} -> {tgt}")

        local_text = src.read_text()
        grist_text = local_to_grist(local_text, args.basedir)
        tgt.write_text(grist_text)

        # verify that code can be converted back without changes
        roundtrip_text = grist_to_local(grist_text)
        if roundtrip_text != local_text:
            temp = OutputName.ROUND.get(args.outdir, src.name)
            temp.write_text(roundtrip_text)
            cmd = ["diff", str(src), str(temp)]
            diff = subprocess.run(cmd, capture_output=True, text=True, check=False)
            warn(f"Round-trip failed for {src.name}:\n> {' '.join(cmd)}\n{diff.stdout}")
