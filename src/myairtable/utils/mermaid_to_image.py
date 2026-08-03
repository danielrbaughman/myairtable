import asyncio
import base64
import hashlib
import json
import sys
import zlib
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from mermaid_cli import render_mermaid
from rich import print


def mermaid_live_url(mermaid_code: str) -> str:
    """Generate a Mermaid Live Editor URL for the given mermaid code."""
    state = {"code": mermaid_code, "mermaid": {"theme": "default"}}
    json_bytes = json.dumps(state).encode("utf-8")
    compressed = zlib.compress(json_bytes, level=9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
    return f"https://mermaid.live/edit#pako:{encoded}"


def _compute_content_hash(content: str, length: int = 12) -> str:
    """Compute SHA256 hash of content, return first `length` hex chars."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:length]


def cleanup_old_versions(cache_dir: Path, field_id: str, current_file: Path) -> None:
    """Remove cached SVG files for field_id that don't match current_file."""
    for old_file in cache_dir.glob(f"{field_id}_*.svg"):
        if old_file != current_file:
            old_file.unlink(missing_ok=True)


# Diagram rendering degrades rather than aborts — one bad diagram should not lose a
# whole docs build. But a degraded build must not look like a clean one, so every
# failure is counted here and the CLI exits non-zero if the count is non-zero.
# See svg_failure_count() / report_svg_failures().
_svg_failures: list[str] = []


def svg_failure_count() -> int:
    """Number of SVG renders that have failed in this process."""
    return len(_svg_failures)


def _record_svg_failure(error: str) -> None:
    _svg_failures.append(error)


def report_svg_failures() -> None:
    """Print a summary of failed SVG renders. No-op when everything rendered."""
    if not _svg_failures:
        return

    print(f"[red]{len(_svg_failures)} diagram(s) failed to render — docs are missing or serving stale SVGs.[/]")

    # The same root cause fails every diagram identically, so group rather than
    # printing N copies of one message.
    counts = Counter(_svg_failures)
    for error, count in counts.most_common():
        suffix = f" [dim](x{count})[/]" if count > 1 else ""
        print(f"[red] - {error}[/]{suffix}")

    # By far the most common cause: playwright resolved to a version whose pinned
    # chromium build was never downloaded. Say the exact command rather than making
    # the reader decode playwright's box-drawing banner.
    if any("Executable doesn't exist" in error or "playwright install" in error for error in counts):
        print("[yellow]Hint: the chromium build this playwright expects is not installed. Run:[/]")
        print("[yellow]  playwright install chromium-headless-shell[/]")


async def render_svg(mermaid_code: str) -> bytes:
    """Async render mermaid to SVG using mermaid-cli. Raises on render failure."""
    _, _, svg_data = await render_mermaid(
        mermaid_code,
        output_format="svg",
    )
    return svg_data


def get_cached_svg(
    mermaid_code: str,
    cache_dir: Path,
    field_id: str,
) -> str | None:
    """
    Check if a cached SVG exists for the given mermaid code.

    Args:
        mermaid_code: The mermaid diagram code
        cache_dir: Directory to check for cached images
        field_id: Field ID for cache filename prefix

    Returns SVG content as string if cached, or None if not cached.
    """
    content_hash = _compute_content_hash(mermaid_code)
    cache_file = cache_dir / f"{field_id}_{content_hash}.svg"

    if cache_file.exists():
        cached_content = cache_file.read_text()
        if cached_content.strip().startswith("<svg"):
            return cached_content
        # Corrupted cache file, remove it
        cache_file.unlink(missing_ok=True)

    return None


def mermaid_to_svg(
    mermaid_code: str,
    cache_dir: Path,
    field_id: str,
) -> str | None:
    """
    Convert mermaid code to SVG using local mermaid-cli with content-based caching.

    Cache files are named {field_id}_{hash}.svg where hash is computed from
    mermaid_code. If content changes, a new cache file is created and old
    versions are cleaned up.

    Args:
        mermaid_code: The mermaid diagram code
        cache_dir: Directory to cache rendered images
        field_id: Field ID for cache filename prefix

    Returns SVG content as string, or None on failure.
    """
    # Check cache first
    if cached := get_cached_svg(mermaid_code, cache_dir, field_id):
        return cached

    # Compute hash for cache filename
    content_hash = _compute_content_hash(mermaid_code)
    cache_file = cache_dir / f"{field_id}_{content_hash}.svg"

    try:
        svg_data = asyncio.run(render_svg(mermaid_code))
    except Exception as e:
        _record_svg_failure(str(e))
        return None

    if svg_data:
        svg_content = svg_data.decode("utf-8") if isinstance(svg_data, bytes) else svg_data

        # Atomic write: write to temp file, then rename
        temp_file = cache_file.with_suffix(".tmp")
        temp_file.write_text(svg_content)
        temp_file.rename(cache_file)

        # Cleanup old versions with different hashes
        cleanup_old_versions(cache_dir, field_id, cache_file)

        return svg_content

    return None


async def render_svg_task(field_id: str, mermaid_code: str, cache_dir: Path) -> tuple[str, str | None]:
    """Async task to render a single SVG and handle caching."""
    # Compute hash for cache filename
    content_hash = _compute_content_hash(mermaid_code)
    cache_file = cache_dir / f"{field_id}_{content_hash}.svg"

    try:
        svg_data = await render_svg(mermaid_code)
    except Exception as e:
        _record_svg_failure(str(e))
        return (field_id, None)

    if svg_data:
        svg_content = svg_data.decode("utf-8") if isinstance(svg_data, bytes) else svg_data

        # Atomic write: write to temp file, then rename
        temp_file = cache_file.with_suffix(".tmp")
        temp_file.write_text(svg_content)
        temp_file.rename(cache_file)

        # Cleanup old versions with different hashes
        cleanup_old_versions(cache_dir, field_id, cache_file)

        return (field_id, svg_content)

    return (field_id, None)


async def render_all_svgs_async(
    svg_tasks: list[tuple[str, str]],
    cache_dir: Path,
    on_progress: Callable[[int, int], None] | None = None,
    batch_size: int = 10,
) -> list[tuple[str, str | None]]:
    """Render all SVGs concurrently in batches with progress callback."""
    results: list[tuple[str, str | None]] = []
    total = len(svg_tasks)

    # Process in batches
    for i in range(0, total, batch_size):
        batch = svg_tasks[i : i + batch_size]
        batch_tasks = [render_svg_task(field_id, mermaid_code, cache_dir) for field_id, mermaid_code in batch]

        # Run batch concurrently, updating progress as each task completes
        for coro in asyncio.as_completed(batch_tasks):
            result = await coro
            results.append(result)
            if on_progress:
                on_progress(len(results), total)

    return results


def render_svgs_parallel(
    svg_tasks: list[tuple[str, str]],
    cache_dir: Path,
) -> list[tuple[str, str | None]]:
    """
    Render multiple SVGs in parallel using asyncio.

    Args:
        svg_tasks: List of (field_id, mermaid_code) tuples to render
        cache_dir: Directory to cache rendered images

    Returns:
        List of (field_id, svg_content) tuples. svg_content is None on failure.
    """
    if not svg_tasks:
        return []

    total = len(svg_tasks)

    def update_progress(completed: int, total: int) -> None:
        sys.stdout.write(f"\rGenerating formula SVGs ({completed}/{total})...\033[K")
        sys.stdout.flush()

    # Print initial status
    sys.stdout.write(f"Generating formula SVGs (0/{total})...")
    sys.stdout.flush()

    failures_before = svg_failure_count()
    results = asyncio.run(render_all_svgs_async(svg_tasks, cache_dir, update_progress))
    failed = svg_failure_count() - failures_before

    # The progress counter counts *completed* tasks, not successful ones, so an
    # unqualified "done" here read as success even when every render had failed.
    if failed:
        sys.stdout.write(f" {total - failed}/{total} ok, {failed} FAILED\n")
    else:
        sys.stdout.write(" done\n")
    sys.stdout.flush()

    return results
