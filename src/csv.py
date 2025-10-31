from pathlib import Path

import pandas as pd
from pydantic.alias_generators import to_snake

from src.helpers import MODEL_NAME, PROPERTY_NAME, property_name_model, property_name_snake, sanitize_string
from src.meta_types import BaseMetadata
from src.python import python_type
from src.typescript import typescript_type


def gen_csv(metadata: BaseMetadata, folder: Path, fresh: bool):
    """Export Airtable data to CSV format."""

    use_custom = not fresh

    table_rows = []
    for table in metadata["tables"]:
        table_rows.append(
            {
                "Table ID": table["id"],
                "Table Name": table["name"],
                PROPERTY_NAME: property_name_snake(table, folder, use_custom=use_custom),
                MODEL_NAME: to_snake(property_name_model(table, folder, use_custom=use_custom)),
            }
        )

    df = pd.DataFrame(
        table_rows,
        columns=[
            "Table ID",
            "Table Name",
            PROPERTY_NAME,
            MODEL_NAME,
        ],
    )
    tables_csv_path = Path(folder) / "tables.csv"
    df.to_csv(tables_csv_path, index=False)
    print(f"Table CSV exported to {tables_csv_path}")

    fields_output_path = Path(folder) / "fields.csv"
    use_custom = use_custom and fields_output_path.exists()

    field_rows: list[dict] = []
    for table in metadata["tables"]:
        for field in table["fields"]:
            field_rows.append(
                {
                    "Table ID": table["id"],
                    "Table Name": table["name"],
                    "Field ID": field["id"],
                    "Field Name": sanitize_string(field["name"]),
                    PROPERTY_NAME: property_name_snake(field, folder, use_custom=use_custom),
                    "Airtable Type": field["type"],
                    "Python Type": python_type(table["name"], field, warn=False),
                    "TypeScript Type": typescript_type(table["name"], field, warn=False),
                }
            )

    fields_df = pd.DataFrame(
        field_rows,
        columns=[
            "Table ID",
            "Table Name",
            "Field ID",
            "Field Name",
            PROPERTY_NAME,
            "Airtable Type",
            "Python Type",
            "TypeScript Type",
        ],
    )
    fields_df.to_csv(fields_output_path, index=False)
    print(f"Fields CSV exported to {fields_output_path}")
