import time
from datetime import datetime
from pathlib import Path

from rich import print
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from src.mermaid import mermaid_base, mermaid_formula

from . import timer
from .helpers import Paths, sanitize_for_markdown
from .mermaid_to_image import mermaid_to_svg
from .meta import Base
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
def generate_markdown(
    base: Base,
    output_folder: Path,
    svg_enabled: bool = True,
) -> None:
    start = time.time()
    print("Generating Markdown code")

    # Pre-create all folders once before generation
    tables_folder = output_folder / Paths.DOCS / "tables"
    tables_folder.mkdir(parents=True, exist_ok=True)
    for table in base.tables:
        fields_folder = output_folder / Paths.DOCS / "fields" / table.name_snake()
        fields_folder.mkdir(parents=True, exist_ok=True)

    # Create diagrams directory for SVG files
    diagrams_dir: Path | None = None
    svg_cache_dir: Path | None = None
    if svg_enabled:
        diagrams_dir = output_folder / Paths.DOCS / "diagrams"
        diagrams_dir.mkdir(parents=True, exist_ok=True)
        svg_cache_dir = output_folder / ".svg_cache"
        svg_cache_dir.mkdir(parents=True, exist_ok=True)

    with timer.timer("Markdown: write_tables"):
        write_tables(base, output_folder)

    with timer.timer("Markdown: write_fields"):
        write_fields(base, output_folder, svg_enabled, diagrams_dir, svg_cache_dir)

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


def write_fields(
    base: Base,
    output_folder: Path,
    svg_enabled: bool = True,
    diagrams_dir: Path | None = None,
    svg_cache_dir: Path | None = None,
) -> None:
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn()) as progress:
        progress_task = progress.add_task("Generating field documentation...", total=sum(len(t.fields) for t in base.tables))
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
                                if field.formula(condense=True) != field.formula(flatten=True, condense=True):
                                    write.header("Formula (Flattened)", level=5)
                                    write.line("*Formula with nested formulas expanded*")
                                    write.html(field.formula(sanitized=True, flatten=True, format=True, highlight=True))
                                    write.line_empty()

                            with timer.timer("Markdown: write_field: formula: raw"):
                                write.header("Formula (Raw)", level=5)
                                write.code_block(field.formula(sanitized=True, condense=True))
                                write.line_empty()

                            with timer.timer("Markdown: write_field: formula: diagram"):
                                write.header("Formula Diagram", level=5)
                                mermaid_code = mermaid_formula(field)
                                with timer.timer("Markdown: write_field: formula: diagram: svg generation"):
                                    if svg_enabled and diagrams_dir and svg_cache_dir:
                                        svg_content = mermaid_to_svg(mermaid_code, svg_cache_dir, field.id)
                                        if svg_content:
                                            svg_path = diagrams_dir / f"{field.id}.svg"
                                            svg_path.write_text(svg_content)
                                            write.line(f"[SVG](../../diagrams/{field.id}.svg)")
                                        else:
                                            write.warning("SVG generation failed - showing mermaid source only")
                                write.code_block(mermaid_code, language="mermaid")
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
                progress.advance(progress_task)


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
