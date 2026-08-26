import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Generic, Optional, cast, overload

from pyairtable import Table
from pyairtable.api.types import RecordDict, UpdateRecordDict
from pyairtable.formulas import Formula

from .formula import ID
from .helpers import validate_keys
from .table_helpers import (
    CreateDictType,
    DictType,
    FieldType,
    SortOption,
    UpdateDictType,
    ViewType,
    convert_sort_options,
    prepare_fields_for_save,
    project_attachments_for_create,
    sanitize_record_dict,
)


class DictTable(Generic[DictType, UpdateDictType, CreateDictType, ViewType, FieldType]):
    """An abstraction of pyAirtable's `Table` for typed RecordDicts."""

    _dict_cls: type[DictType]
    _update_cls: type[UpdateDictType]
    _create_cls: type[CreateDictType]
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
        dict_cls: type[DictType],
        update_cls: type[UpdateDictType],
        create_cls: type[CreateDictType],
        calculated_field_names: Sequence[str],
        calculated_field_ids: Sequence[str],
        view_name_id_mapping: "Mapping[ViewType, str]",
        field_names: Sequence[str],
        cache_seconds: int = 0,
    ) -> "DictTable[DictType, UpdateDictType, CreateDictType, ViewType, FieldType]":
        instance = cls()
        instance._table = table
        instance._dict_cls = dict_cls
        instance._update_cls = update_cls
        instance._create_cls = create_cls
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
        use_field_ids: bool = False,
        fields: list[FieldType] | None = None,
        max_records: int | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        **options,
    ) -> DictType:
        """
        Retrieves a single Airtable record as a typed RecordDict.

        Args:
            record_id (str): Airtable record ID
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to False.
            max_records (int | None, optional): The maximum number of records to retrieve. If None, retrieves all records. Defaults to None.
            **options: Additional options to pass to the pyAirtable `get` method.
        """
        ...

    @overload
    def get(
        self,
        record_ids: list[str],
        use_field_ids: bool = False,
        fields: list[FieldType] | None = None,
        max_records: int | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        **options,
    ) -> list[DictType]:
        """
        Retrieves multiple Airtable records as typed RecordDicts.

        Args:
            record_ids (list[str]): Airtable record IDs
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to False.
            fields (list[str] | None, optional): A list of fields to retrieve. If None, retrieves all fields. Defaults to None.
            max_records (int | None, optional): The maximum number of records to retrieve. If None, retrieves all records. Defaults to None.
            **options: Additional options to pass to the pyAirtable `get` method.
        """
        ...

    @overload
    def get(
        self,
        formula: Optional[Formula | str] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = False,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        max_records: int | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        **options,
    ) -> list[DictType]:
        """
        Retrieves multiple Airtable records as typed RecordDicts.

        Calling with no formula/view will return all records.

        Args:
            formula (str, optional): An Airtable formula string to filter records. Defaults to "" (no filter).
            view (str, optional): The name/id of the view to filter records. Defaults to "" (no filter).
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to False.
            page_size (int, optional): The number of records to retrieve per page. Max 100. Defaults to 100.
            fields (list[str] | None, optional): A list of fields to retrieve. If None, retrieves all fields. Defaults to None.
            max_records (int | None, optional): The maximum number of records to retrieve. If None, retrieves all records. Defaults to None.
            **options: Additional options to pass to the pyAirtable `all` method.
        """
        ...

    def get(
        self,
        record_id: str | None = None,
        record_ids: list[str] | None = None,
        formula: Optional[Formula | str] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = False,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        max_records: int | None = None,
        sort: list[SortOption[FieldType]] | None = None,
        offset: int | None = None,
        time_zone: str | None = None,
        user_locale: str | None = None,
        **options,
    ) -> DictType | list[DictType]:
        # Cache check
        if self._cache_seconds > 0:
            cache_key = self._cache_key(
                record_id, record_ids, str(formula), view, use_field_ids, page_size, fields, max_records, sort, offset, time_zone, user_locale
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

        if record_id and isinstance(record_id, str):
            if fields is not None:
                # table.get does not support fields parameter, so we use table.all with a formula instead
                record_dicts: list[RecordDict] = self._table.all(
                    formula=ID.equals(record_id),
                    use_field_ids=use_field_ids,
                    fields=fields,
                    max_records=max_records,
                    sort=convert_sort_options(sort),
                    offset=offset,
                    time_zone=time_zone,
                    user_locale=user_locale,
                    **options,
                )
                record: RecordDict = record_dicts[0] if record_dicts else {"id": "", "createdTime": "", "fields": {}}
            else:
                record: RecordDict = self._table.get(
                    record_id,
                    use_field_ids=use_field_ids,
                    max_records=max_records,
                    sort=convert_sort_options(sort),
                    offset=offset,
                    time_zone=time_zone,
                    user_locale=user_locale,
                    **options,
                )
            record = sanitize_record_dict(record)
            result = record
        elif record_ids and len(record_ids) > 0:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            records: list[RecordDict] = self._table.all(
                formula=ID.in_list(record_ids),
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                max_records=max_records,
                sort=convert_sort_options(sort),
                offset=offset,
                time_zone=time_zone,
                user_locale=user_locale,
                **options,
            )
            records = [sanitize_record_dict(r) for r in records]
            result = records
        else:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            records: list[RecordDict] = self._table.all(
                formula=Formula(str(formula)).flatten() if formula else None,
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                max_records=max_records,
                sort=convert_sort_options(sort),
                offset=offset,
                time_zone=time_zone,
                user_locale=user_locale,
                **options,
            )
            records = [sanitize_record_dict(r) for r in records]
            result = records

        # Cache store
        if self._cache_seconds > 0:
            self._cache[cache_key] = (result, time.monotonic() + self._cache_seconds)
        # The pyairtable layer hands back base `RecordDict`s; the generated subclass
        # narrows them to its specific `DictType` shape, which we assert here.
        return cast("DictType | list[DictType]", result)

    @overload
    def create(
        self,
        record: DictType | CreateDictType,
        use_field_ids: bool = False,
        **options,
    ) -> DictType:
        """
        Creates a single Airtable record.

        Args:
            record (RecordDict): The record to create.
            use_field_ids (bool, optional): If True, uses field IDs instead of field names. Defaults to False.
            **options: Additional options to pass to the pyAirtable `create` method.
        """
        ...

    @overload
    def create(
        self,
        records: list[DictType] | list[CreateDictType],
        use_field_ids: bool = False,
        **options,
    ) -> list[DictType]:
        """
        Creates multiple Airtable records.

        Args:
            records (list[RecordDict]): The records to create.
            use_field_ids (bool, optional): If True, uses field IDs instead of field names. Defaults to False.
            **options: Additional options to pass to the pyAirtable `batch_create` method.
        """
        ...

    def create(
        self,
        record: DictType | CreateDictType | None = None,
        records: list[DictType] | list[CreateDictType] | None = None,
        use_field_ids: bool = False,
        **options,
    ) -> DictType | list[DictType]:
        self.invalidate_cache()
        calculated_field_keys = self._calculated_field_ids if use_field_ids else self._calculated_field_names
        if isinstance(record, list):
            if len(record) == 0:
                return []
            if len(record) > 0 and isinstance(record[0], dict):
                records = record
                record = None

        if records is not None and isinstance(records, list):
            if records is None:
                raise ValueError("Records to create cannot be None.")
            if len(records) == 0:
                return []
            for r in records:
                r["fields"] = prepare_fields_for_save(r["fields"], calculated_field_keys)
            created = self._table.batch_create([r["fields"] for r in records], use_field_ids=use_field_ids, **options)
            sanitized = [sanitize_record_dict(r) for r in created]
            return cast("list[DictType]", sanitized)
        else:
            if record is None:
                raise ValueError("Record to create cannot be None.")
            record["fields"] = prepare_fields_for_save(record["fields"], calculated_field_keys)
            created_record = self._table.create(fields=record["fields"], use_field_ids=use_field_ids, **options)
            sanitized_record = sanitize_record_dict(created_record)
            return cast("DictType", sanitized_record)

    @overload
    def duplicate(self, record: DictType, *, use_field_ids: bool = False, **options) -> DictType:
        """
        Creates a new Airtable record that is an exact copy of an existing one.

        Args:
            record (RecordDict): The record to copy. Only its id is used — the source is re-read
                from Airtable, so the copy always reflects current server state.
        """
        ...

    @overload
    def duplicate(self, records: list[DictType], *, use_field_ids: bool = False, **options) -> list[DictType]:
        """
        Creates a copy of each of several existing Airtable records.

        Args:
            records (list[RecordDict]): The records to copy.
        """
        ...

    @overload
    def duplicate(self, record_id: str, *, use_field_ids: bool = False, **options) -> DictType:
        """
        Creates a new Airtable record that is an exact copy of the record with this id.

        Args:
            record_id (str): Airtable record ID of the record to copy.
        """
        ...

    @overload
    def duplicate(self, record_ids: list[str], *, use_field_ids: bool = False, **options) -> list[DictType]:
        """
        Creates a copy of each of the records with these ids.

        Args:
            record_ids (list[str]): Airtable record IDs of the records to copy.
        """
        ...

    def duplicate(
        self,
        record: "DictType | list[DictType] | str | list[str] | None" = None,
        records: list[DictType] | None = None,
        record_id: str = "",
        record_ids: list[str] | None = None,
        use_field_ids: bool = False,
        **options,
    ) -> "DictType | list[DictType]":
        """Copy one or more records into brand-new records.

        Every writable field is copied verbatim, including the primary field. Computed fields
        are omitted and recalculated by Airtable, so the copy gets its own id, autonumber and
        timestamps.

        The source is always re-read from Airtable before copying, even when a record dict is
        passed, so the copy reflects current server state and attachment URLs are freshly
        signed. The caller's dict is never mutated (unlike ``create``/``update``, which
        rewrite ``record["fields"]`` in place).
        """
        self.invalidate_cache()

        source_ids: list[str]
        is_list: bool
        if isinstance(record, str):
            source_ids, is_list = [record], False
        elif isinstance(record, list):
            if len(record) == 0:
                return []
            source_ids = cast("list[str]", record) if isinstance(record[0], str) else [r["id"] for r in cast("list[DictType]", record)]
            is_list = True
        elif record is not None:
            source_ids, is_list = [record["id"]], False
        elif record_ids is not None:
            source_ids, is_list = list(record_ids), True
        elif records is not None:
            source_ids, is_list = [r["id"] for r in records], True
        elif record_id:
            source_ids, is_list = [record_id], False
        else:
            raise ValueError("Record to duplicate cannot be None.")

        if not source_ids:
            return []
        unsaved = [i for i, source_id in enumerate(source_ids) if not source_id]
        if unsaved:
            raise ValueError(f"duplicate: record(s) at position(s) {unsaved} have no id; only saved records can be duplicated.")

        # One batched read (ID.in_list), then re-key to input order: Airtable returns records in
        # table order, not the order they were asked for.
        fetched = self.get(record_ids=source_ids, use_field_ids=use_field_ids)
        fetched_list: list[DictType] = fetched if isinstance(fetched, list) else [fetched]
        by_id = {r["id"]: r for r in fetched_list}
        not_found = [source_id for source_id in source_ids if source_id not in by_id]
        if not_found:
            raise RuntimeError(f"duplicate: source record(s) not found: {not_found}")

        calculated_field_keys = self._calculated_field_ids if use_field_ids else self._calculated_field_names
        create_dicts = [
            project_attachments_for_create(prepare_fields_for_save(dict(by_id[source_id]["fields"]), calculated_field_keys))
            for source_id in source_ids
        ]
        created = self._table.batch_create(create_dicts, use_field_ids=use_field_ids, **options)
        copies = cast("list[DictType]", [sanitize_record_dict(r) for r in created])
        return copies if is_list else copies[0]

    @overload
    def update(
        self,
        record: DictType | UpdateDictType,
        use_field_ids: bool = False,
        **options,
    ) -> DictType:
        """
        Updates a single Airtable record.

        Args:
            record (RecordDict): The record to update.
            use_field_ids (bool, optional): If True, uses field IDs instead of field names. Defaults to False.
            **options: Additional options to pass to the pyAirtable `update` method.
        """
        ...

    @overload
    def update(
        self,
        records: list[DictType] | list[UpdateDictType],
        use_field_ids: bool = False,
        **options,
    ) -> list[DictType]:
        """
        Updates multiple Airtable records.

        Args:
            records (list[RecordDict]): The records to update.
            use_field_ids (bool, optional): If True, uses field IDs instead of field names. Defaults to False.
            **options: Additional options to pass to the pyAirtable `batch_update` method.
        """
        ...

    def update(
        self,
        record: DictType | UpdateDictType | None = None,
        records: list[DictType] | list[UpdateDictType] | None = None,
        use_field_ids: bool = False,
        **options,
    ) -> DictType | list[DictType]:
        self.invalidate_cache()
        calculated_field_keys = self._calculated_field_ids if use_field_ids else self._calculated_field_names
        if isinstance(record, list):
            if len(record) == 0:
                return []
            if len(record) > 0 and isinstance(record[0], dict):
                records = record
                record = None

        if records is not None and isinstance(records, list):
            if records is None:
                raise ValueError("Records to update cannot be None.")
            if len(records) == 0:
                return []
            for r in records:
                r["fields"] = prepare_fields_for_save(r["fields"], calculated_field_keys)
            update_dicts: list[UpdateRecordDict] = [{"id": r["id"], "fields": r["fields"]} for r in records]
            updated = self._table.batch_update(
                update_dicts,
                use_field_ids=use_field_ids,
                **options,
            )
            sanitized = [sanitize_record_dict(r) for r in updated]
            return cast("list[DictType]", sanitized)
        else:
            if record is None:
                raise ValueError("Record to update cannot be None.")
            record["fields"] = prepare_fields_for_save(record["fields"], calculated_field_keys)
            updated_record = self._table.update(
                record_id=record["id"],
                fields=record["fields"],
                use_field_ids=use_field_ids,
                **options,
            )
            sanitized_record = sanitize_record_dict(updated_record)
            return cast("DictType", sanitized_record)

    @overload
    def delete(self, record_id: str) -> None:
        """
        Deletes a single Airtable record.

        Args:
            record_id (str): Airtable record ID
        """
        ...

    @overload
    def delete(self, record_ids: list[str]) -> None:
        """
        Deletes multiple Airtable records.

        Args:
            record_ids (list[str]): Airtable record IDs
        """
        ...

    @overload
    def delete(self, record: DictType) -> None:
        """
        Deletes a single Airtable record.

        Args:
            record (RecordDict): The record to delete.
        """
        ...

    @overload
    def delete(self, records: list[DictType]) -> None:
        """
        Deletes multiple Airtable records.

        Args:
            records (list[RecordDict]): The records to delete.
        """
        ...

    def delete(
        self,
        record: DictType | None = None,
        records: list[DictType] = [],
        record_id: str = "",
        record_ids: list[str] = [],
    ) -> None:
        self.invalidate_cache()
        if record:
            self._table.delete(record["id"])
        elif record_id:
            self._table.delete(record_id)
        elif records:
            self._table.batch_delete([r["id"] for r in records])
        elif record_ids:
            self._table.batch_delete(record_ids)
