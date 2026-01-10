"""Mermaid to SVG conversion using mermaid-cli (local Playwright/Chromium)."""

import asyncio
from pathlib import Path

from mermaid_cli import render_mermaid
from rich import print

from . import timer


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


def mermaid_to_svg(
    mermaid_code: str,
    cache_dir: Path,
    field_id: str,
) -> str | None:
    """
    Convert mermaid code to SVG using local mermaid-cli with caching.

    Args:
        mermaid_code: The mermaid diagram code
        cache_dir: Directory to cache rendered images
        field_id: Field ID to use as cache filename

    Returns SVG content as string, or None on failure.
    """
    cache_file = cache_dir / f"{field_id}.svg"

    # Return cached if exists
    if cache_file.exists():
        return cache_file.read_text()

    with timer.timer("mermaid-cli render (SVG)"):
        svg_data = asyncio.run(_render_svg(mermaid_code))

    if svg_data:
        svg_content = svg_data.decode("utf-8") if isinstance(svg_data, bytes) else svg_data
        cache_file.write_text(svg_content)
        return svg_content

    return None
