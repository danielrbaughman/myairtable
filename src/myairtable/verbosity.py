"""Process-wide verbosity flag, with no typer dependency.

The analysis core (meta.py and the generators) reads this via ``if verbose:``.
The CLI flips it from typer's ``-v`` flag (see main.py). Keeping it typer-free is
the point: importing the core (``schema_tools`` -> ``meta`` -> here) must not pull
typer + click + shellingham, which belong to the ``[cli]`` extra.
"""

from __future__ import annotations


class _Verbosity:
    """A mutable, truthy-when-enabled singleton.

    A tiny object rather than a module-level bool so that readers can keep the
    idiomatic ``if verbose:`` and still observe the current process state
    regardless of import order (a re-bound module global would not propagate to
    ``from ... import verbose`` callers).
    """

    def __init__(self) -> None:
        self.enabled = False

    def __bool__(self) -> bool:
        return self.enabled


verbose = _Verbosity()


def enable() -> None:
    """Turn on verbose output. Called by the CLI when ``-v`` is passed."""
    verbose.enabled = True
