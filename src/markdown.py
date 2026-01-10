import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from rich import print

from . import timer
from .helpers import Paths, sanitize_for_markdown
from .meta import Base, Field
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

    def html(self, text: str):
        self.line('<div style="font-family: monospace; white-space: pre-wrap; padding: 8px; border-radius: 4px; overflow-x: auto;">')
        self.line(text)
        self.line("</div>")


# region MAIN
def generate_markdown(base: Base, output_folder: Path) -> None:
    start = time.time()
    print("Generating Markdown code")

    # Pre-create all folders once before generation
    tables_folder = output_folder / Paths.DOCS / "tables"
    tables_folder.mkdir(parents=True, exist_ok=True)
    for table in base.tables:
        fields_folder = output_folder / Paths.DOCS / "fields" / table.name_snake()
        fields_folder.mkdir(parents=True, exist_ok=True)

    with timer.timer("Markdown: write_tables"):
        write_tables(base, output_folder)

    with timer.timer("Markdown: write_fields"):
        write_fields(base, output_folder)

    with timer.timer("Markdown: write_index"):
        write_index(base, output_folder)

    print("[green] - Markdown code generation complete.[/]")
    print("")
    elapsed = time.time() - start
    print(f"[dim]  » Elapsed time: {elapsed:.2f}s[/]")


def write_tables(base: Base, output_folder: Path) -> None:
    folder: Path = output_folder / Paths.DOCS / "tables"
    for table in base.tables:
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
        folder: Path = output_folder / Paths.DOCS / "fields" / table.name_snake()
        for field in table.fields:
            with WriteToMarkdownFile(path=folder / f"{field.name_snake()}.md") as write:
                with timer.timer("Markdown: write_field: headers"):
                    write.header(f"{field.name_markdown()}", level=1)

                    write.list_item(f"**Airtable ID:** `{field.id}`")
                    write.list_item(f"**Table:** [{table.name_markdown()}](../../tables/{table.name_snake()}.md)")
                    write.list_item(f"**Type:** #{field.type}")

                with timer.timer("Markdown: write_field: links"):
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

                with timer.timer("Markdown: write_field: count"):
                    if field.type == "count":
                        if counted_field := field.counted_field():
                            write.list_item(
                                f"**Counts Records in:** [{counted_field.name_markdown()}](../../fields/{table.name_snake()}/{counted_field.name_snake()}.md)"
                            )

                with timer.timer("Markdown: write_field: description"):
                    if field.description:
                        write.line_empty()
                        write.header("Description", level=5)
                        write.quote(sanitize_for_markdown(field.description))
                        write.line_empty()

                    if not field.is_valid():
                        write.line_empty()
                        write.warning("Field is #invalid")

                with timer.timer("Markdown: write_field: formula"):
                    if field.type == "formula":
                        with timer.timer("Markdown: write_field: formula: highlighted"):
                            write.header("Formula", level=5)
                            write.html(field.formula(sanitized=True, format=True, highlight=True))
                            write.line_empty()

                        with timer.timer("Markdown: write_field: formula: flattened + highlighted"):
                            write.header("Formula (Flattened)", level=5)
                            write.html(field.formula(sanitized=True, flatten=True, format=True, highlight=True))
                            write.line_empty()

                        with timer.timer("Markdown: write_field: formula: raw"):
                            write.header("Formula (Raw)", level=5)
                            write.code_block(field.formula(sanitized=True, condense=True))
                            write.line_empty()

                        with timer.timer("Markdown: write_field: formula: diagram"):
                            write.header("Formula Diagram", level=5)
                            write.code_block(mermaid_formula(field), language="mermaid")
                            write.line_empty()

                        with timer.timer("Markdown: write_field: formula: field links"):
                            write.header(f"Field Linked via Formula ({len(field.referenced_fields())})", level=5)
                            for f in field.referenced_fields():
                                if linked_field := table.field_by_id(f.id):
                                    write.list_item(
                                        f"[{linked_field.name_markdown()}](../../fields/{table.name_snake()}/{linked_field.name_snake()}.md)"
                                    )
                            write.line_empty()

                with timer.timer("Markdown: write_field: options"):
                    if (field.type == "singleSelect" or field.type == "multipleSelects") and field.options and field.options.choices:
                        write.header("Options", level=5)
                        for option in field.options.choices:
                            write.list_item(f"{option.name_markdown()}")
                        write.line_empty()

                with timer.timer("Markdown: write_field: monitors"):
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

    def _node(self, id: str, label: str, left_delimiter: str, right_delimiter: str, indent: int = 1):
        self.line_indented(f'{id}{left_delimiter}"{label}"{right_delimiter}', indent=indent)

    def node(
        self,
        id: str,
        label: str,
        type: Literal[
            "Square",
            "Round",
            "Stadium",
            "Subroutine",
            "Cylinder",
            "Circle",
            "Rhombus",
            "Hexagon",
            "Parallelogram",
            "Parallelogram Alt",
            "Trapezoid",
            "Trapezoid Alt",
            "Double Circle",
        ] = "Square",
        indent: int = 1,
    ):
        match type:
            case "Square":
                self._node(id, label, "[", "]", indent=indent)
            case "Round":
                self._node(id, label, "(", ")", indent=indent)
            case "Stadium":
                self._node(id, label, "([", "])", indent=indent)
            case "Subroutine":
                self._node(id, label, "[[", "]]", indent=indent)
            case "Cylinder":
                self._node(id, label, "[(", ")]", indent=indent)
            case "Circle":
                self._node(id, label, "((", "))", indent=indent)
            case "Rhombus":
                self._node(id, label, "{", "}", indent=indent)
            case "Hexagon":
                self._node(id, label, "{{", "}}", indent=indent)
            case "Parallelogram":
                self._node(id, label, "[/", "/]", indent=indent)
            case "Parallelogram Alt":
                self._node(id, label, "[\\", "\\]", indent=indent)
            case "Trapezoid":
                self._node(id, label, "[/", "\\]", indent=indent)
            case "Trapezoid Alt":
                self._node(id, label, "[\\", "/]", indent=indent)
            case "Double Circle":
                self._node(id, label, "(((", ")))", indent=indent)
            case _:
                raise ValueError(f"Unknown node type: {type}")

    def link(self, from_id: str, to_id: str, label: str = "", indent: int = 1):
        if label:
            self.line_indented(f"{from_id} -->|{label}| {to_id}", indent=indent)
        else:
            self.line_indented(f"{from_id} --> {to_id}", indent=indent)

    def subgraph(self, id: str, label: str, direction: Literal["TB", "LR", "BT", "RL"] | None = None, indent: int = 1):
        self.line_indented(f"subgraph {id} [{label}]", indent=indent)
        if direction:
            self.line_indented(f"direction {direction}", indent=indent + 1)

    def end(self, indent: int = 1):
        self.line_indented("end", indent=indent)

    def colors(self):
        self.line("%% Colors")
        self.line("classDef pink fill:#FFE0F0,stroke:#CC0066,stroke-width:2px;")
        self.line("classDef purple fill:#F3E6FF,stroke:#6600CC,stroke-width:2px;")
        self.line("classDef blue fill:#D0E6FF,stroke:#0033CC,stroke-width:2px;")
        self.line("classDef lightblue fill:#E0F0FF,stroke:#0066CC,stroke-width:2px;")
        self.line("classDef green fill:#DFFFE0,stroke:#339900,stroke-width:2px;")
        self.line("classDef yellow fill:#FFF8D0,stroke:#CC9900,stroke-width:2px;")
        self.line("classDef orange fill:#FFE6D0,stroke:#CC6600,stroke-width:2px;")
        self.line("classDef red fill:#FFD0D0,stroke:#CC0000,stroke-width:2px;")
        self.line("")

    def color(self, id: str, color: Literal["pink", "purple", "blue", "lightblue", "green", "yellow", "orange", "red"]):
        self.line(f"class {id} {color}")


def mermaid_base(base: Base) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart()
    for table in base.tables:
        write.node(table.id, table.name_markdown(), indent=1)
        for t in table.linked_tables():
            write.link(table.id, t.id, indent=2)

    return "\n".join(write.lines)


def box_label(field: Field) -> str:
    label = f"""
{field.name_markdown()}
_({field.type_friendly()})_
"""
    return label


def mermaid_field(field: Field) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart("LR")
    write.node(field.id, field.name_markdown())
    for f in field.referenced_fields():
        write.node(f.id, f.name_markdown())
        write.link(field.id, to_id=f.id, indent=2)

    return "\n".join(write.lines)


def mermaid_formula(field: Field) -> str:
    write = WriteToMermaidFile(path=Path("/dev/null"))  # Dummy path since we won't write to file
    write.flowchart()
    write.colors()

    visited_fields: set[str] = set()
    fields_by_table: dict[str, list[Field]] = {}  # table_id -> [fields]
    links: list[tuple[str, str]] = []  # (from_id, to_id)

    def collect_fields(fld: Field):
        """Recursively collect all fields and links."""
        if fld.id in visited_fields:
            return
        visited_fields.add(fld.id)
        fields_by_table.setdefault(fld.table.id, []).append(fld)

        for ref_fld in fld.referenced_fields():
            links.append((fld.id, ref_fld.id))
            collect_fields(ref_fld)

    # Pass 1: Collect all fields and links
    collect_fields(field)

    # Pass 2: Render subgraphs with boxes
    for table_id, fields in fields_by_table.items():
        table = fields[0].table
        write.subgraph(table_id, table.name_markdown())
        for fld in fields:
            if fld.is_datetime():
                write.node(fld.id, box_label(fld), type="Circle", indent=2)
                write.color(fld.id, "pink")
            elif fld.is_computed():
                match fld.type:
                    case "formula":
                        write.node(fld.id, box_label(fld), type="Rhombus", indent=2)
                        write.color(fld.id, "red")
                    case "lookup" | "rollup" | "multipleLookupValues":
                        write.node(fld.id, box_label(fld), type="Parallelogram", indent=2)
                        write.color(fld.id, "orange")
                    case _:
                        write.node(fld.id, box_label(fld), type="Trapezoid", indent=2)
                        write.color(fld.id, "yellow")
            else:
                match fld.type:
                    case "multipleRecordLinks":
                        write.node(fld.id, box_label(fld), "Stadium", indent=2)
                        write.color(fld.id, "purple")
                    case "multipleAttachments":
                        write.node(fld.id, box_label(fld), "Cylinder", indent=2)
                        write.color(fld.id, "blue")
                    case "singleSelect" | "multipleSelects":
                        write.node(fld.id, box_label(fld), "Subroutine", indent=2)
                        write.color(fld.id, "green")
                    case _:
                        write.node(fld.id, box_label(fld), indent=2)
        write.end()

    # Pass 3: Render all links (outside subgraphs)
    for from_id, to_id in links:
        write.link(from_id, to_id=to_id)

    return "\n".join(write.lines)
