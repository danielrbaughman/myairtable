"""Base selection: threading, fan-out routing, and the per-(base_id, api_key) cache.

The property under test is *which base a tool reads*, which no signature audit and no
byte-comparison can establish. The dangerous failure is silent: base_health_report(base="b")
returning base "a"'s findings under base b's name, with no error anywhere.
"""

from __future__ import annotations

import inspect
from types import FunctionType
from typing import cast

import pytest

from myairtable import meta, schema_tools
from myairtable.meta import Base


@pytest.fixture(autouse=True)
def _clean_registry():
    """Every test starts with an empty registry, env, and base cache."""
    meta.reset_configuration()
    schema_tools.clear_base_cache()
    yield
    meta.reset_configuration()
    schema_tools.clear_base_cache()


class _EmptyBase:
    """A base with no tables. Findings are empty everywhere — routing is the subject."""

    id = "appFAKE"
    tables: list = []

    def fields(self) -> list:
        return []

    def select_fields(self) -> list:
        return []

    def field_by_id(self, _id):
        return None

    def table_by_id(self, _id):
        return None


# --- the fan-out -----------------------------------------------------------


def test_base_health_report_never_leaves_the_requested_base(monkeypatch):
    """base_health_report aggregates 8 tools + its own lookup; each must ask for the same base.

    _get_base raises on any other selector, so a sub-call that forgot to thread `base`
    (and thus resolves the *default* base) fails loudly here instead of silently
    reporting the wrong base's findings.
    """
    seen: list[str] = []

    def _strict_get_base(base: str = "", api_key: str = "") -> Base:
        seen.append(base)
        if base != "equipment":
            raise AssertionError(f"a tool reached for base={base!r}; every call must thread 'equipment'")
        return cast(Base, _EmptyBase())

    monkeypatch.setattr(schema_tools, "_get_base", _strict_get_base)

    result = schema_tools.base_health_report(base="equipment")

    assert result["summary"]["categories"] == 9
    # Its own lookup + the sub-tools that reach for a base. If a future tool joins the
    # roll-up without threading base, the raise above fires before this.
    assert seen and set(seen) == {"equipment"}
    assert len(seen) >= 8, f"expected the full fan-out to resolve a base, saw {len(seen)}"


def test_every_public_tool_threads_base_to_get_base(monkeypatch):
    """Call all 28 with base='equipment'; none may resolve any other base.

    Complements the fan-out test: that one proves the aggregator routes, this one proves
    each individual tool does. Tools needing real table/field args are exercised via the
    fan-out test and the CLI suite instead; here an empty base makes most calls trivial.
    """
    called: list[tuple[str, str]] = []
    current: dict[str, str] = {}

    def _strict_get_base(base: str = "", api_key: str = "") -> Base:
        called.append((current["tool"], base))
        if base != "equipment":
            raise AssertionError(f"{current['tool']} resolved base={base!r}, not 'equipment'")
        return cast(Base, _EmptyBase())

    monkeypatch.setattr(schema_tools, "_get_base", _strict_get_base)

    # Tools whose only params are optional; the rest need real tables to reach _get_base
    # and are covered by the fan-out test above. The annotation widens the union of
    # concrete function types PUBLIC_TOOLS infers to, which a dynamic call can't satisfy.
    no_arg_tools: list[FunctionType] = [t for t in schema_tools.PUBLIC_TOOLS if not _required_params(t)]
    assert len(no_arg_tools) >= 13

    for tool in no_arg_tools:
        current["tool"] = tool.__name__
        tool(base="equipment")

    resolved = {name for name, _ in called}
    assert resolved == {t.__name__ for t in no_arg_tools}, "a tool never resolved a base at all"
    assert {b for _, b in called} == {"equipment"}


def _required_params(fn) -> list[str]:
    return [
        name
        for name, p in inspect.signature(fn).parameters.items()
        if p.default is inspect.Parameter.empty and p.kind is not inspect.Parameter.VAR_KEYWORD
    ]


# --- the signature contract ------------------------------------------------


def test_base_is_keyword_only_on_every_tool():
    """Keyword-only turns a positional slip into TypeError rather than a wrong-base read.

    compare_tables(a, b, c) must not quietly treat `c` as a base selector.
    """
    for tool in schema_tools.PUBLIC_TOOLS:
        param = inspect.signature(tool).parameters.get("base")
        assert param is not None, f"{tool.__name__} has no base param"
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, f"{tool.__name__}: base is {param.kind}"
        assert param.default == "", f"{tool.__name__}: base default is {param.default!r}, want ''"

    # ty rejects this call statically, which is the property holding at the type level.
    # The ignore keeps the runtime half of it: agents and JSON clients get no type
    # checking, so a third positional must still raise rather than land in `base`.
    with pytest.raises(TypeError):
        schema_tools.compare_tables("a", "b", "oops")  # ty: ignore[too-many-positional-arguments]


# --- the cache -------------------------------------------------------------


def _stub_metadata(monkeypatch) -> list[tuple[str, str]]:
    """Record every real schema fetch. Stubs the network boundary, not _get_base.

    Stubbing _get_base wholesale (as the other suites do) bypasses _base_cache entirely
    and would prove nothing about the cache.
    """
    fetches: list[tuple[str, str]] = []

    def _fake_fetch(base_id: str = "", api_key: str = "") -> dict:
        fetches.append((base_id, api_key))
        return {"tables": []}

    monkeypatch.setattr(meta, "get_base_meta_data", _fake_fetch)
    return fetches


def test_cache_reuses_one_base_per_base_id_and_key(monkeypatch):
    fetches = _stub_metadata(monkeypatch)
    meta.configure_bases({"crm": ("appCRM", "keyCRM")})

    first = schema_tools._get_base("crm")
    second = schema_tools._get_base("crm")

    assert first is second
    assert fetches == [("appCRM", "keyCRM")], "second call refetched instead of hitting the cache"


def test_same_base_under_two_keys_is_not_shared(monkeypatch):
    """The cross-credential leak the (base_id, api_key) key exists to prevent.

    Two callers naming the same base with different tokens must not share a Base — under
    transport='http' with per-request credentials, caller B would read A's schema.
    Both keys are explicit so an env fallback can't mask a failure to thread the key.
    """
    fetches = _stub_metadata(monkeypatch)

    alice = schema_tools._get_base("appSHARED", api_key="keyALICE")
    bob = schema_tools._get_base("appSHARED", api_key="keyBOB")

    assert alice is not bob
    assert fetches == [("appSHARED", "keyALICE"), ("appSHARED", "keyBOB")]

    assert schema_tools._get_base("appSHARED", api_key="keyALICE") is alice
    assert len(fetches) == 2, "a cached entry was evicted by the other credential"


def test_two_aliases_get_two_bases(monkeypatch):
    fetches = _stub_metadata(monkeypatch)
    meta.configure_bases({"crm": ("appCRM", "keyCRM"), "equipment": ("appEQ", "keyEQ")})

    crm = schema_tools._get_base("crm")
    equipment = schema_tools._get_base("equipment")

    assert crm is not equipment
    assert crm.id == "appCRM"
    assert equipment.id == "appEQ"
    assert fetches == [("appCRM", "keyCRM"), ("appEQ", "keyEQ")]


def test_clear_base_cache_targets_one_base_then_all(monkeypatch):
    fetches = _stub_metadata(monkeypatch)
    meta.configure_bases({"crm": ("appCRM", "keyCRM"), "equipment": ("appEQ", "keyEQ")})

    schema_tools._get_base("crm")
    equipment = schema_tools._get_base("equipment")
    assert len(fetches) == 2

    schema_tools.clear_base_cache("crm")
    schema_tools._get_base("crm")
    assert len(fetches) == 3, "clearing crm should force exactly one refetch"
    assert schema_tools._get_base("equipment") is equipment, "clearing crm evicted equipment"

    schema_tools.clear_base_cache()
    schema_tools._get_base("equipment")
    assert len(fetches) == 4


def test_clear_base_cache_drops_a_base_under_every_credential(monkeypatch):
    """Staleness is a property of the base, not the token — clear must not miss a key."""
    fetches = _stub_metadata(monkeypatch)

    schema_tools._get_base("appSHARED", api_key="keyALICE")
    schema_tools._get_base("appSHARED", api_key="keyBOB")
    assert len(fetches) == 2

    schema_tools.clear_base_cache("appSHARED")

    schema_tools._get_base("appSHARED", api_key="keyALICE")
    schema_tools._get_base("appSHARED", api_key="keyBOB")
    assert len(fetches) == 4
