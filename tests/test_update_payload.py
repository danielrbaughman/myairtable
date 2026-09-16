"""Hermetic guards on the payload `update()` sends to Airtable.

Airtable's PATCH is per field: whatever fields are in the request are re-asserted, everything
else is left alone. `update()` therefore has to send a dirty diff, not the full record, or a
model that was read a few seconds ago silently reverts fields another writer changed in the
meantime. These tests pin that contract without touching the network.
"""

from typing import Any

from myairtable.static.python.orm_table import ORMTable

COMPUTED_FIELD = "fldFormula00000001"
TEXT_FIELD = "fldText00000000001"
FLAG_FIELD = "fldFlag00000000001"
OTHER_FIELD = "fldOther0000000001"


class FakeTable:
    """Stands in for pyairtable's `Table`, recording what a write would have sent."""

    def __init__(self):
        self.update_calls: list[dict[str, Any]] = []
        self.batch_update_calls: list[dict[str, Any]] = []

    def update(self, record_id, fields, **kwargs):
        self.update_calls.append({"record_id": record_id, "fields": dict(fields), **kwargs})
        return {"id": record_id, "createdTime": "", "fields": dict(fields)}

    def batch_update(self, records, **kwargs):
        self.batch_update_calls.append({"records": [dict(r) for r in records], **kwargs})
        return [{"id": r["id"], "createdTime": "", "fields": dict(r["fields"])} for r in records]


class FakeModel:
    """Minimal stand-in for a generated pyairtable ORM model, including its change tracking."""

    def __init__(self, record_id: str, fields: dict, changed: dict[str, bool] | None = None):
        self.id = record_id
        self._fields = fields
        self._changed: dict[str, bool] = dict(changed or {})

    def to_record(self) -> dict:
        return {"id": self.id, "createdTime": "", "fields": dict(self._fields)}

    @classmethod
    def from_record(cls, record: dict) -> "FakeModel":
        return cls(record["id"], record["fields"])


class UntrackedModel(FakeModel):
    """A model with no `_changed` attribute at all (not a pyairtable Model)."""

    def __init__(self, record_id: str, fields: dict):
        self.id = record_id
        self._fields = fields

    def to_record(self) -> dict:
        return {"id": self.id, "createdTime": "", "fields": dict(self._fields)}


def _table(model_cls=FakeModel) -> "tuple[ORMTable, FakeTable]":
    """An ORMTable wired to fakes, bypassing from_table()'s pyairtable dependency."""
    table = ORMTable.__new__(ORMTable)
    fake = FakeTable()
    table._table = fake
    table._orm_cls = model_cls
    table._calculated_field_ids = [COMPUTED_FIELD]
    table._calculated_field_names = [COMPUTED_FIELD]
    table._cache_seconds = 0
    table._cache = {}
    table._field_names = []
    table._view_name_id_mapping = {}
    return table, fake


FULL = {TEXT_FIELD: "text", FLAG_FIELD: ["Job Completed"], OTHER_FIELD: 7, COMPUTED_FIELD: "computed"}


class TestSingleUpdate:
    def test_sends_only_changed_fields(self):
        table, fake = _table()
        model = FakeModel("rec1", FULL, changed={TEXT_FIELD: True})
        table.update(model)
        assert fake.update_calls == [{"record_id": "rec1", "fields": {TEXT_FIELD: "text"}, "use_field_ids": True, "typecast": False}]

    def test_stale_fields_are_not_reasserted(self):
        """The regression: an unchanged multi-select must not be written back over another writer's value."""
        table, fake = _table()
        model = FakeModel("rec1", FULL, changed={OTHER_FIELD: True})
        table.update(model)
        assert FLAG_FIELD not in fake.update_calls[0]["fields"]

    def test_unchanged_model_is_a_noop_and_returned_as_is(self):
        table, fake = _table()
        model = FakeModel("rec1", FULL)
        assert table.update(model) is model
        assert fake.update_calls == []

    def test_changed_computed_field_is_still_omitted(self):
        table, fake = _table()
        model = FakeModel("rec1", FULL, changed={COMPUTED_FIELD: True, TEXT_FIELD: True})
        table.update(model)
        assert fake.update_calls[0]["fields"] == {TEXT_FIELD: "text"}

    def test_only_computed_changed_is_a_noop(self):
        table, fake = _table()
        model = FakeModel("rec1", FULL, changed={COMPUTED_FIELD: True})
        assert table.update(model) is model
        assert fake.update_calls == []

    def test_force_sends_every_writable_field(self):
        table, fake = _table()
        model = FakeModel("rec1", FULL)
        table.update(model, force=True)
        assert fake.update_calls[0]["fields"] == {TEXT_FIELD: "text", FLAG_FIELD: ["Job Completed"], OTHER_FIELD: 7}

    def test_model_without_change_tracking_is_sent_in_full(self):
        table, fake = _table(UntrackedModel)
        table.update(UntrackedModel("rec1", FULL))
        assert fake.update_calls[0]["fields"] == {TEXT_FIELD: "text", FLAG_FIELD: ["Job Completed"], OTHER_FIELD: 7}

    def test_returns_a_fresh_model_from_the_response(self):
        table, _ = _table()
        model = FakeModel("rec1", FULL, changed={TEXT_FIELD: True})
        updated = table.update(model)
        assert updated is not model
        assert updated.id == "rec1"

    def test_changes_are_cleared_after_a_write(self):
        table, fake = _table()
        model = FakeModel("rec1", FULL, changed={TEXT_FIELD: True})
        table.update(model)
        assert model._changed == {}
        table.update(model)
        assert len(fake.update_calls) == 1

    def test_typecast_is_forwarded(self):
        table, fake = _table()
        table.update(FakeModel("rec1", FULL, changed={TEXT_FIELD: True}), typecast=True)
        assert fake.update_calls[0]["typecast"] is True


class TestBatchUpdate:
    def test_each_record_carries_its_own_diff(self):
        table, fake = _table()
        a = FakeModel("recA", FULL, changed={TEXT_FIELD: True})
        b = FakeModel("recB", FULL, changed={OTHER_FIELD: True})
        table.update([a, b])
        sent = fake.batch_update_calls[0]["records"]
        assert sent == [
            {"id": "recA", "createdTime": "", "fields": {TEXT_FIELD: "text"}},
            {"id": "recB", "createdTime": "", "fields": {OTHER_FIELD: 7}},
        ]

    def test_unchanged_records_are_skipped_but_keep_their_position(self):
        table, fake = _table()
        a = FakeModel("recA", FULL, changed={TEXT_FIELD: True})
        b = FakeModel("recB", FULL)
        c = FakeModel("recC", FULL, changed={OTHER_FIELD: True})
        out = table.update([a, b, c])
        assert [r["id"] for r in fake.batch_update_calls[0]["records"]] == ["recA", "recC"]
        assert [r.id for r in out] == ["recA", "recB", "recC"]
        assert out[1] is b
        assert out[0] is not a and out[2] is not c

    def test_all_unchanged_is_a_noop(self):
        table, fake = _table()
        models = [FakeModel("recA", FULL), FakeModel("recB", FULL)]
        assert table.update(models) == models
        assert fake.batch_update_calls == []

    def test_force_sends_every_writable_field(self):
        table, fake = _table()
        table.update([FakeModel("recA", FULL)], force=True)
        assert fake.batch_update_calls[0]["records"][0]["fields"] == {TEXT_FIELD: "text", FLAG_FIELD: ["Job Completed"], OTHER_FIELD: 7}

    def test_changes_are_cleared_only_for_written_records(self):
        table, _ = _table()
        a = FakeModel("recA", FULL, changed={TEXT_FIELD: True})
        b = FakeModel("recB", FULL, changed={COMPUTED_FIELD: True})  # nothing writable changed
        table.update([a, b])
        assert a._changed == {}
        assert b._changed == {COMPUTED_FIELD: True}

    def test_empty_list_is_a_noop(self):
        table, fake = _table()
        assert table.update([]) == []
        assert fake.batch_update_calls == []

    def test_typecast_is_forwarded(self):
        table, fake = _table()
        table.update([FakeModel("recA", FULL, changed={TEXT_FIELD: True})], typecast=True)
        assert fake.batch_update_calls[0]["typecast"] is True
