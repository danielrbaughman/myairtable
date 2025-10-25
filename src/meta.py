import json
import os
import time
from pathlib import Path

import httpx

from .meta_types import BaseMetadata


def get_base_meta_data(base_id: str) -> BaseMetadata:
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment")

    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.ReadTimeout:
        print("Request timed out, retrying in 5 seconds...")
        time.sleep(5)
        response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"})
    data: BaseMetadata = response.json()
    data["tables"].sort(key=lambda t: t["name"].lower())
    for table in data["tables"]:
        table["fields"].sort(key=lambda f: f["name"].lower())
    return data


def get_base_id() -> str:
    """Get the Airtable Base ID from environment variable."""
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not base_id:
        raise Exception("AIRTABLE_BASE_ID not found in environment")
    return base_id


def gen_meta(folder: Path):
    """Fetch Airtable metadata into a json file."""

    base_id = get_base_id()
    data = get_base_meta_data(base_id)
    p = folder / "meta.json"
    with open(p, "w") as f:
        f.write(json.dumps(data, indent=4))
    print(f"Base metadata written to {p.as_posix()}")
