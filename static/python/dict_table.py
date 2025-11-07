from typing import Generic, Optional, overload

from pyairtable import Table
from pyairtable.api.types import RecordDict
from pyairtable.formulas import Formula

from .formula import ID
from .helpers import validate_keys
from .table_helpers import CreateDictType, DictType, FieldType, UpdateDictType, ViewType, prepare_fields_for_save, sanitize_record_dict


class DictTable(Generic[DictType, UpdateDictType, CreateDictType, ViewType, FieldType]):
    """An abstraction of pyAirtable's `Table` for typed RecordDicts."""

    _dict_cls: type[DictType]
    _update_cls: type[UpdateDictType]
    _create_cls: type[CreateDictType]
    _table: Table
    """The original pyAirtable instance. Returns un-typed RecordDicts."""
    _calculated_field_names: list[str]
    _calculated_field_ids: list[str]
    _view_name_id_mapping: dict[ViewType, str]
    _field_names: list[str]

    @classmethod
    def from_table(
        cls,
        table: Table,
        dict_cls: type[DictType],
        update_cls: type[UpdateDictType],
        create_cls: type[CreateDictType],
        calculated_field_names: list[str],
        calculated_field_ids: list[str],
        view_name_id_mapping: "dict[ViewType, str]",
        field_names: list[str],
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
        return instance

    def get_view_id(self, view: ViewType) -> str:
        """Resolves an Airtable view name to the corresponding ID, if available."""
        id = self._view_name_id_mapping.get(view, view)
        return id if id else view

    @overload
    def get(
        self,
        record_id: str,
        use_field_ids: bool = False,
        max_records: int | None = None,
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
        formula: Optional[Formula] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = False,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        max_records: int | None = None,
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
        record_id: str = "",
        record_ids: list[str] = [],
        formula: Optional[Formula] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = False,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        max_records: int | None = None,
        **options,
    ) -> DictType | list[DictType]:
        if fields is not None:
            validate_keys(fields, self._field_names)

        if isinstance(record_id, list) and len(record_id) > 0 and isinstance(record_id[0], str):
            record_ids = record_id
            record_id = None  # type: ignore

        if record_id and isinstance(record_id, str):
            record: RecordDict = self._table.get(
                record_id,
                use_field_ids=use_field_ids,
                max_records=max_records,
                **options,
            )
            record: DictType = sanitize_record_dict(record)
            return record
        elif len(record_ids) > 0:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            records: list[RecordDict] = self._table.all(
                formula=ID.in_list(record_ids),
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                **options,
            )
            records: list[DictType] = [sanitize_record_dict(r) for r in records]
            return records
        else:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            records: list[RecordDict] = self._table.all(
                formula=formula.flatten() if formula else None,
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                max_records=max_records,
                **options,
            )
            records: list[DictType] = [sanitize_record_dict(r) for r in records]
            return records

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
        record: DictType | CreateDictType,
        records: list[DictType] | list[CreateDictType],
        use_field_ids: bool = False,
        **options,
    ) -> DictType | list[DictType]:
        calculated_field_keys = self._calculated_field_ids if use_field_ids else self._calculated_field_names
        if isinstance(record, list) and len(record) > 0 and (isinstance(record[0], DictType) or isinstance(record[0], CreateDictType)):
            records = record
            record = None  # type: ignore

        if records:
            for r in records:
                r["fields"] = prepare_fields_for_save(r["fields"], calculated_field_keys)
            records = self._table.batch_create([r["fields"] for r in records], use_field_ids=use_field_ids, **options)
            records = [sanitize_record_dict(r) for r in records]
            return records
        else:
            if not record:
                raise ValueError("Record to create cannot be None.")
            record["fields"] = prepare_fields_for_save(record["fields"], calculated_field_keys)  # type: ignore
            record = self._table.create(fields=record["fields"], use_field_ids=use_field_ids, **options)
            record = sanitize_record_dict(record)
            return record

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
        record: DictType | UpdateDictType,
        records: list[DictType] | list[UpdateDictType] = [],
        use_field_ids: bool = False,
        **options,
    ) -> DictType | list[DictType]:
        calculated_field_keys = self._calculated_field_ids if use_field_ids else self._calculated_field_names
        if isinstance(record, list) and len(record) > 0 and (isinstance(record[0], DictType) or isinstance(record[0], UpdateDictType)):
            records = record
            record = None  # type: ignore

        if isinstance(records, list):
            for r in records:
                r["fields"] = prepare_fields_for_save(r["fields"], calculated_field_keys)
            update_dicts: list[UpdateDictType] = [{"id": r["id"], "fields": r["fields"]} for r in records]
            records = self._table.batch_update(
                update_dicts,
                use_field_ids=use_field_ids,
                **options,
            )
            records = [sanitize_record_dict(r) for r in records]
            return records
        else:
            record["fields"] = prepare_fields_for_save(record["fields"], calculated_field_keys)  # type: ignore
            record = self._table.update(
                record_id=record["id"],
                fields=record["fields"],
                use_field_ids=use_field_ids,
                **options,
            )
            record = sanitize_record_dict(record)
            return record

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
        if record:
            self._table.delete(record["id"])
        elif record_id:
            self._table.delete(record_id)
        elif records:
            self._table.batch_delete([r["id"] for r in records])
        elif record_ids:
            self._table.batch_delete(record_ids)
