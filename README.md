# myAirtable

An Airtable code generator, focused on developer experience.

> [!WARNING]
> myAirtable is under active development.

Languages supported:

- Python (via [pyAirtable](https://pyairtable.readthedocs.io/en/stable/))
- TypeScript (via [airtable.js](https://github.com/Airtable/airtable.js))
- JavaScript (via [airtable.js](https://github.com/Airtable/airtable.js))
- Rust (via a custom-built client)

## Features

The following examples are in Python, but most features are suppported in every language. See notes in each section for language-specific differences.

### ORM Models

myAirtable generates strongly-typed RecordDicts and ORM classes, intended for use with the pyAirtable library.

```python
# Fully-typed versions of pyAirtable's RecordDict TypedDict class
class ContactsRecordDict(RecordDict):
  fields: dict[ContactsField, Any] # ContactsFields is a Literal of the fields names in the Contacts table

nanm = contact["fields"]["Name"] # your IDE will suggest "Name"

# Instance of pyAirtable's ORM
class ContactsModel(Model):
  name: SingleLineTextField = SingleLineTextField(field_name="fld123")
  address: MultiLineTextField = MultiLineTextField(field_name="fld789")
  # etc

name = contact.name
```

> [!NOTE]
> For JavaScript & TypeScript, the ORM models are custom to myAirtable, rather than drawn from Airtable.js, though they use Airtable.js under-the-hood, and contain methods for conversion to/from Airtable.js's "Record" class.
>
> For Rust, 100% of the code is custom to myAirtable. Convenient linked-record traversal like that in Python and TS/JS is not implemented in Rust; they are just string ids here.

### Formula Builders

myAirtable also generates formula builders, for use when filtering by formula. pyAirtable already includes decent formula builders, but their options are currently limited to simple operations (e.g. =, >, <, etc), without any type-specific operations. myAirtable's formula builders include additional operations (e.g. "string contains", "date is N days ago", etc). You can access the myAirtable formula helpers from the `.f` property on each ORM class. myAirtable's formula builders are fully compatible with pyAirtable's formula builders.

```python
from myairtable_output import Airtable, AND, OR, ContactsModel

formula: str = AND(
  (ContactsModel.f.first_name.contains("Bob") & ContactsModel.f.last_name == "Smith"),
  ContactsModel.f.birthday.after().years_ago(30),
  ContactsModel.f.birthday < "2019-04-01"
  (ContactsModel.f.age < 10 | ContactsModel.f.age == 12 | ContactsModel.f.age > 15),
  "{fld1234567890}='you can also put raw strings here'",
)

Airtable().contacts.get(formula=formula)
```

> [!NOTE]
> For JavaScript, TypeScript, and Rust, the formula builders output strings, and lack the Python-specific convenience of dunder methods, but are otherwise the same.

### Table/CRUD Wrappers

Finally, myAirtable generates custom lightweight wrapper classes, which expose pyAirtable's CRUD methods with strongly-typed kwargs, and provide easy access to the tables through a simple interface.

```python
from myairtable_output import Airtable, ContactsModel, ContactsRecordDict

airtable = Airtable()

# CRUD operations for pyAirtable ORMs
contact: ContactsModel = airtable.contacts.get("rec1234567890")
contact.name = "Bob"
contact.save() # pyAirtable's ORM models have handy functions like .save()
airtable.contacts.update(contact) # or you can use myAirtable's wrapper if you prefer that syntax

# table.get() method has kwargs for most of pyAirtable's options, which are otherwise less clear. View and Fields kwargs are typed.
contacts: list[ContactsModel] = airtable.contacts.get(view="Family & Friends", fields=["Name", "Age"])
for contact in contacts
	contact.age = contact.age + 1
  contact.save()

# CRUD operations for pyAirtable RecordDicts
contact: ContactsRecordDict = airtable.contacts.dict.get("rec1234567890")
contact["fields"]["name"] = "Joe"
airtable.contacts.dict.update(contact)
```

> [!NOTE]
> For JavaScript & TypeScript, the equivalents of `.dict` are integrated into the standard CRUD operations. They will return/accept the myAirtable's `AirtableModel` classes, Airtable.js's `Record<FieldSet>` class, or a plain interface containing the json data.

### Name-locking and custom names

myAirtable optionally generates CSV files containing the names/ids of the tables and fields, including the "property name" or "model name" (for the ORM models) that they will be given in myAirtable's output. These CSV files, if present in the destination folder, will be used as the source of truth for table, model, and field names in the generated code. They can thus be used to prevent class/property names from changing unexpectedly when someone else changes a field name in Airtable, or for customizing the class/property names as they appear in code, if you prefer a different name for a given table/field. They can also be handy for resolving duplicate property name issues if that happens.

### Documentation via Markdown

myAirtable also includes support for generating documentation for your Airtable base, written in Markdown, intended for use in Obsidian. This documentation includes:

- Files for every table & field, with metadata for each.
- Tags for each field type for easy sorting/filtering
- Obsidian links between related tables/fields, whether by link, lookup, rollup, or formula. This make the graph look pretty neat :)
- For formula fields, the formulas are presented in a variety of ways, most notably:
  - A "flattened" version of the formula. If the formulas references anoher formula (etc), the whole thing is shown.
  - A formatted and syntax-colored version of the formula, for easy readability.
  - A [Mermaid](https://mermaid.ai) representation of the formula.

### Extra Goodies (because I can't stop coding...)

- All the types: just about everything fromt the schema has a constant/dict/type for convenience. Want an array of the options for a select field? How about a map between field ids and names? Or perhaps a union type representing all table names? It's all in there.
- Convenience functions to:
  - build an Airtable URL for base/table/view/record
  - get the schema, either static (the one used to build the code) or live (from Airtable's API)
- Optional caching
- Optional runtime formula evaluation: if enabled, formula fields have their formula transpiled to native code, to allow runtime (re)evaluation.
- MCP Server: Allows agents to analyze your Airtable schema

## Getting Started

1. Clone the repo

2. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

3. Run `uv sync`

4. Add a `.env` file like so:

```
AIRTABLE_API_KEY=your_airtable_api_key_here
AIRTABLE_BASE_ID=app1234567890
```

5. Run `uv run main.py --help` to see all commands
