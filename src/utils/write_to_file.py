import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, PrivateAttr

PROPERTY_NAME = "Property Name (snake_case)"
MODEL_NAME = "Model Name (snake_case)"


@dataclass
class ImportSymbol:
    """A single importable symbol.

    `name` is how the symbol renders inside the import clause (e.g. ``"AirtableRuntime as F"``),
    `local` is the token scanned for in the generated body (e.g. ``"F"``). For a bare symbol the
    two are identical. `always` forces the symbol to be emitted regardless of body usage.
    """

    name: str
    local: str
    always: bool = False


@dataclass
class ImportGroup:
    """Candidate imports from a single module."""

    module: str
    symbols: list[ImportSymbol] = field(default_factory=list)


def _token_used(token: str, text: str) -> bool:
    """Word-boundary search for `token` in `text`.

    `[\\w$]` lookarounds respect JS/TS ``$`` identifiers and avoid substring matches
    (``F`` does not match ``FieldSet``; ``RecordId`` does not match ``RecordIdMapping``).
    """
    return re.search(r"(?<![\w$])" + re.escape(token) + r"(?![\w$])", text) is not None


class WriteToFile(BaseModel):
    """Abstracts file writing operations with buffered single-write output."""

    path: Path
    lines: list[str] = []
    language: Literal["python", "typescript", "javascript", "markdown", "mermaid", "rust", "html"]

    # Deferred-import state. Imports are registered as candidates, then resolved against actual
    # body usage at flush time so each file only imports symbols it references.
    _import_groups: list[ImportGroup] = PrivateAttr(default_factory=list)
    _import_marker: int | None = PrivateAttr(default=None)
    _resolved: bool = PrivateAttr(default=False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.resolve_imports()

            os.makedirs(self.path.parent, exist_ok=True)

            # Build header based on language
            match self.language:
                case "python":
                    header: str = (
                        "# ==========================================\n"
                        "# Auto-generated file. Do not edit directly.\n"
                        "# ==========================================\n\n"
                    )
                case "typescript" | "javascript" | "rust":
                    header: str = (
                        "// ==========================================\n"
                        "// Auto-generated file. Do not edit directly.\n"
                        "// ==========================================\n\n"
                    )
                case _:
                    header: str = ""

            # Single write operation: header + all lines joined
            content = header + "\n".join(self.lines) + ("\n" if self.lines else "")

            # Write mode truncates/creates file (no need to delete first)
            with open(self.path, "w") as f:
                f.write(content)

    def line(self, text: str):
        self.lines.append(text)

    def line_empty(self):
        self.lines.append("")

    def line_indented(self, text: str, indent: int = 1):
        self.lines.append("    " * indent + text)

    # region Smart imports

    def add_import(self, module: str, symbols: list[str | tuple[str, str]], *, always: bool = False) -> None:
        """Register candidate imports from `module`.

        Each entry is either a bare name (scanned & rendered identically) or a
        ``(render_name, local_token)`` tuple for aliases. `always=True` forces inclusion of every
        symbol in the call. Symbols are not written to the buffer here — they are resolved against
        actual body usage at flush time. Repeated calls for the same module merge into one group.
        """
        group = next((g for g in self._import_groups if g.module == module), None)
        if group is None:
            group = ImportGroup(module=module)
            self._import_groups.append(group)
        for entry in symbols:
            if isinstance(entry, str):
                name = local = entry
            else:
                name, local = entry
            group.symbols.append(ImportSymbol(name=name, local=local, always=always))

    def mark_imports(self) -> None:
        """Record the current buffer position as the splice point for resolved imports.

        Everything appended after this call is treated as the file body for usage scanning.
        """
        self._import_marker = len(self.lines)

    def _render_import_group(self, group: ImportGroup, used: list[ImportSymbol]) -> list[str]:
        """Render the import line(s) for the used symbols of one group. Overridden per language."""
        raise NotImplementedError(f"{type(self).__name__} does not implement _render_import_group")

    def resolve_imports(self) -> None:
        """Scan the body and splice in only the imports whose symbols are actually used."""
        if self._resolved:
            return
        self._resolved = True
        if not self._import_groups:
            return

        marker = self._import_marker if self._import_marker is not None else 0
        # Scan only the body (lines after the marker) so resolved imports never self-match.
        body = "\n".join(self.lines[marker:])

        rendered: list[str] = []
        for group in self._import_groups:
            used = [sym for sym in group.symbols if sym.always or _token_used(sym.local, body)]
            if used:
                rendered.extend(self._render_import_group(group, used))

        self.lines[marker:marker] = rendered

    # endregion
