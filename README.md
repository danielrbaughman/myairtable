# myAirtable

An Airtable code generator, focused on developer experience.

> [!WARNING]
> myAirtable is under active development.

Languages supported:

- Python (via [pyAirtable](https://pyairtable.readthedocs.io/en/stable/))
- TypeScript (via [airtable.js](https://github.com/Airtable/airtable.js))
- JavaScript (via [airtable.js](https://github.com/Airtable/airtable.js))
- Rust (via a custom-built client)
- Swift (via a custom-built client)
- Kotlin (via a custom-built client on [Ktor](https://ktor.io) + [kotlinx.serialization](https://github.com/Kotlin/kotlinx.serialization))
- Java (via a custom-built client on the JDK's `java.net.http.HttpClient` + [Jackson](https://github.com/FasterXML/jackson-databind))
- Go (via a custom-built client on the standard library — `net/http` + `encoding/json`, zero third-party dependencies)

### Kotlin

The generated Kotlin code uses `@Serializable` models, so the **kotlinx.serialization compiler plugin is REQUIRED** — without `kotlin("plugin.serialization")` the generated code will not compile. A known-good Gradle setup (`build.gradle.kts`):

```kotlin
plugins {
    kotlin("jvm") version "2.2.20"
    kotlin("plugin.serialization") version "2.2.20" // REQUIRED for the generated @Serializable models
}

sourceSets {
    main {
        kotlin.srcDir("path/to/generated/output") // wherever you generate into
    }
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("io.ktor:ktor-client-core:3.2.3")
    implementation("io.ktor:ktor-client-cio:3.2.3")
}
```

### Java

The generated Java code targets **Java 21+** (sealed interfaces, records, pattern-matching switch) and is a plain blocking API (cheap on virtual threads). It only needs Jackson databind on the classpath:

```kotlin
java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

sourceSets {
    main {
        java.srcDir("path/to/generated/output") // wherever you generate into
    }
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.2")
}
```

> [!IMPORTANT]
> Do NOT register `jackson-datatype-jsr310` (or call `findAndRegisterModules()`) on the runtime's mapper — the bundled `AirtableJacksonModule` owns `Instant`/`Duration` encoding (Airtable durations are numeric seconds, not ISO `PT…` strings).

Models are mutable POJOs created through a generated `Builder` (the Java analog of the other targets' named arguments): `PrimaryModel.builder().primaryKey("x").build()`. Bulk deletes are named `deleteAll(ids)` / `deleteModels(models)` because Java's type erasure forbids overloading `delete(List<String>)` against `delete(List<Model>)`.

#### Error handling

Every failure is an `AirtableException` — a sealed, **unchecked** hierarchy (checked exceptions would poison every generated signature). The subtypes are `Http` (non-2xx, with `statusCode()`/`body()`), `Api` (a structured Airtable error envelope, with `code()`/`apiMessage()`), `RateLimited` (429, with `retryAfterSeconds()`), `Decoding`, `Network`, `InvalidUrl`, and `MissingCredentials`. Catch the base type for everything, or a specific subtype for targeted handling:

```java
try {
    var contacts = airtable.primary().get();
} catch (AirtableException.RateLimited e) {
    // Only reached after retries are exhausted (see below).
    log.warn("rate limited; retry after {}s", e.retryAfterSeconds());
} catch (AirtableException e) {
    log.error("airtable call failed", e);
}
```

Because the hierarchy is sealed, you can also pattern-match exhaustively with a `switch` (Java 21):

```java
String describe(AirtableException e) {
    return switch (e) {
        case AirtableException.Http h -> "HTTP " + h.statusCode();
        case AirtableException.Api a -> a.code() + ": " + a.apiMessage();
        case AirtableException.RateLimited r -> "rate limited (" + r.retryAfterSeconds() + "s)";
        case AirtableException.Decoding d -> "decode error";
        case AirtableException.Network n -> "network error";
        case AirtableException.InvalidUrl u -> "bad url";
        case AirtableException.MissingCredentials m -> "missing credentials";
    };
}
```

> [!NOTE]
> 429 and 5xx responses are **automatically retried** with exponential backoff (plus jitter, honoring a server `Retry-After`). `AirtableException.RateLimited` only surfaces once retries are exhausted.

#### Resource lifecycle

`Airtable` (and the underlying `AirtableClient`) implements `AutoCloseable`. A long-lived application should construct **one** `Airtable` and hold it for the process lifetime. For short-lived use, a try-with-resources block is idiomatic:

```java
try (var airtable = new Airtable(baseId, apiKey)) {
    var contacts = airtable.primary().get();
}
```

> [!NOTE]
> `close()` only closes the `HttpClient` the runtime **owns** — when you inject your own `HttpClient` (via the full `AirtableClient` constructor), `close()` is a no-op and the client remains yours to manage.

#### Clearing a field

To clear a field server-side, set it to `null` on a **fetched** model and update it. Dirty-tracking diffs the model against the snapshot taken at fetch time and emits an explicit JSON `null` for the cleared field:

```java
var contact = airtable.primary().get("rec1234567890"); // fetched: carries a snapshot
contact.setSingleLineText(null);
airtable.primary().update(contact); // sends {"fields": {"fld...": null}}, clearing it
```

> [!IMPORTANT]
> This only works on a model **obtained from the table** — it has a snapshot to diff against. A freshly built model (`PrimaryModel.builder()...build()`) has no snapshot, so a `null` field is simply omitted from the create payload rather than sent as an explicit clear.

#### Filtering by formula

Filter with the per-field `f` accessor and pass the resulting formula string via `AirtableQuery.withFormula`:

```java
var bobs = airtable.primary()
    .get(new AirtableQuery().withFormula(PrimaryModel.f.singleLineText.contains("Bob")));
```

Text fields expose `eq`/`neq`/`contains`/`startsWith`/`endsWith`/`regexMatch` (etc.); number fields expose `eq`/`neq`/`greaterThan`/`lessThan`/`between` (etc.). Combine clauses with the `Formulas` combinators `and` / `or` / `not` / `xor`:

```java
var formula = Formulas.and(
    PrimaryModel.f.singleLineText.contains("Bob"),
    PrimaryModel.f.numberInt.greaterThan(10));
var results = airtable.primary().get(new AirtableQuery().withFormula(formula));
```

#### Upsert

`upsert(model, mergeOnFieldIds)` inserts or updates a record, matching on the given field IDs. It returns an `OrmTable.UpsertResult<T>` exposing `.model()` (the merged record) and `.wasCreated()` (insert vs update). Merge keys come from the generated `{Table}Fields` ID constants:

```java
var result = airtable.primary().upsert(
    PrimaryModel.builder().primaryKey("alice@example.com").build(),
    List.of(PrimaryFields.primaryKeyId));
if (result.wasCreated()) {
    log.info("created {}", result.model().getId());
}
```

### Go

The generated Go code targets **Go 1.21+** and depends on the **standard library only** (`net/http` + `encoding/json` — no third-party modules). All files (the static runtime and the generated code) live in one flat `package airtable`, and the generator emits **no** `go.mod` — the consuming project owns its module and imports the generated package:

```go
import airtable "yourmodule/path/to/output"

at := airtable.NewWithBase(apiKey, baseID, 0) // cacheSeconds; 0 disables caching
```

Idioms:

- **Models** are structs with `json:"fldID"` tags; optional fields are pointers (`*string`, `*float64`, …) so absent and cleared are distinguishable. Build them with the pointer helpers: `airtable.PrimaryModel{PrimaryKey: airtable.String("x")}`.
- **`context.Context`** is the first argument of every I/O method: `at.Primary.GetOne(ctx, id)`, `rec.Save(ctx)`.
- **Errors are returned, never panicked** — typed errors via `errors.As` (`*airtable.APIError`, `*airtable.RateLimitError`, …) and sentinels via `errors.Is` (`airtable.ErrNotFound`). 429/5xx are retried with backoff before surfacing.
- **Typed table** layer uses generics: `at.Primary` is a `Table[PrimaryModel, *PrimaryModel]`. Methods follow an explicit `*One`/`*Many` naming convention (Go has no overloading): `GetOne`/`GetMany`, `CreateOne`/`CreateMany`, `UpdateOne`/`UpdateMany`, `DeleteOne`/`DeleteMany`, plus `Upsert` and `.Dict()` for raw access. Per-model fluent `Save`/`Fetch`/`Delete` work on models bound via `at.Primary.Attach(&m)` or returned from the table.
- **Select options** are typed-string constants; **computed fields** decode into `*MaybeSpecialOrError[T]` (read with `.Value()`), lookups/rollups into `*VecOrValue[MaybeSpecialOrError[T]]` (read with `CleanValues`).
- **Filtering**: `at.Primary.GetMany(ctx, (&airtable.Query{}).WithFilterFormula(airtable.PrimaryF.PrimaryKey.Eq("alice@example.com")))`.

Generated code is `gofmt`-clean by construction; format/lint via `gofmt`/`go vet`/`golangci-lint`.

## Features

The following examples are in Python, but most features are supported in every language. See notes in each section for language-specific differences.

> [!NOTE]
> In the examples below, `myairtable_output` stands in for _your_ generated package — the actual import path depends on the output folder you generate into.

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
> For Rust, Swift, Kotlin, and Java, 100% of the code is custom to myAirtable. The convenient linked-record traversal syntax in Python and TS/JS is not (yet?) implemented in these targets — linked records are raw record-ID lists resolved through the linked table's `get`.

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
> For JavaScript, TypeScript, Rust, Swift, Kotlin, and Java, the formula builders output strings, and lack the Python-specific convenience of dunder methods, but are otherwise the same. (Kotlin and Java name the equality pair `eq`/`neq` — `equals` collides with `Any.equals`/`Object.equals` on the JVM.)

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
```

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
  - get the schema, either static (the one used to build the code) or live (from Airtable's API)
- Optional caching
- Optional runtime formula evaluation: if enabled, formula fields have their formula transpiled to native code, to allow runtime (re)evaluation. Supports nearly all formulas (can't do LAST_MODIFIED_TIME or CREATED_TIME).
- MCP Server: Allows agents to analyze your Airtable schema

## Getting Started

Requires Python 3.12+.

1. Clone the repo

2. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

3. Run `uv sync`

4. Add a `.env` file like so:

```
AIRTABLE_API_KEY=your_airtable_api_key_here
AIRTABLE_BASE_ID=app1234567890
```

5. Run `uv run main.py --help` to see all commands

## MCP Server

myAirtable includes an MCP server that exposes read-only tools for Airtable schema introspection and analysis.

### Setup

Add the following to your MCP client config (e.g. `claude_desktop_config.json` for Claude Desktop, or `.claude/settings.json` for Claude Code):

```json
{
	"mcpServers": {
		"myairtable": {
			"command": "uv",
			"args": ["run", "--directory", "/path/to/myairtable", "python", "mcp_server.py"],
			"env": {
				"AIRTABLE_API_KEY": "your_airtable_api_key_here",
				"AIRTABLE_BASE_ID": "app1234567890"
			}
		}
	}
}
```

If you have a `.env` file configured (see step 4 above), you can omit the `env` block.

### Tools on the CLI

Every MCP tool is also a CLI subcommand under `myairtable tools` — handy for scripting,
piping to `jq`, or testing without an MCP client:

```bash
uv run main.py tools list-tables            # public meta-API tools
uv run main.py tools transpile Jobs "Total" --language python
uv run main.py tools get-view Contacts "Active"   # internal-API tools
uv run main.py tools --help                 # list all commands
```

Output is JSON by default (`--pretty` for rich rendering). Add `--save` (before the
subcommand) to offload large results to `.data/internal_api/` and print the envelope,
mirroring the MCP server. The same `schema_tools.py` / internal `tools.py` functions back
both the MCP tools and these commands.

## Live view state (internal API, optional)

The `get_view` / `get_view_sections` MCP tools and the `myairtable tools ...` CLI commands
return live view definitions (filters, sorts, grouping, column order/visibility) that the
public meta API does not expose. They use Airtable's **internal, unofficial** web-client
API — endpoints can break without notice; failures degrade to structured errors and never
affect the public-API features above.

Setup (opt-in):

1. `uv sync --group internal && uv run playwright install firefox`
2. Add `AIRTABLE_EMAIL` and `AIRTABLE_PASSWORD` to `.env` (email+password account, no 2FA).
   ⚠️ This stores a real password, not a revocable token — use a dedicated account if possible.
3. That's it — tools auto-authenticate via a scripted headless login and the session
   persists (~1 year) at `~/.myairtable/internal-session.json`. `uv run main.py login --headful`
   forces a fresh login with a visible browser for debugging.

See `docs/airtable-internal-api.md` for the endpoint reference and spike findings.

### Large results are saved to disk

Many tools can return large payloads (whole-base scans, full automation config dumps). When a
result exceeds the inline limit (default 16 KB; override with `MYAIRTABLE_INLINE_MAX_BYTES`),
the **full** result is written to a gitignored `.data/internal_api/<tool>__<args>.json` and the
caller receives a small envelope instead:

```json
{ "saved_to": "...", "bytes": 412934, "record_count": 287,
  "summary": { ... }, "schema": { ...compact shape skeleton... }, "note": "..." }
```

`schema` is a depth-capped structural skeleton of the file (keys → type tags, arrays → length +
element shape) — enough to `jq`/`grep` the file without re-running the tool. This applies to
**all** MCP tools via a server middleware. From the CLI, add `--save` (e.g.
`myairtable tools --save list-automations`) to exercise the same path. Note: `audit_shares`
writes share-URL tokens to that local file.

## License

[MIT](LICENSE)
