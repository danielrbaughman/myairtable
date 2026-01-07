import csv
from pathlib import Path

from pydantic.alias_generators import to_snake
from rich import print

from src.helpers import sanitize_string
from src.meta import MODEL_NAME, PROPERTY_NAME, Base
from src.python import python_type
from src.typescript import typescript_type

# Column definitions for CSV exports
TABLE_COLUMNS = [
    "Table ID",
    "Table Name",
    PROPERTY_NAME,
    MODEL_NAME,
]
FIELD_COLUMNS = [
    "Table ID",
    "Table Name",
    "Field ID",
    "Field Name",
    PROPERTY_NAME,
    "Airtable Type",
    "Python Type",
    "TypeScript Type",
]


def generate_csv(base: Base, folder: Path, fresh: bool):
    """Export Airtable data to CSV format."""
    use_custom = not fresh

    # Generate tables CSV
    tables_csv_path = Path(folder) / "tables.csv"
    with open(tables_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TABLE_COLUMNS)
        writer.writeheader()
        for table in base.tables:
            writer.writerow(
                {
                    "Table ID": table.id,
                    "Table Name": table.name,
                    PROPERTY_NAME: table.name_snake(use_custom=use_custom),
                    MODEL_NAME: to_snake(table.name_model(use_custom=use_custom)),
                }
            )
    print(f"Table CSV exported to '{tables_csv_path}'")

    # Generate fields CSV
    fields_output_path = Path(folder) / "fields.csv"
    use_custom = use_custom and fields_output_path.exists()

    with open(fields_output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_COLUMNS)
        writer.writeheader()
        for table in base.tables:
            for field in table.fields:
                writer.writerow(
                    {
                        "Table ID": table.id,
                        "Table Name": table.name,
                        "Field ID": field.id,
                        "Field Name": sanitize_string(field.name),
                        PROPERTY_NAME: field.name_snake(use_custom=use_custom),
                        "Airtable Type": field.type,
                        "Python Type": python_type(field),
                        "TypeScript Type": typescript_type(field),
                    }
                )
    print(f"Fields CSV exported to '{fields_output_path}'")
