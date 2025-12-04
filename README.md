# myAirtable

A code generator for [pyAirtable](https://pyairtable.readthedocs.io/en/stable/) (Python) and [airtable.js](https://github.com/Airtable/airtable.js) (TypeScript), focused on developer experience.

> **Warning**  
> myAirtable is under active development.

## Python (pyAirtable)

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

Finally, myAirtable generates custom lightweight wrapper classes, which expose pyAirtable's CRUD methods with strongly-typed kwargs, and provide easy access to the tables through a simple interface.

```python
from myairtable_output import Airtable, ContactsModel, ContactsRecordDict

at = Airtable()

# CRUD operations for pyAirtable ORMs
contact: ContactsModel = at.contacts.get("rec1234567890")
contact.name = "Bob"
contact.save() # pyAirtable's ORM models have handy functions like .save()
at.contacts.update(contact) # or you can use myAirtable's wrapper if you prefer that syntax

# table.get() method has kwargs for most of pyAirtable's options, which are otherwise less clear. View and Fields kwargs are typed.
contacts: list[ContactsModel] = at.contacts.get(view="Family & Friends", fields=["Name", "Age"])
for contact in contacts
	contact.age = contact.age + 1
  contact.save()

# CRUD operations for pyAirtable RecordDicts
contact: ContactsRecordDict = at.contacts.dict.get("rec1234567890")
contact["fields"]["name"] = "Joe"
at.contacts.dict.update(contact)
```

## TypeScript (airtable.js)

myAirtable generates strongly-typed interfaces and ORM classes, intended for use with the airtable.js library.

```typescript
// Fully-typed FieldSet, which can be used with airtable.js's `Record` class
interface ContactFieldSet extends FieldSet {
    "Name"?: string,
    "Age"?: number,
}
interface ContactRecord extends Record<ContactFieldSet>

const name = contact.get("Name");

// Instance of a custom wrapper around airtable.js's `Record` class
export class ContactModel extends AirtableModel<ContactFieldSet> {
  public name?: string;
  public age?: number;
}

const name = contact.name;
```

myAirtable also generates formula builders, for use when filtering by formula. You can access the myAirtable formula helpers from the `.f` property on each ORM class.

```typescript
import { Airtable, AND, OR, ContactsModel } from "./myairtable/output"

const formula: string = AND(
  AND(ContactsModel.f.firstName.contains("Bob"), ContactsModel.f.lastName == "Smith"),
  ContactsModel.f.birthday.after().yearsAgo(30),
  ContactsModel.f.birthday.before("2019-04-01"),
  OR(ContactsModel.f.age.lessThan(10), ContactsModel.f.age.equals(12), ContactsModel.f.age.greaterThan(15),
  "{fld1234567890}='you can also put raw strings here'",
);

const contacts = await new Airtable().contacts.get({ formula: formula });
```

Finally, myAirtable generates custom lightweight wrapper classes, which expose airtable.js's CRUD methods with strongly-typed arguments and options, and provide easy access to the tables through a simple interface.

```typescript
import { Airtable, ContactsModel } from "./myairtable/output";

const at = new Airtable();

// CRUD operations for airtabe.js ORMs
const contact: ContactsModel = await at.contacts.get("rec1234567890");
contact.name = "Bob";
contact.save(); // airtable.js's ORM models have handy functions like .save(), which are exposed in myAirtable's custom ORM wrappers
await at.contacts.update(contact); // or you can use myAirtable's wrapper if you prefer that syntax

// table.get() method has type arguments for most of airtable.js's options, which are otherwise less clear. View and Fields options are typed.
const contacts: ContactsModel[] = await at.contacts.get({ view: "Family & Friends", fields: ["Name", "Age"] });
for (const contact of contacts) {
	contact.age = contact.age + 1;
	contact.save();
}
```

## Name-locking and custom names

myAirtable optionally generates CSV files containing the names/ids of the tables and fields, including the "property name" or "model name" (for the ORM models) that they will be given in myAirtable's output. These CSV files, if present in the destination folder, will be used as the source of truth for table, model, and field names in the generated code. They can thus be used to prevent class/property names from changing unexpectedly when someone else changes a field name in Airtable, or for customizing the class/property names as they appear in code, if you prefer a different name for a given table/field. They can also be handy for resolving duplicate property name issues if that happens.

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

## Notable Options

`uv run main.py py` or `uv run main.py ts`

- `--fresh`: Regenerates the name-locking CSVs from scratch, rather than using the existing ones.
- `--formulas`: You can choose not to include myAirtable's formula builders in the output.
- `--wrapper`: You can choose to not include myAirtable's table/base wrapper classes in the output.
