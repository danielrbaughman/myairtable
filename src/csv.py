from pathlib import Path

import pandas as pd

from src.helpers import camel_case, property_name, python_property_name, sanitize_string
from src.meta import get_base_id, get_base_meta_data
from src.python import python_type
from src.typescript import typescript_type


def gen_csv(folder: Path, fresh: bool):
    """Export Airtable data to CSV format."""

    use_custom = not fresh
    metadata = get_base_meta_data(get_base_id())

    table_rows = []
    for table in metadata["tables"]:
        table_rows.append(
            {
                "Table ID": table["id"],
                "Table Name": table["name"],
                "Class Name": f"{camel_case(table['name'])}",
                "Property Name": python_property_name(table, folder, use_custom=False),
            }
        )

    df = pd.DataFrame(table_rows, columns=["Table ID", "Table Name", "Class Name", "Record Dict", "ORM Model", "Pydantic Model", "Property Name"])
    tables_csv_path = Path(folder) / "tables.csv"
    df.to_csv(tables_csv_path, index=False)
    print(f"Table CSV exported to {tables_csv_path}")

    field_rows: list[dict] = []
    for table in metadata["tables"]:
        for field in table["fields"]:
            field_rows.append(
                {
                    "Table ID": table["id"],
                    "Table Name": table["name"],
                    "Field ID": field["id"],
                    "Field Name": sanitize_string(field["name"]),
                    "Property Name (snake)": python_property_name(field, folder, use_custom=use_custom),
                    "Property Name (camel)": property_name(field, folder, use_custom=use_custom),
                    "Airtable Type": field["type"],
                    "Python Type": python_type(field, warn=False),
                    "TypeScript Type": typescript_type(field, warn=False),
                }
            )

    fields_df = pd.DataFrame(
        field_rows,
        columns=[
            "Table ID",
            "Table Name",
            "Field ID",
            "Field Name",
            "Property Name (snake)",
            "Property Name (camel)",
            "Airtable Type",
            "Python Type",
            "TypeScript Type",
        ],
    )
    fields_output_path = Path(folder) / "fields.csv"
    fields_df.to_csv(fields_output_path, index=False)
    print(f"Fields CSV exported to {fields_output_path}")
