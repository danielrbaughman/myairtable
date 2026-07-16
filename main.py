"""Transitional entry-point shim.

The CLI now lives in the package at src/myairtable/main.py. This shim keeps
`uv run main.py` working, which is how both sibling repos still invoke the
generator:

  ../airtable/generate.sh:24        cd "$MYAIRTABLE_DIR" && uv run main.py ...
  ../myairtable-tests/build.sh:12   cd "$MYAIRTABLE_DIR" && uv run main.py ...

Removed once those move to the published entry point (myairtable-vmj4).
"""

from myairtable.main import app

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
