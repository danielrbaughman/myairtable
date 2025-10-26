# myAirtable

A code generator for [pyAirtable](https://pyairtable.readthedocs.io/en/stable/), focused on developer experience.

## Output

myAirtable generates strongly-typed dicts, ORM classes, and Pydantic models, all intended for use with the pyAirtable library.

```python
# Fully-typed versions of pyAirtable's RecordDict TypedDict class
class ContactsRecordDict(RecordDict):
  fields: dict[ContactsField, Any] # ContactsFields is a Literal of the fields names in the Contacts table
  
nane = contact["fields"]["Name"] # your IDE will suggest "Name"

# Instance of pyAirtable's ORM
class ContactsORM(Model):
  name: SingleLineTextField = SingleLineTextField(field_name="fld123")
  address: MultiLineTextField = MultiLineTextField(field_name="fld789")
  # etc

name = contact.name

# A Pydantic representation of the record
class ContactsModel(AirtableBaseModel):
  name: Optional[str] = None # all Pydantic properties are Optional by necessity
  address: Optional[str] = None
  # etc
    
name = contact.name

# myAirtable's ORMs make use of the Pydantic models under-the-hood for type validation
contact.name = 123 # causes a Pydantic validation error
```

myAirtable also generates typed formula helpers, for use when filtering by formula. pyAirtable already includes decent formula builders, but their options are limited to simple operations (e.g. =, >, <, etc). myAirtable's formula helpers include additional operations (e.g. "string contains", "date is N days ago", etc)

```python
from myairtable_output import Airtable, AND, OR, ContactsTextField, ContactsDateField, ContactsNumberField

# there are formula-builder classes for various Airtable fields
# myAirtable generates a typed version for each table

formula: str = AND(
  ContactsTextField("Name").contains("Bob"),
  ContactsDateField("Birthday").is_before("2020-04-01")
  OR(
    ContactsNumberField("Age").is_greater_than(10),
    ContactsNumberField("Age").is_less_than(20)
  ),
  "{fld1234567890}='you can also put raw strings here'"
)

Airtable().contacts.get(formula=formula)
```

Finally, myAirtable generates custom lightweight wrapper classes, which expose pyAirtable's CRUD methods with strongly-typed kwargs, and provide easy access to the tables through a simple interface.

```python
from myairtable_output import Airtable

at = Airtable()

# CRUD operations for pyAirtable ORMs
contact: ContactsORM = at.contacts.get("rec1234567890")
contact.name = "Bob"
contact.save() # pyAirtable's ORM models have handy functions like .save()
at.contacts.update(contact) # or you can use myAirtable's wrapper if you prefer that syntax

# table.get() method has kwargs for most of pyAirtable's options, which are otherwise less clear. View and Fields kwargs are typed.
contacts: list[ContactsORM] = at.contacts.get(view="Family & Friends", fields=["Name", "Age"])
for contact in contacts
	contact.age = contact.age + 1
  contact.save()

# CRUD operations for pyAirtable RecordDicts
contact: ContactsRecordDict = at.contacts.dict.get("rec1234567890")
contact["fields"]["name"] = "Joe"
at.contacts.dict.update(contact)

# CRUD operations for Pydantic models
contact: ContactsModel = at.contacts.model.get("rec1234567890")
contact.name = "Jane"
at.contacts.model.update(contact)
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
