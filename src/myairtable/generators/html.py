import html
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from rich import print

from ..formulas.formula_formatter import _count_nesting_depth
from ..formulas.formula_tokenizer import TokenType, tokenize_formula
from ..meta import Base
from ..utils.helpers import static_dir
from ..utils.mermaid_to_image import get_cached_svg, mermaid_live_url, mermaid_to_svg, render_svgs_parallel
from ..utils.verbose import verbose
from ..utils.write_to_file import WriteToFile
from .mermaid import mermaid_base, mermaid_formula

# Paths to static files bundled with the project
_STATIC_DIR = static_dir("html")
_STATIC_CSS = _STATIC_DIR / "style.css"
_STATIC_JS = _STATIC_DIR / "script.js"
_TEMPLATE_HEADER = (_STATIC_DIR / "template-header.html").read_text()
_TEMPLATE_FOOTER = (_STATIC_DIR / "template-footer.html").read_text()


def _esc(text: str) -> str:
    """HTML-escape user-provided text."""
    return html.escape(text, quote=True)


def _css_path(depth: int) -> str:
    """Return relative path to style.css from a given folder depth."""
    return "../" * depth + "style.css"


def _link(text: str, href: str) -> str:
    """Return an <a> tag. Text is NOT escaped (caller may include tags)."""
    return f'<a href="{_esc(href)}">{text}</a>'


# Field type -> CSS modifier for colored tags
_TYPE_CATEGORIES: dict[str, str] = {
    "formula": "computed",
    "rollup": "computed",
    "lookup": "computed",
    "multipleLookupValues": "computed",
    "count": "computed",
    "multipleRecordLinks": "link",
    "date": "date",
    "dateTime": "date",
    "createdTime": "date",
    "lastModifiedTime": "date",
    "duration": "date",
    "singleSelect": "select",
    "multipleSelects": "select",
    "checkbox": "select",
    "multipleAttachments": "attachment",
    "singleCollaborator": "collab",
    "multipleCollaborators": "collab",
    "createdBy": "collab",
    "lastModifiedBy": "collab",
    "number": "numeric",
    "percent": "numeric",
    "rating": "numeric",
    "currency": "numeric",
    "autoNumber": "numeric",
}


def _field_type_tag(field_type: str) -> str:
    """Return a <span class="tag tag-{category}"> for a field type."""
    cat = _TYPE_CATEGORIES.get(field_type, "text")
    return f'<span class="tag tag-{cat}">{_esc(field_type)}</span>'


def _formula_complexity(formula: str) -> tuple[str, str]:
    """Return (label, css_class) for a formula's complexity level."""
    depth = _count_nesting_depth(formula)
    tokens = tokenize_formula(formula)
    func_count = sum(1 for t in tokens if t.type == TokenType.FUNCTION)
    ref_count = sum(1 for t in tokens if t.type == TokenType.FIELD_REF)

    score = depth * 3 + func_count + ref_count
    if score <= 5:
        return "simple", "complexity-simple"
    elif score <= 20:
        return "moderate", "complexity-moderate"
    else:
        return "complex", "complexity-complex"


def _formula_complexity_badge(formula: str) -> str:
    """Return a <span> badge for formula complexity."""
    label, css = _formula_complexity(formula)
    return f'<span class="tag {css}">{_esc(label)}</span>'


class WriteToHtmlFile(WriteToFile):
    def __init__(self, path: Path, title: str, css_path: str, breadcrumbs: list[tuple[str, str]] | None = None, depth: int = 0):
        super().__init__(path=path, language="html")
        self._title = title
        self._css_path = css_path
        self._breadcrumbs = breadcrumbs or []
        self._depth = depth

    def _render_breadcrumbs(self) -> str:
        if not self._breadcrumbs:
            return ""
        parts: list[str] = []
        for label, href in self._breadcrumbs[:-1]:
            parts.append(_link(_esc(label), href))
        parts.append(_esc(self._breadcrumbs[-1][0]))
        inner = '<span class="separator">/</span>'.join(parts)
        return f'<nav class="breadcrumbs">\n  {inner}\n</nav>'

    def document_start(self):
        root = "../" * self._depth
        header = _TEMPLATE_HEADER.replace("{{title}}", _esc(self._title))
        header = header.replace("{{css_path}}", _esc(self._css_path))
        header = header.replace("{{root}}", root)
        header = header.replace("{{breadcrumbs}}", self._render_breadcrumbs())
        self.line(header.rstrip())

    def document_end(self):
        root = "../" * self._depth
        footer = _TEMPLATE_FOOTER.replace("{{root}}", root)
        self.line(footer.rstrip())

    def header(self, text: str, level: int = 1):
        self.line(f"<h{level}>{_esc(text)}</h{level}>")

    def header_raw(self, html_content: str, level: int = 1):
        """Header where content is already HTML (e.g. contains links or tags)."""
        self.line(f"<h{level}>{html_content}</h{level}>")

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert title to a URL-friendly anchor id."""
        import re

        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    def section_start(self, title: str, level: int = 5, open: bool = True):
        """Start a collapsible section using <details>/<summary>."""
        open_attr = " open" if open else ""
        slug = self._slugify(title)
        self.line(f'<details{open_attr} id="{slug}">')
        self.line(f'  <summary><h{level}>{_esc(title)}</h{level}><a class="anchor-link" href="#{slug}" title="Copy link to section">#</a></summary>')

    def section_end(self):
        self.line("</details>")

    def list_start(self, css_class: str = ""):
        cls = f' class="{_esc(css_class)}"' if css_class else ""
        self.line(f"<ul{cls}>")

    def list_end(self):
        self.line("</ul>")

    def list_item(self, content: str):
        """Content is raw HTML (caller is responsible for escaping)."""
        self.line(f"  <li>{content}</li>")

    def table(self, data: list[dict[str, str]]):
        if not data:
            return
        headers = list(data[0].keys())
        self.line("<table>")
        self.line("  <thead><tr>")
        for h in headers:
            self.line(f"    <th>{_esc(h)}</th>")
        self.line("  </tr></thead>")
        self.line("  <tbody>")
        for row in data:
            self.line("  <tr>")
            for h in headers:
                self.line(f"    <td>{_esc(row[h])}</td>")
            self.line("  </tr>")
        self.line("  </tbody>")
        self.line("</table>")

    def interactive_table(self, table_id: str, headers: list[str], rows: list[list[tuple[str, str]]], filter_columns: list[int] | None = None):
        """Emit a searchable, sortable, filterable table.

        Args:
            table_id: unique DOM id for the table wrapper
            headers: column header labels
            rows: list of rows, each row is a list of (html_content, sort_value) tuples
            filter_columns: column indices that should get a filter dropdown
        """
        filter_columns = filter_columns or []

        self.line(f'<div class="interactive-wrapper" id="{_esc(table_id)}">')

        # Controls row
        self.line('<div class="interactive-controls">')
        self.line(f'  <input type="text" class="interactive-search" placeholder="Search..." data-target="{_esc(table_id)}">')

        # Filter dropdowns
        for col_idx in filter_columns:
            unique_vals = sorted({row[col_idx][1] for row in rows})
            self.line(f'  <select class="interactive-filter" data-target="{_esc(table_id)}" data-col="{col_idx}">')
            self.line(f'    <option value="">All {_esc(headers[col_idx])}s</option>')
            for val in unique_vals:
                self.line(f'    <option value="{_esc(val)}">{_esc(val)}</option>')
            self.line("  </select>")

        self.line("</div>")

        # Table
        self.line('<table class="interactive">')
        self.line("  <thead><tr>")
        for i, h in enumerate(headers):
            self.line(f'    <th data-col="{i}">{_esc(h)}</th>')
        self.line("  </tr></thead>")
        self.line("  <tbody>")
        for row in rows:
            self.line("  <tr>")
            for i, (html_content, sort_value) in enumerate(row):
                self.line(f'    <td data-sort-value="{_esc(sort_value)}">{html_content}</td>')
            self.line("  </tr>")
        self.line("  </tbody>")
        self.line("</table>")
        self.line("</div>")

    def copyable(self, value: str) -> str:
        """Return an inline <code> element that copies its value on click."""
        return f'<code class="copyable" data-copy="{_esc(value)}" title="Click to copy">{_esc(value)}</code>'

    def code_block(self, text: str, language: str = ""):
        self.line("<pre><code>")
        self.line(_esc(text))
        self.line("</code></pre>")

    def code_block_copyable(self, text: str):
        """A code block that copies its full text on click."""
        self.line(f'<pre class="copyable copyable-block" data-copy="{_esc(text)}"><code>')
        self.line(_esc(text))
        self.line("</code></pre>")

    def separator(self):
        self.line("<hr>")

    def callout(self, text: str, title: str):
        kind = title.lower() if title.lower() in ("note", "warning", "tip") else "note"
        self.line(f'<div class="callout callout-{kind}">')
        self.line(f'  <div class="callout-title">{_esc(title)}</div>')
        self.line(f"  <p>{_esc(text)}</p>")
        self.line("</div>")

    def note(self, text: str):
        self.callout(text, title="Note")

    def warning(self, text: str):
        self.callout(text, title="Warning")

    def tip(self, text: str):
        self.callout(text, title="Tip")

    def quote(self, text: str):
        self.line("<blockquote>")
        for ln in text.splitlines():
            self.line(f"  <p>{_esc(ln)}</p>")
        self.line("</blockquote>")

    def formula_html(self, text: str):
        """Write pre-highlighted formula HTML (already contains <span> tags)."""
        self.line('<div class="formula-display">')
        self.line(text)
        self.line("</div>")

    def paragraph(self, text: str):
        self.line(f"<p>{_esc(text)}</p>")

    def paragraph_raw(self, html_content: str):
        """Paragraph where content is already HTML."""
        self.line(f"<p>{html_content}</p>")

    def svg_embed(self, src: str, alt: str = "Diagram"):
        self.line('<div class="diagram-container">')
        self.line(f'  <div class="diagram-viewport"><img class="diagram" src="{_esc(src)}" alt="{_esc(alt)}"></div>')
        self.line('  <div class="diagram-controls">')
        self.line('    <button class="diagram-btn diagram-zoom-in" title="Zoom in">+</button>')
        self.line('    <button class="diagram-btn diagram-zoom-out" title="Zoom out">&minus;</button>')
        self.line('    <button class="diagram-btn diagram-reset" title="Reset">Reset</button>')
        self.line("  </div>")
        self.line("</div>")


# region MAIN
def generate_html(
    base: Base,
    output_folder: Path,
    svg_enabled: bool = True,
    format_formulas: bool = True,
    flatten_formulas: bool = True,
    mermaid_formulas: bool = True,
) -> None:
    print("Generating HTML documentation")

    # Pre-create all folders
    tables_folder = output_folder / "tables"
    tables_folder.mkdir(parents=True, exist_ok=True)
    for table in base.tables:
        fields_folder = output_folder / "fields" / table.name_snake()
        fields_folder.mkdir(parents=True, exist_ok=True)

    diagrams_dir = output_folder / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    svg_cache_dir: Path | None = None
    if svg_enabled:
        svg_cache_dir = output_folder / ".svg_cache"
        svg_cache_dir.mkdir(parents=True, exist_ok=True)

    # Copy static assets
    shutil.copy2(_STATIC_CSS, output_folder / "style.css")
    shutil.copy2(_STATIC_JS, output_folder / "script.js")

    # Generate search index
    write_search_index(base, output_folder)

    # Build reverse dependency index: field_id -> list of (field, table) that reference it
    reverse_deps: dict[str, list[tuple]] = {}
    for table in base.tables:
        for field in table.fields:
            for ref in field.referenced_fields():
                reverse_deps.setdefault(ref.id, []).append((field, table))

    write_tables(base, output_folder)
    if verbose:
        print("[dim] - HTML tables generated.[/]")

    svg_tasks: list[tuple[str, str]] = []
    svg_tasks = write_fields(
        base,
        output_folder,
        svg_enabled,
        diagrams_dir,
        svg_cache_dir,
        format_formulas=format_formulas,
        flatten_formulas=flatten_formulas,
        mermaid_formulas=mermaid_formulas,
        reverse_deps=reverse_deps,
    )
    if verbose:
        print("[dim] - HTML fields generated.[/]")

    write_svgs(svg_tasks=svg_tasks, svg_enabled=svg_enabled, diagrams_dir=diagrams_dir, svg_cache_dir=svg_cache_dir)
    if svg_enabled and verbose:
        print("[dim] - SVGs generated.[/]")

    write_index(base, output_folder, diagrams_dir, svg_enabled, reverse_deps)
    if verbose:
        print("[dim] - HTML index generated.[/]")

    if verbose:
        print("[green] - HTML documentation generation complete.[/]")
        print("")


def write_tables(base: Base, output_folder: Path) -> None:
    for table in base.tables:
        crumbs = [("Home", "../index.html"), (table.name, "")]
        with WriteToHtmlFile(
            path=output_folder / "tables" / f"{table.name_snake()}.html",
            title=table.name,
            css_path=_css_path(1),
            breadcrumbs=crumbs,
            depth=1,
        ) as w:
            w.document_start()

            w.header(table.name, level=1)

            w.list_start("metadata")
            w.list_item(f"<strong>Airtable ID:</strong> {w.copyable(table.id)}")
            w.list_item(f"<strong>Number of Fields:</strong> {len(table.fields)}")
            w.list_item(f"<strong>Number of Views:</strong> {len(table.views)}")
            w.list_end()

            if table.linked_tables():
                w.section_start(f"Linked Tables ({len(table.linked_tables())})")
                w.list_start()
                for t in table.linked_tables():
                    w.list_item(_link(_esc(t.name), f"../tables/{t.name_snake()}.html"))
                w.list_end()
                w.section_end()

            w.section_start(f"Fields ({len(table.fields)})")
            field_rows = [
                [
                    (_link(_esc(field.name), f"../fields/{table.name_snake()}/{field.name_snake()}.html"), field.name),
                    (w.copyable(field.id), field.id),
                    (_field_type_tag(field.type), field.type),
                ]
                for field in table.fields
            ]
            w.interactive_table(
                table_id=f"fields-{table.name_snake()}",
                headers=["Name", "ID", "Type"],
                rows=field_rows,
                filter_columns=[2],
            )
            w.section_end()

            w.section_start(f"Views ({len(table.views)})")
            view_rows = [
                [
                    (_esc(view.name), view.name),
                    (w.copyable(view.id), view.id),
                    (_esc(view.type), view.type),
                ]
                for view in table.views
            ]
            w.interactive_table(
                table_id=f"views-{table.name_snake()}",
                headers=["Name", "ID", "Type"],
                rows=view_rows,
                filter_columns=[2],
            )
            w.section_end()

            w.document_end()


def write_fields(
    base: Base,
    output_folder: Path,
    svg_enabled: bool = True,
    diagrams_dir: Path | None = None,
    svg_cache_dir: Path | None = None,
    format_formulas: bool = True,
    flatten_formulas: bool = True,
    mermaid_formulas: bool = True,
    reverse_deps: dict[str, list[tuple]] | None = None,
) -> list[tuple[str, str]]:
    svg_tasks: list[tuple[str, str]] = []

    for table in base.tables:
        folder = output_folder / "fields" / table.name_snake()
        for field in table.fields:
            crumbs = [
                ("Home", "../../index.html"),
                (table.name, f"../../tables/{table.name_snake()}.html"),
                (field.name, ""),
            ]
            with WriteToHtmlFile(
                path=folder / f"{field.name_snake()}.html",
                title=f"{field.name} - {table.name}",
                css_path=_css_path(2),
                breadcrumbs=crumbs,
                depth=2,
            ) as w:
                w.document_start()

                w.header(field.name, level=1)

                w.list_start("metadata")
                w.list_item(f"<strong>Airtable ID:</strong> {w.copyable(field.id)}")
                w.list_item("<strong>Table:</strong> " + _link(_esc(table.name), f"../../tables/{table.name_snake()}.html"))
                w.list_item(f"<strong>Type:</strong> {_field_type_tag(field.type)}")

                if field.is_link_or_linked_value() and field.options:
                    if linked_table := field.linked_table():
                        w.list_item(
                            "<strong>Linked Table:</strong> " + _link(_esc(linked_table.name), f"../../tables/{linked_table.name_snake()}.html")
                        )
                    if field.is_lookup_rollup() and field.options.record_link_field_id:
                        lookup_field = table.field_by_id(field.options.record_link_field_id)
                        if lookup_field:
                            w.list_item(
                                "<strong>Linked via:</strong> "
                                + _link(
                                    _esc(lookup_field.name),
                                    f"../../fields/{table.name_snake()}/{lookup_field.name_snake()}.html",
                                )
                            )

                if field.type == "count":
                    if counted_field := field.counted_field():
                        w.list_item(
                            "<strong>Counts Records in:</strong> "
                            + _link(
                                _esc(counted_field.name),
                                f"../../fields/{table.name_snake()}/{counted_field.name_snake()}.html",
                            )
                        )

                if field.type == "formula" and field.options and field.options.formula:
                    w.list_item(f"<strong>Complexity:</strong> {_formula_complexity_badge(field.options.formula)}")

                w.list_end()

                if field.description:
                    w.section_start("Description")
                    w.quote(field.description)
                    w.section_end()

                if not field.is_valid():
                    w.warning("Field is invalid")

                if field.type == "formula":
                    condensed = field.formula(condense=True)
                    raw_sanitized = field.formula(sanitized=True, condense=True)

                    w.section_start("Formula")
                    if format_formulas:
                        w.formula_html(field.formula(sanitized=True, format=True, highlight=True))
                    else:
                        w.code_block(field.formula(sanitized=True))
                    w.section_end()

                    if flatten_formulas:
                        flattened_condensed = field.formula(flatten=True, condense=True)
                        if condensed != flattened_condensed:
                            w.section_start("Formula (Flattened)")
                            w.paragraph_raw("<em>Nested formulas expanded</em>")
                            if format_formulas:
                                w.formula_html(field.formula(sanitized=True, flatten=True, format=True, highlight=True))
                            else:
                                w.code_block(field.formula(sanitized=True, flatten=True))
                            w.section_end()

                    w.section_start("Formula (Raw)")
                    w.code_block_copyable(raw_sanitized)
                    w.section_end()

                    if mermaid_formulas:
                        w.section_start("Formula Diagram")
                        mermaid_code = mermaid_formula(field)
                        w.paragraph_raw(_link("Open in Mermaid Live", mermaid_live_url(mermaid_code)))
                        if svg_enabled and diagrams_dir and svg_cache_dir:
                            w.svg_embed(f"../../diagrams/{field.id}.svg", alt=f"Formula diagram for {field.name}")
                            if cached_svg := get_cached_svg(mermaid_code, svg_cache_dir, field.id):
                                svg_path = diagrams_dir / f"{field.id}.svg"
                                svg_path.write_text(cached_svg)
                            else:
                                svg_tasks.append((field.id, mermaid_code))
                        if diagrams_dir:
                            mmd_path = diagrams_dir / f"{field.id}.mmd"
                            mmd_path.write_text(mermaid_code)
                        w.section_end()

                    refs = field.referenced_fields()
                    w.section_start(f"Fields Linked via Formula ({len(refs)})")
                    if refs:
                        w.list_start()
                        for f in refs:
                            if linked_field := table.field_by_id(f.id):
                                w.list_item(
                                    _link(
                                        _esc(linked_field.name),
                                        f"../../fields/{table.name_snake()}/{linked_field.name_snake()}.html",
                                    )
                                )
                        w.list_end()
                    w.section_end()

                if (field.type == "singleSelect" or field.type == "multipleSelects") and field.options and field.options.choices:
                    w.section_start("Options")
                    w.list_start()
                    for option in field.options.choices:
                        w.list_item(_esc(option.name))
                    w.list_end()
                    w.section_end()

                if field.type == "lastModifiedTime":
                    ref_fields = field.referenced_fields()
                    w.section_start(f"Monitors {len(ref_fields)} Field(s)")
                    if ref_fields:
                        w.list_start()
                        for ref_field in ref_fields:
                            w.list_item(
                                _link(
                                    _esc(ref_field.name),
                                    f"../../fields/{table.name_snake()}/{ref_field.name_snake()}.html",
                                )
                            )
                        w.list_end()
                    w.section_end()

                refs_by = reverse_deps.get(field.id, []) if reverse_deps else []
                if refs_by:
                    w.section_start(f"Referenced By ({len(refs_by)})")
                    w.list_start()
                    for ref_field, ref_table in refs_by:
                        label = f'{_esc(ref_field.name)} <span class="search-hint">{_esc(ref_table.name)} &middot; {_esc(ref_field.type)}</span>'
                        w.list_item(
                            _link(
                                label,
                                f"../../fields/{ref_table.name_snake()}/{ref_field.name_snake()}.html",
                            )
                        )
                    w.list_end()
                    w.section_end()
                elif reverse_deps is not None and not field.is_computed():
                    w.paragraph_raw('<span class="tag tag-unreferenced">unreferenced</span> Not used by any formula, lookup, or rollup.')

                w.document_end()

    return svg_tasks


def write_svgs(
    svg_tasks: list[tuple[str, str]],
    svg_enabled: bool = True,
    diagrams_dir: Path | None = None,
    svg_cache_dir: Path | None = None,
) -> None:
    if svg_enabled and diagrams_dir and svg_cache_dir and svg_tasks:
        results = render_svgs_parallel(svg_tasks, svg_cache_dir)
        for field_id, svg_content in results:
            if svg_content:
                svg_path = diagrams_dir / f"{field_id}.svg"
                svg_path.write_text(svg_content)


def write_index(
    base: Base, output_folder: Path, diagrams_dir: Path, svg_enabled: bool = True, reverse_deps: dict[str, list[tuple]] | None = None
) -> None:
    with WriteToHtmlFile(
        path=output_folder / "index.html",
        title="Airtable Documentation",
        css_path=_css_path(0),
    ) as w:
        w.document_start()

        w.paragraph_raw(f"<em>Last Updated:</em> {datetime.now().strftime('%Y-%m-%d')}")
        w.header("Airtable Documentation", level=1)

        w.list_start("metadata")
        w.list_item(f"<strong>Total Tables:</strong> {len(base.tables)}")
        w.list_item(f"<strong>Total Fields:</strong> {sum(len(t.fields) for t in base.tables)}")
        w.list_item(f"<strong>Total Views:</strong> {sum(len(t.views) for t in base.tables)}")
        w.list_end()

        # Write schema JSON and add download link
        schema_path = output_folder / "schema.json"
        schema_path.write_text(json.dumps(base.to_dict(), indent=2))
        w.paragraph_raw('<a href="schema.json" download="schema.json">Download Schema (JSON)</a>')

        w.section_start(f"Tables ({len(base.tables)})")
        w.list_start()
        for table in base.tables:
            w.list_item(_link(_esc(table.name), f"tables/{table.name_snake()}.html"))
        w.list_end()
        w.section_end()

        # Field type breakdown
        type_counts = Counter(field.type for table in base.tables for field in table.fields)
        w.section_start(f"Field Types ({len(type_counts)})")
        type_rows = [[(_field_type_tag(ft), ft), (str(count), str(count).zfill(6))] for ft, count in type_counts.most_common()]
        w.interactive_table(
            table_id="field-type-stats",
            headers=["Type", "Count"],
            rows=type_rows,
        )
        w.section_end()

        # Base diagram
        mmd_code = mermaid_base(base)
        mmd_path = diagrams_dir / "base.mmd"
        mmd_path.write_text(mmd_code)
        if svg_enabled:
            svg_cache_dir = output_folder.parent / ".svg_cache"
            svg_cache_dir.mkdir(parents=True, exist_ok=True)
            svg_content = mermaid_to_svg(mmd_code, svg_cache_dir, "base")
            if svg_content:
                svg_path = diagrams_dir / "base.svg"
                svg_path.write_text(svg_content)
                w.svg_embed("diagrams/base.svg", alt="Base schema diagram")

        # Dead fields summary
        if reverse_deps is not None:
            dead_fields: list[tuple] = []
            for table in base.tables:
                for field in table.fields:
                    if field.id not in reverse_deps and not field.is_computed():
                        dead_fields.append((field, table))
            if dead_fields:
                w.section_start(f"Unreferenced Fields ({len(dead_fields)})", open=False)
                w.paragraph("Fields not referenced by any formula, lookup, or rollup.")
                dead_rows = [
                    [
                        (_link(_esc(f.name), f"fields/{t.name_snake()}/{f.name_snake()}.html"), f.name),
                        (_esc(t.name), t.name),
                        (_field_type_tag(f.type), f.type),
                    ]
                    for f, t in dead_fields
                ]
                w.interactive_table(
                    table_id="dead-fields",
                    headers=["Field", "Table", "Type"],
                    rows=dead_rows,
                    filter_columns=[1, 2],
                )
                w.section_end()

        w.document_end()


def write_search_index(base: Base, output_folder: Path) -> None:
    """Generate a JS file with all tables/fields for global search."""
    entries: list[dict[str, str]] = []
    for table in base.tables:
        entries.append({"name": table.name, "kind": "table", "url": f"tables/{table.name_snake()}.html"})
        for field in table.fields:
            entry: dict[str, str] = {
                "name": field.name,
                "kind": field.type,
                "table": table.name,
                "url": f"fields/{table.name_snake()}/{field.name_snake()}.html",
            }
            if field.description:
                entry["desc"] = field.description
            entries.append(entry)
    js_content = f"var SEARCH_INDEX={json.dumps(entries, separators=(',', ':'))};\n"
    (output_folder / "search-index.js").write_text(js_content)
