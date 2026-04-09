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
from ..utils import timer
from ..utils.helpers import Paths
from ..utils.mermaid_to_image import get_cached_svg, mermaid_live_url, mermaid_to_svg, render_svgs_parallel
from ..utils.verbose import verbose
from ..utils.write_to_file import WriteToFile
from .mermaid import mermaid_base, mermaid_formula

# Path to the static CSS file bundled with the project
_STATIC_CSS = Path(__file__).resolve().parent.parent.parent / "static" / "html" / "style.css"


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

    def document_start(self):
        root = "../" * self._depth
        self.line("<!DOCTYPE html>")
        self.line('<html lang="en">')
        self.line("<head>")
        self.line('  <meta charset="utf-8">')
        self.line('  <meta name="viewport" content="width=device-width, initial-scale=1">')
        self.line(f"  <title>{_esc(self._title)}</title>")
        self.line(f'  <link rel="stylesheet" href="{_esc(self._css_path)}">')
        self.line(f'  <script src="{root}search-index.js"></script>')
        self.line("</head>")
        self.line("<body>")
        # Apply saved theme (or system preference) before any content renders to avoid flash
        self.line(
            "<script>(function(){var t=localStorage.getItem('theme');"
            "if(t==='dark'||(t!=='light'&&window.matchMedia('(prefers-color-scheme:dark)').matches))"
            "document.body.classList.add('dark-mode');})()</script>"
        )
        self.line('<div class="page">')
        # Header bar with breadcrumbs, search, and theme toggle
        self.line('<div class="page-header">')
        if self._breadcrumbs:
            self.line('<nav class="breadcrumbs">')
            parts: list[str] = []
            for label, href in self._breadcrumbs[:-1]:
                parts.append(_link(_esc(label), href))
            # Last breadcrumb is current page (no link)
            parts.append(_esc(self._breadcrumbs[-1][0]))
            self.line("  " + '<span class="separator">/</span>'.join(parts))
            self.line("</nav>")
        self.line('<button class="theme-toggle" title="Toggle dark mode">&#9790;</button>')
        self.line(f'<div class="global-search" data-root="{root}">')
        self.line('  <input type="text" class="global-search-input" placeholder="Search tables and fields...">')
        self.line('  <div class="global-search-results"></div>')
        self.line("</div>")
        self.line("</div>")

    def document_end(self):
        self.line("</div>")
        self.line("<script>")
        # Theme toggle
        self.line("document.querySelectorAll('.theme-toggle').forEach(function(btn){")
        self.line("  btn.textContent=document.body.classList.contains('dark-mode')?'\\u2600':'\\u263E';")
        self.line("  btn.addEventListener('click',function(){")
        self.line("    document.body.classList.toggle('dark-mode');")
        self.line("    var dark=document.body.classList.contains('dark-mode');")
        self.line("    localStorage.setItem('theme',dark?'dark':'light');")
        self.line("    btn.textContent=dark?'\\u2600':'\\u263E';")
        self.line("  });")
        self.line("});")
        # Copy-to-clipboard
        self.line("document.addEventListener('click',function(e){")
        self.line("  var el=e.target.closest('.copyable');")
        self.line("  if(!el)return;")
        self.line("  navigator.clipboard.writeText(el.getAttribute('data-copy'));")
        self.line("  el.classList.add('copied');")
        self.line("  setTimeout(function(){el.classList.remove('copied')},1500);")
        self.line("});")
        # Interactive table: search
        self.line("document.querySelectorAll('.interactive-search').forEach(function(input){")
        self.line("  input.addEventListener('input',function(){")
        self.line("    var wrap=document.getElementById(this.dataset.target);")
        self.line("    var term=this.value.toLowerCase();")
        self.line("    wrap.querySelectorAll('tbody tr').forEach(function(tr){")
        self.line("      var text=tr.textContent.toLowerCase();")
        self.line("      tr.style.display=text.indexOf(term)<0?'none':'';")
        self.line("    });")
        self.line("  });")
        self.line("});")
        # Interactive table: filter
        self.line("document.querySelectorAll('.interactive-filter').forEach(function(sel){")
        self.line("  sel.addEventListener('change',function(){")
        self.line("    var wrap=document.getElementById(this.dataset.target);")
        self.line("    var col=parseInt(this.dataset.col);")
        self.line("    var val=this.value;")
        self.line("    wrap.querySelectorAll('tbody tr').forEach(function(tr){")
        self.line("      var cell=tr.children[col];")
        self.line("      if(!val){tr.style.display='';return;}")
        self.line("      tr.style.display=cell.getAttribute('data-sort-value')===val?'':'none';")
        self.line("    });")
        self.line("    var searchInput=wrap.querySelector('.interactive-search');")
        self.line("    if(searchInput)searchInput.value='';")
        self.line("  });")
        self.line("});")
        # Interactive table: sort
        self.line("document.querySelectorAll('table.interactive thead th').forEach(function(th){")
        self.line("  th.addEventListener('click',function(){")
        self.line("    var table=this.closest('table');")
        self.line("    var col=parseInt(this.dataset.col);")
        self.line("    var asc=!this.classList.contains('sort-asc');")
        self.line("    table.querySelectorAll('th').forEach(function(h){h.classList.remove('sort-asc','sort-desc');});")
        self.line("    this.classList.add(asc?'sort-asc':'sort-desc');")
        self.line("    var tbody=table.querySelector('tbody');")
        self.line("    var rows=Array.from(tbody.querySelectorAll('tr'));")
        self.line("    rows.sort(function(a,b){")
        self.line("      var av=a.children[col].getAttribute('data-sort-value')||a.children[col].textContent;")
        self.line("      var bv=b.children[col].getAttribute('data-sort-value')||b.children[col].textContent;")
        self.line("      return asc?av.localeCompare(bv):bv.localeCompare(av);")
        self.line("    });")
        self.line("    rows.forEach(function(r){tbody.appendChild(r);});")
        self.line("  });")
        self.line("});")
        # Diagram pan/zoom
        self.line("document.querySelectorAll('.diagram-container').forEach(function(container){")
        self.line("  var vp=container.querySelector('.diagram-viewport');")
        self.line("  var img=vp.querySelector('.diagram');")
        self.line("  var scale=1,panX=0,panY=0,dragging=false,lastX,lastY;")
        self.line("  function apply(){img.style.transform='translate('+panX+'px,'+panY+'px) scale('+scale+')';}")
        self.line("  function reset(){scale=1;panX=0;panY=0;apply();}")
        self.line("  vp.addEventListener('wheel',function(e){")
        self.line("    e.preventDefault();")
        self.line("    var d=e.deltaY>0?-0.1:0.1;")
        self.line("    scale=Math.min(Math.max(0.2,scale+d),5);")
        self.line("    apply();")
        self.line("  },{passive:false});")
        self.line("  vp.addEventListener('pointerdown',function(e){")
        self.line("    if(e.button!==0)return;")
        self.line("    dragging=true;lastX=e.clientX;lastY=e.clientY;")
        self.line("    vp.setPointerCapture(e.pointerId);")
        self.line("    vp.style.cursor='grabbing';")
        self.line("    e.preventDefault();")
        self.line("  });")
        self.line("  vp.addEventListener('pointermove',function(e){")
        self.line("    if(!dragging)return;")
        self.line("    panX+=e.clientX-lastX;panY+=e.clientY-lastY;")
        self.line("    lastX=e.clientX;lastY=e.clientY;")
        self.line("    apply();")
        self.line("  });")
        self.line("  vp.addEventListener('pointerup',function(e){")
        self.line("    if(!dragging)return;")
        self.line("    dragging=false;vp.releasePointerCapture(e.pointerId);")
        self.line("    vp.style.cursor='';")
        self.line("  });")
        self.line("  container.querySelector('.diagram-zoom-in').addEventListener('click',function(){")
        self.line("    scale=Math.min(5,scale+0.25);apply();")
        self.line("  });")
        self.line("  container.querySelector('.diagram-zoom-out').addEventListener('click',function(){")
        self.line("    scale=Math.max(0.2,scale-0.25);apply();")
        self.line("  });")
        self.line("  container.querySelector('.diagram-reset').addEventListener('click',reset);")
        self.line("});")
        # Anchor link copy
        self.line("document.addEventListener('click',function(e){")
        self.line("  var a=e.target.closest('.anchor-link');")
        self.line("  if(!a)return;")
        self.line("  e.preventDefault();")
        self.line("  var url=location.href.split('#')[0]+a.getAttribute('href');")
        self.line("  navigator.clipboard.writeText(url);")
        self.line("  a.textContent='Copied!';")
        self.line("  setTimeout(function(){a.textContent='#'},1500);")
        self.line("});")
        # Keyboard shortcut: / to focus search
        self.line("document.addEventListener('keydown',function(e){")
        self.line("  if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){")
        self.line("    e.preventDefault();")
        self.line("    var input=document.querySelector('.global-search-input');")
        self.line("    if(input)input.focus();")
        self.line("  }")
        self.line("});")
        # Global search autocomplete
        self.line("document.querySelectorAll('.global-search').forEach(function(wrap){")
        self.line("  var input=wrap.querySelector('.global-search-input');")
        self.line("  var results=wrap.querySelector('.global-search-results');")
        self.line("  var root=wrap.dataset.root;")
        self.line("  var sel=-1;")
        self.line("  function render(items){")
        self.line("    sel=-1;")
        self.line("    if(!items.length){results.style.display='none';return;}")
        self.line("    results.innerHTML=items.map(function(it,i){")
        self.line("      var label=it.table?it.name+' <span class=\"search-hint\">'+it.table+' &middot; '+it.kind+'</span>'")
        self.line("        :it.name+' <span class=\"search-hint\">'+it.kind+'</span>';")
        self.line("      return '<div class=\"search-item\" data-idx=\"'+i+'\">'+label+'</div>';")
        self.line("    }).join('');")
        self.line("    results.style.display='block';")
        self.line("    results._items=items;")
        self.line("  }")
        self.line("  input.addEventListener('input',function(){")
        self.line("    var q=this.value.toLowerCase().trim();")
        self.line("    if(!q){render([]);return;}")
        self.line("    var matches=SEARCH_INDEX.filter(function(it){")
        self.line("      return it.name.toLowerCase().indexOf(q)>=0")
        self.line("        ||(it.table&&it.table.toLowerCase().indexOf(q)>=0)")
        self.line("        ||it.kind.toLowerCase().indexOf(q)>=0")
        self.line("        ||(it.desc&&it.desc.toLowerCase().indexOf(q)>=0);")
        self.line("    }).slice(0,15);")
        self.line("    render(matches);")
        self.line("  });")
        self.line("  input.addEventListener('keydown',function(e){")
        self.line("    var items=results.querySelectorAll('.search-item');")
        self.line("    if(!items.length)return;")
        self.line("    if(e.key==='ArrowDown'){e.preventDefault();sel=Math.min(sel+1,items.length-1);}")
        self.line("    else if(e.key==='ArrowUp'){e.preventDefault();sel=Math.max(sel-1,0);}")
        self.line("    else if(e.key==='Enter'&&sel>=0){e.preventDefault();items[sel].click();return;}")
        self.line("    else if(e.key==='Escape'){render([]);return;}")
        self.line("    else return;")
        self.line("    items.forEach(function(el,i){el.classList.toggle('active',i===sel);});")
        self.line("  });")
        self.line("  results.addEventListener('click',function(e){")
        self.line("    var item=e.target.closest('.search-item');")
        self.line("    if(!item)return;")
        self.line("    var idx=parseInt(item.dataset.idx);")
        self.line("    var entry=results._items[idx];")
        self.line("    window.location.href=root+entry.url;")
        self.line("  });")
        self.line("  document.addEventListener('click',function(e){")
        self.line("    if(!wrap.contains(e.target))render([]);")
        self.line("  });")
        self.line("});")
        self.line("</script>")
        self.line("</body>")
        self.line("</html>")

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

    html_root = output_folder / Paths.DOCS

    # Pre-create all folders
    tables_folder = html_root / "tables"
    tables_folder.mkdir(parents=True, exist_ok=True)
    for table in base.tables:
        fields_folder = html_root / "fields" / table.name_snake()
        fields_folder.mkdir(parents=True, exist_ok=True)

    diagrams_dir = html_root / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    svg_cache_dir: Path | None = None
    if svg_enabled:
        svg_cache_dir = output_folder / ".svg_cache"
        svg_cache_dir.mkdir(parents=True, exist_ok=True)

    # Copy static CSS
    shutil.copy2(_STATIC_CSS, html_root / "style.css")

    # Generate search index
    write_search_index(base, html_root)

    # Build reverse dependency index: field_id -> list of (field, table) that reference it
    reverse_deps: dict[str, list[tuple]] = {}
    for table in base.tables:
        for field in table.fields:
            for ref in field.referenced_fields():
                reverse_deps.setdefault(ref.id, []).append((field, table))

    with timer.timer("HTML: write_tables"):
        write_tables(base, html_root)
        if verbose:
            print("[dim] - HTML tables generated.[/]")

    svg_tasks: list[tuple[str, str]] = []
    with timer.timer("HTML: write_fields"):
        svg_tasks = write_fields(
            base,
            html_root,
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

    with timer.timer("HTML: write_svgs"):
        write_svgs(svg_tasks=svg_tasks, svg_enabled=svg_enabled, diagrams_dir=diagrams_dir, svg_cache_dir=svg_cache_dir)
        if svg_enabled and verbose:
            print("[dim] - SVGs generated.[/]")

    with timer.timer("HTML: write_index"):
        write_index(base, html_root, diagrams_dir, svg_enabled, reverse_deps)
        if verbose:
            print("[dim] - HTML index generated.[/]")

    if verbose:
        print("[green] - HTML documentation generation complete.[/]")
        print("")


def write_tables(base: Base, html_root: Path) -> None:
    for table in base.tables:
        crumbs = [("Home", "../index.html"), ("Tables", "../index.html"), (table.name, "")]
        with WriteToHtmlFile(
            path=html_root / "tables" / f"{table.name_snake()}.html",
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
    html_root: Path,
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
        folder = html_root / "fields" / table.name_snake()
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

                with timer.timer("HTML: write_field: headers"):
                    w.header(field.name, level=1)

                    w.list_start("metadata")
                    w.list_item(f"<strong>Airtable ID:</strong> {w.copyable(field.id)}")
                    w.list_item("<strong>Table:</strong> " + _link(_esc(table.name), f"../../tables/{table.name_snake()}.html"))
                    w.list_item(f"<strong>Type:</strong> {_field_type_tag(field.type)}")

                with timer.timer("HTML: write_field: links"):
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

                with timer.timer("HTML: write_field: count"):
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

                with timer.timer("HTML: write_field: description"):
                    if field.description:
                        w.section_start("Description")
                        w.quote(field.description)
                        w.section_end()

                    if not field.is_valid():
                        w.warning("Field is invalid")

                with timer.timer("HTML: write_field: formula"):
                    if field.type == "formula":
                        condensed = field.formula(condense=True)
                        raw_sanitized = field.formula(sanitized=True, condense=True)

                        with timer.timer("HTML: write_field: formula: highlighted"):
                            w.section_start("Formula")
                            if format_formulas:
                                w.formula_html(field.formula(sanitized=True, format=True, highlight=True))
                            else:
                                w.code_block(field.formula(sanitized=True))
                            w.section_end()

                        if flatten_formulas:
                            with timer.timer("HTML: write_field: formula: flattened"):
                                flattened_condensed = field.formula(flatten=True, condense=True)
                                if condensed != flattened_condensed:
                                    w.section_start("Formula (Flattened)")
                                    w.paragraph_raw("<em>Nested formulas expanded</em>")
                                    if format_formulas:
                                        w.formula_html(field.formula(sanitized=True, flatten=True, format=True, highlight=True))
                                    else:
                                        w.code_block(field.formula(sanitized=True, flatten=True))
                                    w.section_end()

                        with timer.timer("HTML: write_field: formula: raw"):
                            w.section_start("Formula (Raw)")
                            w.code_block_copyable(raw_sanitized)
                            w.section_end()

                        if mermaid_formulas:
                            with timer.timer("HTML: write_field: formula: diagram"):
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

                        with timer.timer("HTML: write_field: formula: field links"):
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

                with timer.timer("HTML: write_field: options"):
                    if (field.type == "singleSelect" or field.type == "multipleSelects") and field.options and field.options.choices:
                        w.section_start("Options")
                        w.list_start()
                        for option in field.options.choices:
                            w.list_item(_esc(option.name))
                        w.list_end()
                        w.section_end()

                with timer.timer("HTML: write_field: monitors"):
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

                with timer.timer("HTML: write_field: reverse deps"):
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
    base: Base, html_root: Path, diagrams_dir: Path, svg_enabled: bool = True, reverse_deps: dict[str, list[tuple]] | None = None
) -> None:
    with WriteToHtmlFile(
        path=html_root / "index.html",
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
        schema_path = html_root / "schema.json"
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
            svg_cache_dir = html_root.parent / ".svg_cache"
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


def write_search_index(base: Base, html_root: Path) -> None:
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
    (html_root / "search-index.js").write_text(js_content)
