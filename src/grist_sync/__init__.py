from enum import Enum
from pathlib import Path


class OutputName(Enum):
    RENDER = "sandbox/local/"  # Grist-adjusted, from current SOURCE version
    PULL = "sandbox/pull/"  # Raw remote, from current DOC/TABLE
    DERENDERED = "python/remote/"  # Remote, local-adjusted, from current DOC/TABLE
    ROUND = "python/roundtrip/"  # Grist-adjusted, then local-adjusted again
    OLD = "python/old/"  # git checkout TAG -- FILE for DOC/TABLE git@TAG

    def get(self, outdir: Path, name: str):
        name = name.lower()
        if not name.endswith(".py"):
            name = name + ".py"
        f = Path(outdir) / (self.value + name)
        f.parent.mkdir(parents=True, exist_ok=True)
        return f
