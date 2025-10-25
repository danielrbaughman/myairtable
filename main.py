from pathlib import Path
from typing import Annotated

from typer import Argument, Option, Typer

from src.csv import gen_csv
from src.meta import gen_meta, get_base_id, get_base_meta_data
from src.python import gen_python

# from src.typescript import gen_typescript

# TODO

# CLI
# - ReadMe
# - Private -> Public repo

# TS
# - Output to smaller files (similar to python)
# - Improve diff readability of generated code (line breaks, indentations, etc)
# - Need to see what happens to read/write when the field name changes
# - Migrate to Airtable-TS
# - Use Zod for type validation?
# - improve the CLI with lots of options to enable/disable features (typescript)

# Future Ideas
# - JS
# - https://squidfunk.github.io/mkdocs-material/

app = Typer()


@app.command()
def meta(
    folder: Annotated[str, Argument(help="Path to the output folder")],
):
    """Fetch Airtable metadata into a json file."""
    base_id = get_base_id()
    metadata = get_base_meta_data(base_id)
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    gen_meta(metadata=metadata, folder=folder_path)


@app.command()
def csv(
    folder: Annotated[str, Argument(help="Path to the output folder")],
    fresh: Annotated[bool, Option(help="Generate fresh property names instead of using custom names if they exist.")] = False,
):
    """Export Airtable metadata to CSV format."""
    base_id = get_base_id()
    metadata = get_base_meta_data(base_id)
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    gen_csv(metadata=metadata, folder=folder_path, fresh=fresh)


@app.command()
def py(
    folder: Annotated[str, Argument(help="Path to the output folder")],
    fresh: Annotated[bool, Option(help="Generate fresh property names instead of using custom names if they exist.")] = False,
    formulas: Annotated[bool, Option(help="Include formula-helper classes in the output.")] = True,
    wrappers: Annotated[bool, Option(help="Include wrapper classes for tables and base in the output.")] = True,
    validation: Annotated[bool, Option(help="Include Pydantic-based type validation in ORM models.")] = True,
):
    """Generate types and models in Python"""
    base_id = get_base_id()
    metadata = get_base_meta_data(base_id)
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    if fresh:
        gen_csv(metadata=metadata, folder=folder_path, fresh=True)
    gen_python(
        metadata=metadata,
        base_id=base_id,
        folder=folder_path,
        formulas=formulas,
        wrappers=wrappers,
        validation=validation,
    )


# Disabled for now, while I finalize the Python version.
# @app.command()
# def ts(folder: str = Argument(help="Path to the output folder")):
#     """Generate types and models in TypeScript"""
#     base_id = get_base_id()
#     metadata = get_base_meta_data(base_id)
#     folder_path = Path(folder)
#     folder_path.mkdir(parents=True, exist_ok=True)
#     gen_typescript(metadata, base_id, folder=folder_path)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
