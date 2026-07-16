"""Offload large tool results to disk and return a compact envelope.

Several MCP tools return large payloads (whole-base scans, full schema dumps).
Returning them inline bloats the agent's context with data it usually wants to
*query*, not read whole. When a serialized result exceeds the inline limit, the
full result is written to a gitignored `.data/tools/` dir and a small envelope
is returned instead: the file path, byte/record counts, the result's own
`summary`, and a compact inferred *shape skeleton* so the agent knows the
structure and can jq/grep the file without re-running.

Shared by the MCP middleware (src/offload_middleware.py) and the CLI `--save`
flag, so both exercise the identical path.

Mirrors the ../rogo-mcp `.data/` convention, adding a real schema.
"""

import json
import os
from pathlib import Path
from typing import Any

# Per-invocation output, not bundled data: it follows the caller's cwd rather than
# the install location, which would otherwise be site-packages. MYAIRTABLE_DATA_DIR
# overrides for callers that run from somewhere they'd rather not write to.
OUTPUT_DIR = Path(os.environ.get("MYAIRTABLE_DATA_DIR") or Path.cwd() / ".data" / "tools")

_DEFAULT_INLINE_MAX_BYTES = 16384

# Keys that commonly hold the dominant array, in priority order, for record_count.
_DOMINANT_KEYS = ("fields", "shares", "tables", "sections", "views", "automations", "interfaces", "ungrouped_automations")


def inline_max_bytes() -> int:
    raw = os.environ.get("MYAIRTABLE_INLINE_MAX_BYTES")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _DEFAULT_INLINE_MAX_BYTES


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename component."""
    out = name.replace("/", "_").replace(":", "-").replace(" ", "_")
    return "".join(c for c in out if c.isalnum() or c in "._-") or "x"


# --- schema inference -------------------------------------------------------


def infer_schema(data: Any, *, max_depth: int = 4, max_keys: int = 60, node_budget: int = 2000) -> Any:
    """A compact, data-driven shape skeleton (not JSON Schema).

    Scalars -> type tag; dict -> {key: shape} with sorted keys; list ->
    [elem_tag, {len, items: merged element shape}]. Bounded by depth, dict
    breadth, and a total node budget so deeply nested / huge configs (e.g.
    automation `inputExpressions`) can't blow up. Sets a root `_truncated`
    flag when any cap fires. No sample values (avoids leaking sensitive data
    such as share-URL tokens, and keeps the skeleton small).
    """
    state = {"nodes": 0, "truncated": False}
    schema = _infer(data, 0, max_depth, max_keys, node_budget, state)
    if state["truncated"] and isinstance(schema, dict):
        schema = {"_truncated": True, **schema}
    elif state["truncated"]:
        schema = {"_truncated": True, "value": schema}
    return schema


def _scalar_tag(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


def _infer(data: Any, depth: int, max_depth: int, max_keys: int, node_budget: int, state: dict[str, Any]) -> Any:
    state["nodes"] += 1
    if state["nodes"] > node_budget:
        state["truncated"] = True
        return "...(budget)"
    if depth >= max_depth and isinstance(data, (dict, list)):
        state["truncated"] = True
        return f"...(depth>{max_depth})"

    if isinstance(data, dict):
        items = list(data.items())
        shape: dict[str, Any] = {}
        for key, value in sorted(items, key=lambda kv: str(kv[0]))[:max_keys]:
            shape[str(key)] = _infer(value, depth + 1, max_depth, max_keys, node_budget, state)
        if len(items) > max_keys:
            state["truncated"] = True
            shape[f"...(+{len(items) - max_keys} keys)"] = "..."
        return shape

    if isinstance(data, list):
        if not data:
            return []
        # Merge element shapes over a bounded sample so heterogeneous lists
        # don't lose keys.
        sample = data[:20]
        merged = _merge_shapes([_infer(item, depth + 1, max_depth, max_keys, node_budget, state) for item in sample])
        elem_tag = "<obj>" if isinstance(merged, dict) else (merged if isinstance(merged, str) else "<list>")
        return [elem_tag, {"len": len(data), "items": merged}]

    return _scalar_tag(data)


def _merge_shapes(shapes: list[Any]) -> Any:
    """Merge a list of element shapes into one (union of dict keys)."""
    dict_shapes = [s for s in shapes if isinstance(s, dict)]
    if dict_shapes and len(dict_shapes) == len(shapes):
        merged: dict[str, Any] = {}
        for s in dict_shapes:
            for k, v in s.items():
                if k not in merged:
                    merged[k] = v
        return dict(sorted(merged.items()))
    # Non-dicts (or mixed): collapse to the first / a scalar union tag.
    tags = {s for s in shapes if isinstance(s, str)}
    if tags and len(tags) == 1:
        return next(iter(tags))
    return shapes[0]


# --- offload ----------------------------------------------------------------


def record_count(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in _DOMINANT_KEYS:
            if isinstance(value.get(key), list):
                return len(value[key])
        list_lens = [len(v) for v in value.values() if isinstance(v, list)]
        if list_lens:
            return max(list_lens)
    return None


def _heavy_schema_target(value: Any) -> Any:
    """The part of the result to infer a schema over (heavy arrays, not summary)."""
    if isinstance(value, dict):
        heavy = {k: v for k, v in value.items() if k != "summary" and isinstance(v, (list, dict))}
        return heavy or value
    return value


def _is_error_payload(value: Any) -> bool:
    return isinstance(value, dict) and set(value.keys()) <= {"error", "message"} and "error" in value


def arg_slug(arguments: dict[str, Any] | None) -> str:
    """Deterministic slug from a tool's non-empty arguments."""
    if not arguments:
        return "all"
    parts: list[str] = []
    for key in sorted(arguments):
        val = arguments[key]
        if val is None or val == "" or val is False:
            continue
        if val is True:
            parts.append(safe_filename(key))
        elif isinstance(val, (int, float)):
            parts.append(f"{safe_filename(key)}{val}")
        else:
            parts.append(safe_filename(str(val)))
    return "__".join(parts) if parts else "all"


def _atomic_write(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, dest)


def offload(tool_name: str, arguments: dict[str, Any] | None, value: Any) -> Any:
    """Return `value` inline if small, else write it to disk and return an envelope.

    Error payloads ({"error","message"}) are always returned inline.
    """
    if _is_error_payload(value):
        return value

    slug = arg_slug(arguments)

    # Strings (e.g. Mermaid diagrams) save as text, no structural schema.
    if isinstance(value, str):
        encoded = value
        if len(encoded.encode()) <= inline_max_bytes():
            return value
        dest = OUTPUT_DIR / f"{safe_filename(tool_name)}__{slug}.md"
        _atomic_write(dest, encoded)
        return {
            "saved_to": str(dest),
            "bytes": len(encoded.encode()),
            "schema": "str",
            "note": _note(dest),
        }

    encoded = json.dumps(value, default=str)
    if len(encoded.encode()) <= inline_max_bytes():
        return value

    dest = OUTPUT_DIR / f"{safe_filename(tool_name)}__{slug}.json"
    _atomic_write(dest, encoded)

    envelope: dict[str, Any] = {
        "saved_to": str(dest),
        "bytes": len(encoded.encode()),
        "record_count": record_count(value),
        "schema": infer_schema(_heavy_schema_target(value)),
        "note": _note(dest),
    }
    if isinstance(value, dict) and isinstance(value.get("summary"), dict):
        envelope["summary"] = value["summary"]
    elif isinstance(value, list):
        envelope["summary"] = {"count": len(value)}
    return envelope


def _note(dest: Path) -> str:
    return (
        f"Full result saved to disk (exceeded the {inline_max_bytes()}-byte inline limit). "
        f"Read {dest} for the complete data; `schema` describes its structure. "
        "Prefer jq/grep on the file over re-running the tool."
    )
