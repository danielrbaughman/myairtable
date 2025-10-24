import os
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
from fastapi import APIRouter
from rich import print
from typer import Option, Typer

from ...library.airtable import Airtable
from .airtable_meta_types import AirtableMetadata
from .airtable_typegen_helpers import camel_case, python_property_name, sanitize_string
from .airtable_typegen_python import gen_python, python_type
from .airtable_typegen_typescript import gen_typescript

# TODO
# - Add option for custom naming of tables/models
# - need to handle or at least detect duplicate property names
# - improve property naming
# - move to its own repo
# - improve invalid field message

# TS
# - Need to see what happens to read/write when the field name changes
# - Use Zod for type validation
# - Migrate to AirtableTS, or learn from it - especially the error handling

cli = Typer()
api = APIRouter(prefix="/airtable", tags=["airtable"])


# @api.get("/job", response_model=JobsModel)
@cli.command()
def test():
    jobs = Airtable().jobs.get()
    job = jobs[0]
    print(job.name)


def get_base_meta_data(base_id: str) -> AirtableMetadata:
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment")

    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"})
    data: AirtableMetadata = response.json()
    data["tables"].sort(key=lambda t: t["name"].lower())
    for table in data["tables"]:
        table["fields"].sort(key=lambda f: f["name"].lower())
    return data


base_id = os.getenv("AIRTABLE_BASE_ID") or ""
if not base_id:
    raise Exception("AIRTABLE_BASE_ID not found in environment")


@cli.command()
def gen(verbose: bool = False):
    """`WIP` Generate types and models for Airtable"""

    metadata = get_base_meta_data(base_id)
    # csv_export()
    gen_python(metadata, base_id, verbose)
    gen_typescript(metadata, base_id, verbose)


@cli.command(name="py")
def gen_py(verbose: bool = False):
    """`WIP` Generate Python types and models for Airtable"""
    metadata = get_base_meta_data(base_id)
    gen_python(metadata, base_id, verbose)


@cli.command(name="ts")
def gen_ts(verbose: bool = False):
    """`WIP` Generate TypeScript types and models for Airtable"""
    metadata = get_base_meta_data(base_id)
    gen_typescript(metadata, base_id, verbose)


@cli.command(name="csv")
def csv_export(fresh: Annotated[bool, Option(help="Generate fresh property names instead of using custom names if they exist.")] = False):
    """Export Airtable data to CSV format."""
    use_custom = not fresh
    metadata = get_base_meta_data(base_id)

    table_rows = []
    for table in metadata["tables"]:
        table_rows.append(
            {
                "Table ID": table["id"],
                "Table Name": table["name"],
                "Class Name": f"{camel_case(table['name'])}",
                "Record Dict": f"{camel_case(table['name'])}RecordDict",
                "ORM Model": f"{camel_case(table['name'])}ORM",
                "Pydantic Model": f"{camel_case(table['name'])}Model",
                "Property Name": python_property_name(table, use_custom=False),
            }
        )

    df = pd.DataFrame(table_rows, columns=["Table ID", "Table Name", "Class Name", "Record Dict", "ORM Model", "Pydantic Model", "Property Name"])
    output_path = Path("./src/library/airtable/tables.csv")
    df.to_csv(output_path, index=False)
    print(f"Table CSV exported to {output_path}")

    field_rows = []
    for table in metadata["tables"]:
        for field in table["fields"]:
            field_rows.append(
                {
                    "Table ID": table["id"],
                    "Table Name": table["name"],
                    "Field ID": field["id"],
                    "Field Name": sanitize_string(field["name"]),
                    "Property Name": python_property_name(field, use_custom=use_custom),
                    "Python Type": python_type(field, warn=False),
                    "Airtable Type": field["type"],
                }
            )

    fields_df = pd.DataFrame(
        field_rows, columns=["Table ID", "Table Name", "Field ID", "Field Name", "Property Name", "Python Type", "Airtable Type"]
    )
    fields_output_path = Path("./src/library/airtable/fields.csv")
    fields_df.to_csv(fields_output_path, index=False)
    print(f"Fields CSV exported to {fields_output_path}")
