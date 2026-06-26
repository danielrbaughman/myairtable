import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Generic, Optional, overload

from pyairtable import Table
from pyairtable.api.types import RecordDict
from pyairtable.formulas import Formula

from .formula import ID
from .helpers import validate_keys
from .table_helpers import FieldType, ORMType, SortOption, ViewType, convert_sort_options, prepare_fields_for_save, sanitize_record_dict


class ORMTable(Generic[ORMType, ViewType, FieldType]):
    """An abstraction of pyAirtable's `Table` for ORM models."""

    _orm_cls: type[ORMType]
    _table: Table
    """The original pyAirtable instance. Returns un-typed RecordDicts."""
    _calculated_field_names: Sequence[str]
    _calculated_field_ids: Sequence[str]
    _view_name_id_mapping: Mapping[ViewType, str]
    _field_names: Sequence[str]

    _cache_seconds: int = 0
    _cache: dict[str, tuple[Any, float]] = {}

    @classmethod
    def from_table(
        cls,
        table: Table,
        model_cls: type[ORMType],
        calculated_field_names: Sequence[str],
        calculated_field_ids: Sequence[str],
        view_name_id_mapping: "Mapping[ViewType, str]",
        field_names: Sequence[str],
        cache_seconds: int = 0,
    ) -> "ORMTable[ORMType, ViewType, FieldType]":
        instance = cls()
        instance._table = table
        instance._orm_cls = model_cls
        instance._calculated_field_names = calculated_field_names
        instance._calculated_field_ids = calculated_field_ids
        instance._view_name_id_mapping = view_name_id_mapping
        instance._field_names = field_names
        instance._cache_seconds = cache_seconds
        instance._cache = {}
        return instance

    def get_view_id(self, view: ViewType) -> str:
        """Resolves an Airtable view name to the corresponding ID, if available."""
        id = self._view_name_id_mapping.get(view, view)
        return id if id else view

    def invalidate_cache(self) -> None:
        """Clears the cache for this table."""
        self._cache.clear()

    def _cache_key(self, *args: Any) -> str:
        return json.dumps(args, default=str)

    @overload
    def get(
        self,
        record_id: str,
        use_field_ids: bool = True,
        fields: list[FieldType] | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        **options,
    ) -> ORMType:
        """
        Retrieves a single Airtable record as an ORM model.

        Args:
            record_id (str): Airtable record ID
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to True.
            **options: Additional options to pass to the pyAirtable `get` method.
        """
        ...

    @overload
    def get(
        self,
        record_ids: list[str],
        use_field_ids: bool = True,
        fields: list[FieldType] | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        max_records: int | None = None,
        **options,
    ) -> list[ORMType]:
        """
        Retrieves multiple Airtable records as ORM models.

        Args:
            record_ids (list[str]): A list of Airtable record IDs
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to True.
            fields (list[str] | None, optional): A list of fields to retrieve. If None, retrieves all fields. Defaults to None.
            **options: Additional options to pass to the pyAirtable `get` method.
        """
        ...

    @overload
    def get(
        self,
        formula: Optional[Formula | str] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = True,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        max_records: int | None = None,
        **options,
    ) -> list[ORMType]:
        """
        Retrieves multiple Airtable records as ORM models.

        Calling with no formula/view will return all records.

        Args:
            formula (str, optional): An Airtable formula string to filter records. Defaults to "" (no filter).
            view (str, optional): The name/id of the view to filter records. Defaults to "" (no filter).
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to True.
            page_size (int, optional): The number of records to retrieve per page. Max 100. Defaults to 100.
            fields (list[str] | None, optional): A list of fields to retrieve. If None, retrieves all fields. Defaults to None.
            **options: Additional options to pass to the pyAirtable `all` method.
        """
        ...

    def get(
        self,
        record_id: str | None = None,
        record_ids: list[str] | None = None,
        formula: Optional[Formula | str] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = True,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        max_records: int | None = None,
        **options,
    ) -> ORMType | list[ORMType]:
        # Cache check
        if self._cache_seconds > 0:
            cache_key = self._cache_key(
                record_id, record_ids, str(formula), view, use_field_ids, page_size, fields, sort, offset, time_zone, user_locale
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                value, expires_at = cached
                if time.monotonic() < expires_at:
                    return value

        if fields is not None:
            validate_keys(fields, self._field_names)

        if isinstance(record_id, list):
            if len(record_id) == 0:
                return []
            if len(record_id) > 0 and isinstance(record_id[0], str):
                record_ids = record_id
                record_id = None

        if isinstance(record_id, str) and not record_id.strip():
            raise ValueError("Record ID cannot be an empty string.")

        if record_id:
            if fields is not None:
                # table.get does not support fields parameter, so we use table.all with a formula instead
                record_dicts: list[RecordDict] = self._table.all(
                    formula=ID.equals(record_id),
                    use_field_ids=use_field_ids,
                    fields=fields,
                    sort=convert_sort_options(sort),
                    offset=offset,
                    time_zone=time_zone,
                    user_locale=user_locale,
                    **options,
                )
                record_dict: RecordDict = record_dicts[0] if record_dicts else {"id": "", "createdTime": "", "fields": {}}
            else:
                record_dict: RecordDict = self._table.get(
                    record_id,
                    use_field_ids=use_field_ids,
                    sort=convert_sort_options(sort),
                    offset=offset,
                    time_zone=time_zone,
                    user_locale=user_locale,
                    **options,
                )
            record_dict = sanitize_record_dict(record_dict)
            record_orm: ORMType = self._orm_cls.from_record(record_dict)
            result = record_orm
        elif record_ids and len(record_ids) > 0:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            record_dicts: list[RecordDict] = self._table.all(
                formula=ID.in_list(record_ids),
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                sort=convert_sort_options(sort),
                offset=offset,
                time_zone=time_zone,
                user_locale=user_locale,
                max_records=max_records,
                **options,
            )
            record_dicts = [sanitize_record_dict(r) for r in record_dicts]
            record_orms: list[ORMType] = [self._orm_cls.from_record(r) for r in record_dicts]
            result = record_orms
        else:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            record_dicts: list[RecordDict] = self._table.all(
                formula=Formula(str(formula)).flatten() if formula else None,
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                sort=convert_sort_options(sort),
                offset=offset,
                time_zone=time_zone,
                user_locale=user_locale,
                max_records=max_records,
                **options,
            )
            record_dicts = [sanitize_record_dict(r) for r in record_dicts]
            record_orms: list[ORMType] = [self._orm_cls.from_record(r) for r in record_dicts]
            result = record_orms

        # Cache store
        if self._cache_seconds > 0:
            self._cache[cache_key] = (result, time.monotonic() + self._cache_seconds)
        return result

    @overload
    def create(self, record: ORMType) -> ORMType:
        """
        Creates a single Airtable record.

        Args:
            record (Model): The record to create.
        """
        ...

    @overload
    def create(self, records: list[ORMType]) -> list[ORMType]:
        """
        Creates multiple Airtable records.

        Args:
            records (list[Model]): The records to create.
        """
        ...

    def create(
        self,
        record: ORMType | None = None,
        records: list[ORMType] | None = None,
    ) -> ORMType | list[ORMType]:
        self.invalidate_cache()
        if isinstance(record, list):
            if len(record) == 0:
                return []
            if len(record) > 0 and isinstance(record[0], self._orm_cls):
                records = record
                record = None

        if records is not None and isinstance(records, list):
            if records is None:
                raise ValueError("Records to create cannot be None.")
            if len(records) == 0:
                return []
            self._orm_cls.batch_save(records)
            fetched = self.get(record_ids=[r.id for r in records])
            fetched_list: list[ORMType] = fetched if isinstance(fetched, list) else [fetched]
            # get(record_ids=...) re-fetches via all(formula=ID.in_list(...)), which returns
            # Airtable's natural (table/view) order, NOT the input order. Re-key by id so the
            # returned list matches the input order: callers rely on positional correspondence
            # (notably upsert()'s no-merge branch, which zips this result against its inputs).
            by_id = {rec.id: rec for rec in fetched_list}
            missing = [r.id for r in records if r.id not in by_id]
            if missing:
                raise RuntimeError(f"create: re-fetch did not return created record(s): {missing}")
            return [by_id[r.id] for r in records]
        else:
            if record is None:
                raise ValueError("Record to create cannot be None.")
            record.save()
            new_record = self.get(record_id=record.id)
            return new_record

    @overload
    def update(self, record: ORMType) -> ORMType:
        """
        Updates a single Airtable record.

        Args:
            record (Model): The record to update.
        """
        ...

    @overload
    def update(self, records: list[ORMType]) -> list[ORMType]:
        """
        Updates multiple Airtable records.

        Args:
            records (list[Model]): The records to update.
        """
        ...

    def update(
        self,
        record: ORMType | None = None,
        records: list[ORMType] | None = None,
    ) -> ORMType | list[ORMType]:
        self.invalidate_cache()
        if isinstance(record, list):
            if len(record) == 0:
                return []
            if len(record) > 0 and isinstance(record[0], self._orm_cls):
                records = record
                record = None

        if records is not None and isinstance(records, list):
            if records is None:
                raise ValueError("Records to update cannot be None.")
            if len(records) == 0:
                return []
            records: list[RecordDict] = [r.to_record() for r in records]
            for r in records:
                r["fields"] = prepare_fields_for_save(r["fields"], self._calculated_field_ids)
            update_dicts: list[RecordDict] = [{"id": r["id"], "createdTime": r.get("createdTime", ""), "fields": r["fields"]} for r in records]
            records = self._table.batch_update(update_dicts, use_field_ids=True)
            records = [sanitize_record_dict(r) for r in records]
            orm_records = [self._orm_cls.from_record(r) for r in records]
            return orm_records
        else:
            if record is None:
                raise ValueError("Record to update cannot be None.")
            record: RecordDict = record.to_record()
            record["fields"] = prepare_fields_for_save(record["fields"], self._calculated_field_ids)
            record = self._table.update(record_id=record["id"], fields=record["fields"], use_field_ids=True)
            record = sanitize_record_dict(record)
            orm_record = self._orm_cls.from_record(record)
            return orm_record

    def upsert(
        self,
        record: ORMType | list[ORMType],
        fields_to_merge_on: list[str] | None = None,
    ) -> ORMType | list[ORMType]:
        """
        Update-or-insert one or more records.

        With ``fields_to_merge_on`` (a list of field ids), Airtable matches each input record
        against existing records by those field values via its server-side ``performUpsert`` (an
        exact-one match updates, no match inserts, more than one match is rejected). Without it,
        records are matched by ``id`` (those carrying an id are updated, the rest created). Batches
        are handled by the underlying client (10 records per request).
        """
        self.invalidate_cache()
        is_list = isinstance(record, list)
        models: list[ORMType] = list(record) if isinstance(record, list) else [record]
        if not models:
            return []  # only reachable for an empty list input

        if fields_to_merge_on is not None:
            upsert_dicts: list[dict[str, Any]] = []
            for model in models:
                rec = model.to_record()
                fields = prepare_fields_for_save(rec["fields"], self._calculated_field_ids)
                entry: dict[str, Any] = {"fields": fields}
                rid = rec.get("id")
                if rid:
                    entry["id"] = rid
                upsert_dicts.append(entry)
            result = self._table.batch_upsert(upsert_dicts, key_fields=fields_to_merge_on, use_field_ids=True)
            out = [self._orm_cls.from_record(sanitize_record_dict(r)) for r in result["records"]]
        else:
            # No merge fields: update records that already have an id, create the rest.
            ordered: dict[int, ORMType] = {}
            with_id = [(i, m) for i, m in enumerate(models) if m.id]
            without_id = [(i, m) for i, m in enumerate(models) if not m.id]
            if with_id:
                updated = self.update([m for _, m in with_id])
                updated_list: list[ORMType] = updated if isinstance(updated, list) else [updated]
                for (i, _), upd in zip(with_id, updated_list):
                    ordered[i] = upd
            if without_id:
                created = self.create([m for _, m in without_id])
                created_list: list[ORMType] = created if isinstance(created, list) else [created]
                for (i, _), crt in zip(without_id, created_list):
                    ordered[i] = crt
            out = [ordered[i] for i in range(len(models))]

        return out if is_list else out[0]

    @overload
    def delete(
        self,
        record_id: str,
    ) -> None:
        """
        Deletes a single Airtable record.

        Args:
            record_id (str): Airtable record ID
        """
        ...

    @overload
    def delete(
        self,
        record_ids: list[str],
    ) -> None:
        """
        Deletes multiple Airtable records.

        Args:
            record_ids (list[str]): Airtable record IDs
        """
        ...

    @overload
    def delete(self, record: ORMType) -> None:
        """
        Deletes a single Airtable record.

        Args:
            record (ORMType): The record to delete.
        """
        ...

    @overload
    def delete(self, records: list[ORMType]) -> None:
        """
        Deletes multiple Airtable records.

        Args:
            records (list[ORMType]): The records to delete.
        """
        ...

    def delete(
        self,
        record: ORMType | None = None,
        records: list[ORMType] = [],
        record_id: str = "",
        record_ids: list[str] = [],
    ) -> None:
        self.invalidate_cache()
        if record:
            record.delete()
        elif record_id:
            self._table.delete(record_id)
        elif records:
            self._orm_cls.batch_delete(records)
        elif record_ids:
            self._table.batch_delete(record_ids)
