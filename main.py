from typer import Typer

from src import csv, meta

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
app.add_typer(meta.app)
app.add_typer(csv.app)

@app.command(name="py")
def gen_python():
    pass

@app.command(name="ts")
def gen_typescript():
    pass

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app()
