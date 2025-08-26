import json
from pathlib import Path

import pandas as pd
from typer import Typer

from airtable_typegen import camel_case, property_name, python_gen, python_type
from meta import get_base_meta_data

app = Typer()


@app.command()
def meta():
    """Fetch Airtable metadata into a json file."""

    data = get_base_meta_data()
    output_path = Path("airtable_base_metadata.json")
    with open(output_path, "w") as f:
        f.write(json.dumps(data, indent=4))
    print(f"Base metadata written to {output_path}")

@app.command(name="csv")
def csv_export():
    """Export types and names for Airtable tables and fields to CSV."""
    metadata = get_base_meta_data()

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
                "Property Name": property_name(table, use_custom=False),
            }
        )

    df = pd.DataFrame(table_rows, columns=["Table ID", "Table Name", "Class Name", "Record Dict", "ORM Model", "Pydantic Model", "Property Name"])
    output_path = Path("airtable_tables.csv")
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
                    "Field Name": field["name"],
                    "Property Name": property_name(field, use_custom=False),
                    "Python Type": python_type(field, warn=False),
                    "Airtable Type": field["type"],
                }
            )

    fields_df = pd.DataFrame(
        field_rows, columns=["Table ID", "Table Name", "Field ID", "Field Name", "Property Name", "Python Type", "Airtable Type"]
    )
    fields_output_path = Path("airtable_fields.csv")
    fields_df.to_csv(fields_output_path, index=False)
    print(f"Fields CSV exported to {fields_output_path}")

@app.command()
def python():
    """Generate Python types and models for Airtable."""
    python_gen()


if __name__ == "__main__":
    app()
