"""Mermaid to SVG conversion using mermaid-cli (local Playwright/Chromium)."""

import asyncio
import hashlib
from pathlib import Path

from mermaid_cli import render_mermaid
from rich import print

from . import timer


def _compute_content_hash(content: str, length: int = 12) -> str:
    """Compute SHA256 hash of content, return first `length` hex chars."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:length]


def _cleanup_old_versions(cache_dir: Path, field_id: str, current_file: Path) -> None:
    """Remove cached SVG files for field_id that don't match current_file."""
    for old_file in cache_dir.glob(f"{field_id}_*.svg"):
        if old_file != current_file:
            old_file.unlink(missing_ok=True)


async def _render_svg(mermaid_code: str) -> bytes | None:
    """Async render mermaid to SVG using mermaid-cli."""
    try:
        _, _, svg_data = await render_mermaid(
            mermaid_code,
            output_format="svg",
        )
        return svg_data
    except Exception as e:
        print(f"[yellow]SVG render failed: {e}[/]")
        return None


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

    with timer.timer("mermaid-cli render (SVG)"):
        svg_data = asyncio.run(_render_svg(mermaid_code))

    if svg_data:
        svg_content = svg_data.decode("utf-8") if isinstance(svg_data, bytes) else svg_data

        # Atomic write: write to temp file, then rename
        temp_file = cache_file.with_suffix(".tmp")
        temp_file.write_text(svg_content)
        temp_file.rename(cache_file)

        # Cleanup old versions with different hashes
        _cleanup_old_versions(cache_dir, field_id, cache_file)

        return svg_content

    return None
