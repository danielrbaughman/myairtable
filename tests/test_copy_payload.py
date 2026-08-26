"""Hermetic guards on `copy()` -- the local, no-I/O half of `duplicate()`.

`duplicate()` is `fetch + copy + create`; `copy()` is that middle step on its own,
returning a detached unsaved model the caller mutates and hands to `create()`.
Because it touches no network, all of its behaviour is pinned here rather than in
the live suite. Three things are easy to get wrong and silent when you do:

* the DETACH. pyairtable's `Model.save()` branches on `if not self.id:`, so a copy
  that kept the source's id would PATCH THE SOURCE instead of inserting.
* SHARED STATE. A list read off a model is a `ChangeTrackingList` bound to that
  model; alias one into the copy and mutating the copy marks the SOURCE dirty.
* ATTACHMENTS. Airtable's create endpoint accepts only {url, filename}; anything
  echoing a server-side `id` is rejected with INVALID_ATTACHMENT_OBJECT.
"""

from typing import Any, cast

import pytest
from pyairtable.orm import Model, fields

from myairtable.static.python.orm_table import ORMTable
from myairtable.static.python.table_helpers import copy_model

TEXT_FIELD = "fldText00000000001"
TAGS_FIELD = "fldTags00000000001"
ATTACH_FIELD = "fldAttach000000001"
COMPUTED_FIELD = "fldFormula00000001"
COMPUTED_ATTACH_FIELD = "fldLookupAtt000001"

SERVER_ATTACHMENT: dict[str, Any] = {
    "id": "attServerSide00001",
    "url": "https://example.com/a.png",
    "filename": "a.png",
    "size": 1234,
    "type": "image/png",
    "width": 10,
    "height": 10,
    "thumbnails": {"small": {"url": "https://example.com/t.png"}},
}


class Copyable(Model):
    """Stands in for a generated ORM model: field ids as field names, computed
    fields marked readonly -- exactly what the Python generator emits."""

    class Meta:
        api_key = "keyFAKE0000000000"
        base_id = "appFAKE0000000000"
        table_name = "tblFAKE0000000001"
        use_field_ids = True
        memoize = True

    text = fields.TextField(TEXT_FIELD)
    tags = fields.MultipleSelectField(TAGS_FIELD)
    attachments = fields.AttachmentsField(ATTACH_FIELD)
    computed = fields.TextField(COMPUTED_FIELD, readonly=True)
    computed_attachments = fields.AttachmentsField(COMPUTED_ATTACH_FIELD, readonly=True)

    evaluate_formulas_at_runtime: bool = False


def _source(**overrides: Any) -> Copyable:
    """A model in the state `copy()` actually meets: read back from the API, so it
    carries an id, a createdTime, `_fetched`, and server-shaped attachment objects."""
    record_fields: dict[str, Any] = {
        TEXT_FIELD: "hello",
        TAGS_FIELD: ["a", "b"],
        ATTACH_FIELD: [dict(SERVER_ATTACHMENT)],
        COMPUTED_FIELD: "computed value",
        COMPUTED_ATTACH_FIELD: [dict(SERVER_ATTACHMENT)],
    }
    record_fields.update(overrides)
    return Copyable.from_record(
        {"id": "recSOURCE000000001", "createdTime": "2026-01-01T00:00:00.000Z", "fields": record_fields},
        memoize=False,
    )


class TestDetach:
    """What makes `create(copy)` insert instead of update."""

    def test_id_is_cleared(self):
        # THE load-bearing assertion: pyairtable's save() gates create-vs-update on it.
        assert copy_model(_source()).id == ""

    def test_created_time_is_cleared(self):
        assert copy_model(_source()).created_time is None

    def test_not_deleted_and_not_fetched(self):
        copied = copy_model(_source())
        assert copied._deleted is False
        # `_fetched` left True would let from_id() skip the network for the new record.
        assert copied._fetched is False

    def test_changed_is_empty_and_not_shared_with_source(self):
        source = _source()
        source.text = "edited"
        copied = copy_model(source)
        assert copied._changed == {}
        assert copied._changed is not source._changed

    def test_copy_is_not_memoized(self):
        # from_record() would have registered it; building the instance directly must not.
        copied = copy_model(_source())
        assert copied not in Copyable._memoized.values()

    def test_source_is_left_completely_untouched(self):
        source = _source()
        before = source.to_record()
        copy_model(source)
        assert source.to_record() == before
        assert source.id == "recSOURCE000000001"
        assert source._changed == {}


class TestCarriedValues:
    def test_writable_values_are_carried(self):
        copied = copy_model(_source())
        assert copied.text == "hello"
        assert list(copied.tags) == ["a", "b"]

    def test_computed_values_are_carried_and_readable(self):
        # The point of carrying them: the copy reads like its source.
        assert copy_model(_source()).computed == "computed value"

    def test_computed_values_never_reach_the_wire(self):
        # Safe to carry precisely because save() filters readonly fields out.
        written = copy_model(_source()).to_record(only_writable=True)["fields"]
        assert COMPUTED_FIELD not in written
        assert COMPUTED_ATTACH_FIELD not in written
        assert TEXT_FIELD in written

    def test_copying_an_unsaved_model_works(self):
        original = Copyable(text="draft")
        copied = copy_model(original)
        assert copied.id == ""
        assert copied.text == "draft"

    def test_mutating_the_copy_then_writing_sends_the_change(self):
        copied = copy_model(_source())
        copied.text = "changed"
        assert copied.to_record(only_writable=True)["fields"][TEXT_FIELD] == "changed"


class TestRuntimeFormulaToggle:
    """`evaluate_formulas_at_runtime` is the one mutable per-instance attribute the
    generator puts on a model; the copy should behave like its source."""

    def test_instance_level_toggle_is_carried(self):
        source = _source()
        source.evaluate_formulas_at_runtime = True  # type: ignore[attr-defined]
        assert copy_model(source).evaluate_formulas_at_runtime is True  # type: ignore[attr-defined]

    def test_untouched_toggle_stays_on_the_class(self):
        # Copying must not shadow the class attribute with an instance one.
        assert "evaluate_formulas_at_runtime" not in vars(copy_model(_source()))


class TestAttachmentProjection:
    def test_writable_attachments_are_projected(self):
        # Airtable rejects server-returned attachment objects on create; only
        # {url, filename} is accepted. Copying by URL also makes the new record's
        # attachment independent rather than an alias of the source's.
        assert list(copy_model(_source()).attachments) == [{"url": "https://example.com/a.png", "filename": "a.png"}]

    def test_computed_attachments_keep_full_metadata(self):
        # A read-only lookup can hold the same shape as a real attachment cell, but it
        # is never written, so stripping its metadata would lose fidelity for nothing.
        carried = list(copy_model(_source()).computed_attachments)
        assert carried == [SERVER_ATTACHMENT]

    def test_caller_built_attachments_pass_through(self):
        copied = copy_model(_source(**{ATTACH_FIELD: [{"url": "https://example.com/b.png"}]}))
        assert list(copied.attachments) == [{"url": "https://example.com/b.png"}]


class TestNoSharedState:
    def test_list_mutation_does_not_reach_the_source(self):
        source = _source()
        copied = copy_model(source)
        copied.tags.append("c")
        assert list(source.tags) == ["a", "b"]

    def test_list_mutation_does_not_dirty_the_source(self):
        # The ChangeTrackingList trap: it holds a `_model` back-reference and its
        # `_on_change` writes to `self._model._changed`. Aliasing one into the copy
        # would make edits to the COPY mark the SOURCE dirty -- and a dirty source is
        # what a later save() would PATCH.
        source = _source()
        assert list(source.tags) == ["a", "b"]  # force the wrapper to exist on the source
        copied = copy_model(source)
        copied.tags.append("c")
        assert source._changed == {}

    def test_nested_attachment_dicts_are_not_aliased(self):
        source = _source(**{ATTACH_FIELD: [{"url": "u", "filename": "f"}]})
        copied = copy_model(source)
        cast("dict[str, Any]", copied.attachments[0])["filename"] = "mutated"
        assert cast("dict[str, Any]", source.attachments[0])["filename"] == "f"


class FakeTable:
    """Records what a write would have sent. Any UPDATE means the detach failed."""

    def __init__(self):
        self.create_calls: list[tuple[dict, dict]] = []

    def create(self, fields_dict, **kwargs):
        self.create_calls.append((fields_dict, kwargs))
        return {"id": "recNEW000000000001", "createdTime": "2026-02-02T00:00:00.000Z", "fields": dict(fields_dict)}

    def update(self, *args, **kwargs):
        raise AssertionError("create() on a copy issued an UPDATE -- the copy was not detached")

    def batch_update(self, *args, **kwargs):
        raise AssertionError("create() on a copy issued a batch UPDATE -- the copy was not detached")


class TestCreateInsertsRatherThanUpdating:
    """The failure this whole feature has to avoid: `create(copy)` patching the source."""

    @pytest.fixture
    def fake(self, monkeypatch: pytest.MonkeyPatch) -> FakeTable:
        table = FakeTable()
        monkeypatch.setattr(type(Copyable.meta), "table", property(lambda self: table))
        return table

    def _orm_table(self) -> ORMTable:
        table = ORMTable.__new__(ORMTable)
        table._orm_cls = Copyable
        table._calculated_field_ids = [COMPUTED_FIELD, COMPUTED_ATTACH_FIELD]
        table._cache_seconds = 0
        table._cache = {}

        def _get(record_id: str = "", **kwargs: Any) -> Copyable:
            return Copyable.from_record({"id": record_id, "createdTime": "2026-02-02T00:00:00.000Z", "fields": {}}, memoize=False)

        table.get = _get
        return table

    def test_create_on_a_copy_posts_and_never_patches(self, fake: FakeTable):
        self._orm_table().create(copy_model(_source()))
        assert len(fake.create_calls) == 1

    def test_posted_payload_carries_writable_fields_and_drops_computed(self, fake: FakeTable):
        self._orm_table().create(copy_model(_source()))
        posted, _ = fake.create_calls[0]
        assert posted[TEXT_FIELD] == "hello"
        assert posted[ATTACH_FIELD] == [{"url": "https://example.com/a.png", "filename": "a.png"}]
        assert COMPUTED_FIELD not in posted
        assert COMPUTED_ATTACH_FIELD not in posted

    def test_creating_the_source_itself_would_have_updated(self, fake: FakeTable):
        # Proves the guard above is live: the same call on an undetached model raises.
        with pytest.raises(AssertionError, match="issued an UPDATE"):
            source = _source()
            source.text = "edited"
            self._orm_table().create(source)
