import os
from pathlib import Path
from typing import Annotated

import pandas as pd
from rich import print
from typer import Option, Typer

from src.meta import get_base_meta_data

from .airtable_typegen_helpers import camel_case, python_property_name, sanitize_string
from .airtable_typegen_python import gen_python, python_type
from .airtable_typegen_typescript import gen_typescript

cli = Typer()


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
