import json
import os

import httpx
from rich import print
from typer import Typer

from ...library.constants import LocalFolders
from ..src.airtable_meta_types import AirtableMetadata

cli = Typer()


def get_base_meta_data() -> AirtableMetadata:
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment")

    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not base_id:
        raise Exception("AIRTABLE_BASE_ID not found in environment")

    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"})
    data: AirtableMetadata = response.json()
    data["tables"].sort(key=lambda t: t["name"].lower())
    for table in data["tables"]:
        table["fields"].sort(key=lambda f: f["name"].lower())
    return data


def get_view_meta_data(view_id: str):
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment")

    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not base_id:
        raise Exception("AIRTABLE_BASE_ID not found in environment")

    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/views/{view_id}"
    response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, follow_redirects=True)
    data = response.json()
    return data


@cli.command()
def meta():
    """Fetch Airtable metadata into a json file."""

    data = get_base_meta_data()
    output_path = LocalFolders.JSON / "airtable_metadata.json"
    with open(output_path, "w") as f:
        f.write(json.dumps(data, indent=4))
    print(f"Base metadata written to {output_path}")
