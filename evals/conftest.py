"""Collection rules for `pytest evals/`: live evaluation files run only with LIVE_EVAL=1."""

import os
from collections.abc import Mapping
from pathlib import Path

LIVE_FLAG = "LIVE_EVAL"
LIVE_GLOB = "test_*_live.py"
EVALS_DIR = Path(__file__).resolve().parent


def live_ignore(environ: Mapping[str, str], directory: Path = EVALS_DIR) -> list[str]:
    """Live files are not collected (not skipped) unless LIVE_EVAL=1."""
    if environ.get(LIVE_FLAG) == "1":
        return []
    return sorted(path.name for path in directory.glob(LIVE_GLOB))


collect_ignore = live_ignore(os.environ)
