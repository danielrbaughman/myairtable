"""Bundled static files resolve from the module, not the caller's cwd.

Regression tests for the silent-skip bug: copy_static_files located its source
as `Path("./static/<type>")` and guarded with `if source.exists()`, so running
codegen from any directory other than the repo root copied nothing and raised
nothing. The generated packages import these files, so the failure surfaced
later as an ImportError in a consumer, far from the cause.
"""

import pytest

from src.utils.helpers import copy_static_files, static_dir


def test_static_dir_resolves_from_any_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert static_dir("python").is_dir()


def test_static_dir_raises_on_unknown_runtime():
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        static_dir("nonexistent")


def test_copy_static_files_works_outside_the_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "generated"
    copy_static_files(out, "python")

    copied = list((out / "static").rglob("*"))
    assert copied, "static files must copy when cwd is outside the repo"
    # formula.py is load-bearing: generated __init__ does `from .static.formula import *`
    assert (out / "static" / "formula.py").is_file()


def test_copy_static_files_matches_repo_root_run(tmp_path, monkeypatch):
    from_repo = tmp_path / "from_repo"
    copy_static_files(from_repo, "python")

    monkeypatch.chdir(tmp_path)
    from_elsewhere = tmp_path / "from_elsewhere"
    copy_static_files(from_elsewhere, "python")

    names = lambda p: sorted(f.relative_to(p).as_posix() for f in p.rglob("*"))  # noqa: E731
    assert names(from_repo) == names(from_elsewhere)


def test_copy_static_files_raises_when_bundle_is_missing(tmp_path, monkeypatch):
    """A missing bundle must fail loudly rather than emit an incomplete package."""
    monkeypatch.setattr("src.utils.helpers.STATIC_ROOT", tmp_path / "gone")
    with pytest.raises(FileNotFoundError):
        copy_static_files(tmp_path / "out", "python")
