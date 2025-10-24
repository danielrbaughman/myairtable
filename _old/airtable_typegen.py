import os

from typer import Typer

from src.meta import get_base_meta_data

from .airtable_typegen_python import gen_python
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
