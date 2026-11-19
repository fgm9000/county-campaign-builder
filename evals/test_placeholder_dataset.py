"""Placeholder check until the real evaluation dataset exists."""

from pathlib import Path

import evals
from evals.conftest import LIVE_FLAG, live_ignore


def test_evals_package_imports_and_live_files_are_ignored_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / "test_sample_live.py").write_text("", encoding="utf-8")
    (tmp_path / "test_sample.py").write_text("", encoding="utf-8")
    assert isinstance(evals.__doc__, str)
    assert live_ignore({}, tmp_path) == ["test_sample_live.py"]
    assert live_ignore({LIVE_FLAG: "1"}, tmp_path) == []
