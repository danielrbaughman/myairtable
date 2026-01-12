from pathlib import Path
from typing import Literal

from .meta import Base, Field
from .write_to_file import WriteToFile


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
    write.line("---")
    write.line("config:")
    write.line("  flowchart:")
    write.line("    nodeSpacing: 20")
    write.line("    rankSpacing: 30")
    write.line("---")
    write.flowchart("LR")
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
                write.node(fld.id, box_label(fld), type="Hexagon", indent=2)
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
