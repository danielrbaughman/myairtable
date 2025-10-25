from pathlib import Path

from typer import Argument, Option, Typer

from src.csv import gen_csv
from src.meta import gen_meta, get_base_id, get_base_meta_data
from src.python import gen_python
from src.typescript import gen_typescript

# from src import csv, meta, python, typescript

# TODO
# - Add option for custom naming of tables/models
# - need to handle or at least detect duplicate property names
# - improve property naming
# - improve invalid field message
# - improve the CLI with lots of options to enable/disable features

# TS
# - Need to see what happens to read/write when the field name changes
# - Use Zod for type validation?
# - Migrate to AirtableTS, or learn from it - especially the error handling

app = Typer()


@app.command()
def meta(folder: str = Argument(help="Path to the output folder")):
    """Fetch Airtable metadata into a json file."""
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    gen_meta(folder=folder_path)


@app.command()
def csv(
    folder: str = Argument(help="Path to the output folder"),
    fresh: bool = Option(default=False, help="Generate fresh property names instead of using custom names if they exist."),
):
    """Export Airtable metadata to CSV format."""
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    gen_csv(folder=folder_path, fresh=fresh)


@app.command()
def py(folder: str = Argument(help="Path to the output folder"), verbose: bool = False):
    """Generate types and models in Python"""
    base_id = get_base_id()
    metadata = get_base_meta_data(base_id)
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    gen_python(metadata, base_id, verbose, folder=folder_path)


@app.command()
def ts(folder: str = Argument(help="Path to the output folder"), verbose: bool = False):
    """Generate types and models in TypeScript"""
    base_id = get_base_id()
    metadata = get_base_meta_data(base_id)
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    gen_typescript(metadata, base_id, verbose, folder=folder_path)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
