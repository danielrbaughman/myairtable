"""Lightweight timing utilities for performance benchmarking."""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from rich import print

# Global flag to enable/disable timing output
_enabled = False
_timings: dict[str, list[float]] = {}

P = ParamSpec("P")
R = TypeVar("R")


def enable():
    """Enable timing output."""
    global _enabled
    _enabled = True


def disable():
    """Disable timing output."""
    global _enabled
    _enabled = False


def is_enabled() -> bool:
    """Check if timing is enabled."""
    return _enabled


def reset():
    """Reset all accumulated timings."""
    global _timings
    _timings = {}


@contextmanager
def timer(name: str):
    """Context manager for timing a block of code."""
    if not _enabled:
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        _timings.setdefault(name, []).append(elapsed)
        print(f"[dim cyan]  [{elapsed * 1000:.1f}ms] {name}[/]")


def timed(name: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for timing a function."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:  # type: ignore
        timer_name = name or func.__qualname__  # type: ignore

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not _enabled:
                return func(*args, **kwargs)

            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                _timings.setdefault(timer_name, []).append(elapsed)
                print(f"[dim cyan]  [{elapsed * 1000:.1f}ms] {timer_name}[/]")

        return wrapper

    return decorator


def summary():
    """Print a summary of all timings."""
    if not _enabled or not _timings:
        return

    print("\n[bold cyan]Performance Summary[/]")
    print("[dim]" + "-" * 60 + "[/]")

    # Sort by total time descending
    sorted_timings = sorted(
        _timings.items(),
        key=lambda x: sum(x[1]),
        reverse=True,
    )

    for name, times in sorted_timings:
        total = sum(times)
        count = len(times)
        avg = total / count if count > 0 else 0

        if count == 1:
            print(f"[cyan]{name:40}[/] {total * 1000:8.1f}ms")
        else:
            print(f"[cyan]{name:40}[/] {total * 1000:8.1f}ms total ({count}x, avg {avg * 1000:.1f}ms)")

    print("[dim]" + "-" * 60 + "[/]")
    total_time = sum(sum(times) for times in _timings.values())
    print(f"[bold cyan]{'Total measured time':40}[/] {total_time * 1000:8.1f}ms")
