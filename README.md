# myAirtable

An Airtable code generator, focused on developer experience.

Languages supported:

- Python (via [pyAirtable](https://pyairtable.readthedocs.io/en/stable/))
- TypeScript (via [airtable.js](https://github.com/Airtable/airtable.js))
- JavaScript (via [airtable.js](https://github.com/Airtable/airtable.js))
- Rust
- Swift
- Kotlin
- Java
- Go
- C#
- C++

> [!WARNING]
> The Python, JavaScript, and TypeScript versions were all hand-coded, and are abstractions of existing libraries. The other languages use custom-built clients, and were largely AI-generated. All languages are [thoroughly tested](https://github.com/danielrbaughman/myairtable-tests), but only Python, TypeScript, and Rust are battle-tested in production environments. In other words, use at your own risk, and submit a PR if you find a bug.

## Features

The following examples are in Python, but most features are supported in every language, and the api's are roughly the same in each language.

### ORM Models

myAirtable generates strongly-typed RecordDicts and ORM classes, intended for use with the pyAirtable library.

```python
# Fully-typed versions of pyAirtable's RecordDict TypedDict class
class ContactsRecordDict(RecordDict):
  fields: dict[ContactsField, Any] # ContactsField is a Literal of the field names in the Contacts table

name = contact["fields"]["Name"] # your IDE will suggest "Name"

# Instance of pyAirtable's ORM
class ContactsModel(Model):
  name: SingleLineTextField = SingleLineTextField(field_name="fld123")
  address: MultilineTextField = MultilineTextField(field_name="fld789")
  # etc

name = contact.name
```

> [!NOTE]
> For JavaScript & TypeScript, the ORM models are custom to myAirtable, though they still use the Airtable.js client for save/delete, and contain methods for conversion to/from Airtable.js's "Record" class. Also, they use [Zod](https://zod.dev) validation under-the-hood.
>
> For all other languages, 100% of the API-client code is custom to myAirtable.

### Formula Builders

myAirtable also generates formula builders, for use when filtering by formula. pyAirtable already includes decent formula builders, but their options are currently limited to simple operations (e.g. =, >, <, etc), without any type-specific operations. myAirtable's formula builders include additional operations (e.g. "string contains", "date is N days ago", etc). You can access the myAirtable formula helpers from the `.f` property on each ORM class. myAirtable's formula builders are fully compatible with pyAirtable's formula builders.

```python
from myairtable_output import Airtable, AND, OR, ContactsModel

formula: str = AND(
  ContactsModel.f.first_name.contains("Bob") & (ContactsModel.f.last_name == "Smith"),
  ContactsModel.f.birthday.after().years_ago(30),
  ContactsModel.f.birthday < "2019-04-01",
  (ContactsModel.f.age < 10) | (ContactsModel.f.age == 12) | (ContactsModel.f.age > 15),
  "{fld1234567890}='you can also put raw strings here'",
)

Airtable().contacts.get(formula=formula)
```

> [!NOTE]
> For all other languages, the formula builders output strings, and lack the Python-specific convenience of dunder methods, but are otherwise largely the same.

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
for contact in contacts:
  contact.age = contact.age + 1
  contact.save()

# CRUD operations for pyAirtable RecordDicts
contact: ContactsRecordDict = airtable.contacts.dict.get("rec1234567890")
contact["fields"]["name"] = "Joe"
airtable.contacts.dict.update(contact)

# duplicate() copies a record into a brand-new one. Every writable field is copied verbatim
# (primary field included); computed fields are left to Airtable, so the copy gets its own id,
# autonumber and timestamps. Takes a record or a record id, one or many, on either layer.
duplicated: ContactsModel = airtable.contacts.duplicate(contact_id)
duplicates: list[ContactsModel] = airtable.contacts.duplicate([id_a, id_b])

# copy() is the local half of duplicate(): an in-memory, unsaved deep copy of a record.
# Nothing is written until you hand it to create(), so change whatever should differ first.
draft: ContactsModel = contact.copy()
draft.name = "Bob (copy)"
new_contact: ContactsModel = airtable.contacts.create(draft)
```

> [!NOTE]
> `duplicate()` is available in all ten targets. Languages without overloading spell it
> `duplicate_one` / `duplicate_many` / `duplicate_one_by_id` / `duplicate_many_by_ids` (Rust, C++,
> and `DuplicateOne`… in Go), matching how those targets already name the other verbs.
>
> It always re-reads the source from Airtable before copying, so the copy reflects
> current server state. Attachments are copied by URL, which makes Airtable re-ingest each file
> — the copy owns its attachment rather than sharing the original's. Linked records are copied
> as-is; because Airtable links are many-to-many underneath, the copy is added alongside the
> original and the source record's own links are never modified.

> [!NOTE]
> `copy()` is the local counterpart to `duplicate()`, and it lives on the ORM **model** rather
> than the table. `duplicate()` is `fetch + copy + create`; `copy()` is that middle step on its
> own and performs no I/O at all. Available in all ten targets, spelled `Copy()` in Go and C#
> and `copy()` everywhere else. There is no `.dict` equivalent — a bare record dict has no ORM
> identity to detach.
>
> The copy carries computed values so it reads like its source, but they are the _source's_
> values: a formula over `RECORD_ID()` shows the original's id until you save, and Airtable
> recalculates the real ones on create. Attachments are reduced to `{url, filename}` — the only
> shape Airtable accepts when inserting, and what makes the new record own its attachment rather
> than aliasing the original's.
>
> Two things to watch, both of which `duplicate()` avoids by re-reading the source first.
> Attachment URLs are signed and expire (~2h), so copying a long-held record can produce one
> whose attachments Airtable can no longer fetch. And copying a record that was fetched with a
> field projection (`fields=[...]`) inserts a record with holes, because the unfetched fields
> are simply absent.

> [!NOTE]
> For JavaScript & TypeScript, the equivalents of `.dict` are integrated into the standard CRUD operations. They will return/accept the myAirtable's `AirtableModel` classes, Airtable.js's `Record<FieldSet>` class, or a plain interface containing the json data.

### Name-locking and custom names

myAirtable optionally generates CSV files containing the names/ids of the tables and fields, including the "property name" or "model name" (for the ORM models) that they will be given in myAirtable's output. These CSV files, if present in the destination folder, will be used as the source of truth for table, model, and field names in the generated code. They can thus be used to prevent class/property names from changing unexpectedly when someone else changes a field name in Airtable, or for customizing the class/property names as they appear in code, if you prefer a different name for a given table/field. They can also be handy for resolving duplicate property name issues if that happens.

### Documentation (Markdown and HTML)

myAirtable also includes support for generating documentation for your Airtable base. There is a version in Markdown (intended for Obsidian) and in HTML (intended as a static website). This documentation includes:

- Files for every table & field, with metadata for each.
- Tags for each field type for easy sorting/filtering
- Links between related tables/fields, whether by link, lookup, rollup, or formula.
- Formula fields are where it really shines. It shows:
  - A "flattened" version of the formula. If the formula references another formula (etc), the whole thing is shown.
  - A formatted and syntax-colored version of the formula, for easy readability.
  - A [Mermaid](https://mermaid.ai) representation of the formula.

### Extra Goodies (because I can't stop coding...)

- All the types: just about everything from the schema has a constant/dict/type for convenience. Want an array of the options for a select field? How about a map between field ids and names? Or perhaps a union type representing all table names? It's all in there.
- Convenience functions to:
  - build an Airtable URL for base/table/view/record
  - get the base schema
- Optional caching
- Optional runtime formula evaluation: if enabled, formula fields have their formula transpiled to native code, to allow runtime (re)evaluation. Supports nearly all formulas (can't do LAST_MODIFIED_TIME or CREATED_TIME).

## Getting Started

Requires Python 3.12+.

### Install

To run the code generator, install with the `cli` extra:

```bash
uv tool install "myairtable[cli]"
myairtable --help
```

Then provide credentials, either as flags (`--base-id`, `--api-key`) or via a `.env`
file in the working directory:

```
AIRTABLE_API_KEY=your_airtable_api_key_here
AIRTABLE_BASE_ID=app1234567890
```

## License

[MIT](LICENSE)
