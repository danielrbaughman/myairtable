# myAirtable

A code generator for [pyAirtable](https://pyairtable.readthedocs.io/en/stable/).

## Output

myAirtable generates strongly-typed dicts, ORM classes, and Pydantic models, all intended for use with the pyAirtable library.

```python
# TODO
```

myAirtable also generates typed formula helpers, for use when filtering by formula. pyAirtable already includes decent formula builders, but their options are limited to simple operations (e.g. =, >, <, etc). myAirtable's formula helpers include additional operations (e.g. "string contains", "date is N days ago", etc)

```python
# TODO
```

Finally, myAirtable generates custom lightweight wrapper classes, which expose pyAirtable's CRUD methods with strongly-typed kwargs, and provide easy access to the tables through a simple interface.

```python
# TODO
```

## Name-locking and custom names

myAirtable optionally generates CSV files containing the names/ids of the tables and fields, including the "property name" that they will be given in myAirtable's output. These CSV files, if present in the destination folder, will be used as the source of truth for table+field names in the generated code. They can thus be used to prevent class/property names from changing unexpectedly when someone else changes a field name in Airtable, or for customizing the class/property names as they appear in code, if you prefer a different name for a given table/field. They can also be handy for resolving duplicate property name issues if that happens.

```python
# TODO
```

## Getting Started

1. Clone the repo
2. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. Run `uv sync`
4. Add a `.env` file with `AIRTABLE_API_KEY=your_airtable_api_key_here`
5. Run `uv run main.py --help` to see all commands

## Notable Options

`uv run main.py py`

- `--fresh`: Regenerates the name-locking CSVs from scratch, rather than using the existing ones.
- `--formulas`: You can choose not to include myAirtable's formula helpers in the output.
- `--wrapper`: You can choose to not include myAirtable's table/base wrapper classes in the output.
- `--validation`: myAirtable uses Pydantic models under the hood for type validation in the pyAirtable ORM models. You can choose to disable this.
