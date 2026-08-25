"""Hermetic guards on the payload `duplicate()` sends to Airtable.

`duplicate` is the first verb in the project that POSTs a record read back from Airtable, so
it is the first to hit two things the existing verbs never exercise: the attachment write
whitelist, and the fact that every ORM layer's "save" path is dirty- or id-gated. These tests
pin the resulting payload without touching the network.
"""

from typing import Any

import pytest

from myairtable.static.python.orm_table import ORMTable
from myairtable.static.python.table_helpers import project_attachments_for_create

ATTACHMENT_FIELD = "fldAttach000000001"
COMPUTED_FIELD = "fldFormula00000001"
TEXT_FIELD = "fldText00000000001"


class FakeTable:
    """Stands in for pyairtable's `Table`, recording what a write would have sent."""

    def __init__(self, records: dict[str, dict] | None = None):
        self.records = records or {}
        self.batch_create_calls: list[tuple[list[dict], dict]] = []
        self.update_calls: list[Any] = []
        self.batch_update_calls: list[Any] = []

    def batch_create(self, fields_list, **kwargs):
        self.batch_create_calls.append((fields_list, kwargs))
        return [{"id": f"recNEW{i}", "createdTime": "", "fields": dict(f)} for i, f in enumerate(fields_list)]

    def update(self, *args, **kwargs):  # must never be reached by duplicate()
        self.update_calls.append((args, kwargs))
        raise AssertionError("duplicate() issued an UPDATE")

    def batch_update(self, *args, **kwargs):  # must never be reached by duplicate()
        self.batch_update_calls.append((args, kwargs))
        raise AssertionError("duplicate() issued a batch UPDATE")


class FakeModel:
    """Minimal stand-in for a generated pyairtable ORM model."""

    def __init__(self, record_id: str, fields: dict):
        self.id = record_id
        self._fields = fields

    def to_record(self) -> dict:
        return {"id": self.id, "createdTime": "", "fields": dict(self._fields)}

    @classmethod
    def from_record(cls, record: dict) -> "FakeModel":
        return cls(record["id"], record["fields"])


def _table(sources: dict[str, dict]) -> "tuple[ORMTable, FakeTable]":
    """An ORMTable wired to fakes, bypassing from_table()'s pyairtable dependency.

    The FakeTable is returned alongside so assertions read it directly rather than through
    `table._table`, whose declared type is pyairtable's real `Table`.
    """
    table = ORMTable.__new__(ORMTable)
    fake = FakeTable()
    table._table = fake
    table._orm_cls = FakeModel
    table._calculated_field_ids = [COMPUTED_FIELD]
    table._calculated_field_names = [COMPUTED_FIELD]
    table._cache_seconds = 0
    table._cache = {}
    table._field_names = []
    table._view_name_id_mapping = {}
    # duplicate() re-reads its sources; serve them from the fixture.
    table.get = lambda record_ids=None, **kw: [FakeModel(rid, sources[rid]) for rid in (record_ids or [])]
    return table, fake


SERVER_ATTACHMENT = {
    "id": "attServerSide00001",
    "url": "https://example.com/a.png",
    "filename": "a.png",
    "size": 1234,
    "type": "image/png",
    "width": 10,
    "height": 10,
    "thumbnails": {"small": {"url": "https://example.com/t.png"}},
}


class TestAttachmentProjection:
    """Airtable's create endpoint is a strict whitelist: only {url, filename}."""

    def test_strips_readonly_metadata(self):
        out = project_attachments_for_create({"f": [dict(SERVER_ATTACHMENT)]})
        assert out["f"] == [{"url": "https://example.com/a.png", "filename": "a.png"}]

    def test_drops_id_which_create_rejects(self):
        # An `id` -- alone or echoed alongside `url` -- fails with INVALID_ATTACHMENT_OBJECT.
        out = project_attachments_for_create({"f": [dict(SERVER_ATTACHMENT)]})
        assert all("id" not in a for a in out["f"])

    def test_passes_through_caller_built_attachments(self):
        assert project_attachments_for_create({"f": [{"url": "u"}]})["f"] == [{"url": "u"}]

    @pytest.mark.parametrize(
        "cell",
        [
            ["rec1", "rec2"],  # linked records
            {"id": "usrX", "email": "e@x.com"},  # collaborator
            [{"id": "usrX", "email": "e@x.com"}],  # multi-collaborator
            "https://example.com",  # a url-typed text cell
            [],
        ],
    )
    def test_leaves_other_cell_types_alone(self, cell):
        assert project_attachments_for_create({"f": cell})["f"] == cell

    def test_does_not_mutate_caller_fields(self):
        fields = {"f": [dict(SERVER_ATTACHMENT)]}
        project_attachments_for_create(fields)
        assert fields["f"][0]["id"] == "attServerSide00001"


class TestDuplicatePayload:
    def test_posts_and_never_updates(self):
        # pyairtable's Model.save() PATCHes when the model has an id, so a duplicate built on
        # create()'s save() path would silently update the source instead of inserting a copy.
        table, fake = _table({"recSRC": {TEXT_FIELD: "hello"}})
        table.duplicate("recSRC")
        assert len(fake.batch_create_calls) == 1
        assert fake.update_calls == []
        assert fake.batch_update_calls == []

    def test_payload_is_full_writable_set_not_a_dirty_diff(self):
        table, fake = _table({"recSRC": {TEXT_FIELD: "hello", "fldB": 42}})
        table.duplicate("recSRC")
        (fields_list, _kwargs) = fake.batch_create_calls[0]
        assert fields_list[0] == {TEXT_FIELD: "hello", "fldB": 42}

    def test_computed_fields_are_omitted(self):
        table, fake = _table({"recSRC": {TEXT_FIELD: "hi", COMPUTED_FIELD: "computed!"}})
        table.duplicate("recSRC")
        (fields_list, _kwargs) = fake.batch_create_calls[0]
        assert COMPUTED_FIELD not in fields_list[0]

    def test_no_record_id_in_payload(self):
        table, fake = _table({"recSRC": {TEXT_FIELD: "hi"}})
        table.duplicate("recSRC")
        (fields_list, _kwargs) = fake.batch_create_calls[0]
        assert "id" not in fields_list[0]

    def test_attachments_projected_in_the_posted_payload(self):
        table, fake = _table({"recSRC": {ATTACHMENT_FIELD: [dict(SERVER_ATTACHMENT)]}})
        table.duplicate("recSRC")
        (fields_list, _kwargs) = fake.batch_create_calls[0]
        assert fields_list[0][ATTACHMENT_FIELD] == [{"url": "https://example.com/a.png", "filename": "a.png"}]

    def test_typecast_is_forwarded(self):
        table, fake = _table({"recSRC": {TEXT_FIELD: "hi"}})
        table.duplicate("recSRC", typecast=True)
        (_fields_list, kwargs) = fake.batch_create_calls[0]
        assert kwargs["typecast"] is True

    def test_batch_reads_sources_once_and_preserves_input_order(self):
        # get(record_ids=...) returns Airtable's table order, so duplicate must re-key.
        sources = {"recA": {TEXT_FIELD: "a"}, "recB": {TEXT_FIELD: "b"}, "recC": {TEXT_FIELD: "c"}}
        table, fake = _table(sources)
        calls: list[list[str]] = []

        def recording_get(record_ids=None, **kw):
            ids = list(record_ids or [])
            calls.append(ids)
            # deliberately return them in the "wrong" (table) order
            return [FakeModel(rid, sources[rid]) for rid in reversed(ids)]

        table.get = recording_get  # ty: ignore[invalid-assignment]
        table.duplicate(["recC", "recA", "recB"])
        assert len(calls) == 1, "sources must be fetched in a single batched read"
        (fields_list, _kwargs) = fake.batch_create_calls[0]
        assert [f[TEXT_FIELD] for f in fields_list] == ["c", "a", "b"]

    def test_single_returns_scalar_list_returns_list(self):
        table, fake = _table({"recSRC": {TEXT_FIELD: "hi"}})
        assert isinstance(table.duplicate("recSRC"), FakeModel)
        assert isinstance(table.duplicate(["recSRC"]), list)

    def test_empty_list_is_a_noop(self):
        table, fake = _table({})
        assert table.duplicate([]) == []
        assert fake.batch_create_calls == []

    def test_unsaved_source_is_rejected(self):
        table, fake = _table({})
        with pytest.raises(ValueError, match="no id"):
            table.duplicate(FakeModel("", {TEXT_FIELD: "x"}))

    def test_missing_source_raises_rather_than_returning_short(self):
        table, fake = _table({"recA": {TEXT_FIELD: "a"}})
        table.get = lambda record_ids=None, **kw: []  # ty: ignore[invalid-assignment]
        with pytest.raises(RuntimeError, match="not found"):
            table.duplicate(["recA"])
