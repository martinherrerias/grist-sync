from enum import Enum
from pathlib import Path


class OutputName(Enum):
    RENDER = "rendered_"  # Grist-adjusted, from current SOURCE version
    PULL = "pull_"  # Local-adjusted, from current DOC/TABLE
    ROUND = "roundtrip_"  # Grist-adjusted, then local-adjusted again
    OLD = "old_"  # git checkout TAG -- FILE for DOC/TABLE git@TAG

    def get(self, outdir: Path, name: str):
        name = name.lower()
        if not name.endswith(".py"):
            name = name + ".py"
        return Path(outdir) / (self.value + name)
