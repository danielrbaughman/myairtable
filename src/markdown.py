from datetime import datetime
from pathlib import Path
from typing import Literal

from rich import print

from .helpers import Paths, sanitize_for_markdown
from .meta import Base, Field, Table
from .write_to_file import WriteToFile


class WriteToMarkdownFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="markdown")

    def code_block(self, text: str, language: str = ""):
        self.line(f"```{language}")
        self.line(text)
        self.line("```")

    def separator(self):
        self.line("***")

    def header(self, text: str, level: int = 1):
        self.line(f"{'#' * level} {text}")

    def list_item(self, text: str, indent: int = 0):
        self.line(f"{'    ' * indent}- {text}")

    def table(self, data: list[dict[str, str]]):
        if not data:
            return

        # Header
        headers = data[0].keys()
        self.line("| " + " | ".join(headers) + " |")
        self.line("| " + " | ".join(["---"] * len(headers)) + " |")

        # Rows
        for row in data:
            self.line("| " + " | ".join(row[h] for h in headers) + " |")

    def callout(self, text: str, title: str):
        match title.lower():
            case "note":
                self.line("> [!NOTE] ")
            case "warning":
                self.line("> [!WARNING] ")
            case "tip":
                self.line("> [!TIP] ")
            case _:
                self.line(f"> {title}" if title else ">")
        self.line(">")
        self.line(f"> {text}")

    def note(self, text: str):
        self.callout(text, title="note")

    def warning(self, text: str):
        self.callout(text, title="warning")

    def tip(self, text: str):
        self.callout(text, title="tip")

    def quote(self, text: str):
        lines: list[str] = text.splitlines()
        for line in lines:
            self.line(f"> {line}")


# region MAIN
def generate_markdown(base: Base, output_folder: Path) -> None:
    print("Generating Markdown code")

    write_tables(base, output_folder)
    write_fields(base, output_folder)
    write_index(base, output_folder)

    print("[green] - Markdown code generation complete.[/]")
    print("")


def write_tables(base: Base, output_folder: Path) -> None:
    for table in base.tables:
        folder: Path = output_folder / Paths.DOCS / "tables"
        folder.mkdir(parents=True, exist_ok=True)

        with WriteToMarkdownFile(path=folder / f"{table.name_snake()}.md") as write:
            write.header(f"{table.name}", level=1)
            write.list_item(f"**Airtable ID:** `{table.id}`")
            write.list_item(f"**Number of Fields:** {len(table.fields)}")
            write.list_item(f"**Number of Views:** {len(table.views)}")
            write.line_empty()

            if len(table.linked_tables()) > 0:
                write.header(f"Linked Tables ({len(table.linked_tables())})", level=5)
                for t in table.linked_tables():
                    write.list_item(f"[{t.name_markdown()}](../tables/{t.name_snake()}.md)")

            write.header("Diagram", level=5)
            write.code_block(mermaid_table(table), language="mermaid")
            write.line_empty()

            write.header(f"Fields ({len(table.fields)})", level=5)
            for field in table.fields:
                write.line(f"![{field.name_markdown()}](../fields/{table.name_snake()}/{field.name_snake()}.md)")
                write.line_empty()
                write.separator()
                write.line_empty()

            write.header(f"Views ({len(table.views)})", level=5)
            write.table(
                [
                    {
                        "Name": view.name_markdown(),
                        "ID": view.id,
                        "Type": view.type,
                    }
                    for view in table.views
                ]
            )


def write_fields(base: Base, output_folder: Path) -> None:
    for table in base.tables:
        for field in table.fields:
            folder: Path = output_folder / Paths.DOCS / "fields" / table.name_snake()
            folder.mkdir(parents=True, exist_ok=True)

            with WriteToMarkdownFile(path=folder / f"{field.name_snake()}.md") as write:
                write.header(f"{field.name_markdown()}", level=1)

                write.list_item(f"**Airtable ID:** `{field.id}`")
                write.list_item(f"**Table:** [{table.name_markdown()}](../../tables/{table.name_snake()}.md)")
                write.list_item(f"**Type:** #{field.type}")

                if field.is_link_or_linked_value() and field.options:
                    if linked_table := field.linked_table():
                        write.list_item(f"**Linked Table:** [{linked_table.name_markdown()}](../../tables/{linked_table.name_snake()}.md)")
                    if field.is_lookup_rollup() and field.options.record_link_field_id:
                        lookup_id = field.options.record_link_field_id
                        lookup_field = table.field_by_id(lookup_id)
                        if lookup_field:
                            write.list_item(
                                f"**Linked via:** [{lookup_field.name_markdown()}](../../fields/{table.name_snake()}/{lookup_field.name_snake()}.md)"
                            )

                if field.type == "count":
                    if counted_field := field.counted_field():
                        write.list_item(
                            f"**Counts Records in:** [{counted_field.name_markdown()}](../../fields/{table.name_snake()}/{counted_field.name_snake()}.md)"
                        )

                if field.description:
                    write.line_empty()
                    write.header("Description", level=5)
                    write.quote(sanitize_for_markdown(field.description))
                    write.line_empty()

                if not field.is_valid():
                    write.line_empty()
                    write.warning("Field is #invalid")

                if field.referenced_fields():
                    write.header("Linked Fields", level=5)
                    write.code_block(mermaid_field(field), language="mermaid")
                    write.line_empty()

                if field.type == "formula":
                    write.header("Formula", level=5)
                    write.code_block(field.formula(sanitized=True))
                    write.line_empty()

                    write.header(f"Field Linked via Formula ({len(field.get_field_ids_from_formula())})", level=5)
                    for id in field.get_field_ids_from_formula():
                        if linked_field := table.field_by_id(id):
                            write.list_item(f"[{linked_field.name_markdown()}](../../fields/{table.name_snake()}/{linked_field.name_snake()}.md)")
                    write.line_empty()

                    write.header("Formula Diagram", level=5)
                    write.code_block(mermaid_formula(field), language="mermaid")
                    write.line_empty()

                if (field.type == "singleSelect" or field.type == "multipleSelects") and field.options and field.options.choices:
                    write.header("Options", level=5)
                    for option in field.options.choices:
                        write.list_item(f"{option.name_markdown()}")
                    write.line_empty()

                if field.type == "lastModifiedTime":
                    ref_fields = field.referenced_fields()
                    write.header(f"**Monitors {len(ref_fields)} Field(s)**", level=5)
                    for ref_field in field.referenced_fields():
                        write.list_item(f"[{ref_field.name_markdown()}](../../fields/{table.name_snake()}/{ref_field.name_snake()}.md)")


def write_index(base: Base, output_folder: Path) -> None:
    with WriteToMarkdownFile(path=output_folder / Paths.DOCS / "index.md") as write:
        write.line(f"*Last Updated:* {datetime.now().strftime('%Y-%m-%d')}")
        write.line_empty()
        write.line("# Airtable Documentation")
        write.list_item(f"**Total Tables:** {len(base.tables)}")
        write.list_item(f"**Total Fields:** {sum(len(table.fields) for table in base.tables)}")
        write.list_item(f"**Total Views:** {sum(len(table.views) for table in base.tables)}")
        write.line_empty()
        write.header(f"Tables ({len(base.tables)})", level=5)
        for table in base.tables:
            write.list_item(f"[{table.name}](tables/{table.name_snake()}.md)")
        write.code_block(mermaid_base(base), language="mermaid")
        write.line_empty()


class WriteToMermaidFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="mermaid")

    def flowchart(self, direction: Literal["TD", "LR", "BT", "RL"] = "TD"):
        self.line(f"flowchart {direction}")

    def box(self, id: str, text: str, indent: int = 1):
        self.line_indented(f'{id}["{text}"]', indent=indent)

    def link(self, from_id: str, to_id: str, label: str = "", indent: int = 1):
        if label:
            self.line_indented(f"{from_id} -->|{label}| {to_id}", indent=indent)
        else:
            self.line_indented(f"{from_id} --> {to_id}", indent=indent)


def mermaid_base(base: Base) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart()
    for table in base.tables:
        write.box(table.id, table.name_markdown(), indent=1)
        for t in table.linked_tables():
            write.link(table.id, t.id, indent=2)

    return "\n".join(write.lines)


def mermaid_table(table: Table) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart("LR")
    for field in table.fields:
        write.box(field.id, field.name_markdown())
        for f in field.referenced_fields():
            write.link(field.id, to_id=f.id, indent=2)

    return "\n".join(write.lines)


def mermaid_field(field: Field) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart("LR")
    write.box(field.id, field.name_markdown())
    for f in field.referenced_fields():
        write.box(f.id, f.name_markdown())
        write.link(field.id, to_id=f.id, indent=2)

    return "\n".join(write.lines)


def mermaid_formula(field: Field) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart("LR")
    write.box(field.id, field.name_markdown())

    def field_link(fld: Field):
        write.box(fld.id, fld.name_markdown())
        for ref_fld in fld.referenced_fields():
            write.link(fld.id, to_id=ref_fld.id, indent=2)
            field_link(ref_fld)

    field_link(field)

    return "\n".join(write.lines)
