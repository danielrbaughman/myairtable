from typing import Generic, Optional, overload

from pyairtable import Table
from pyairtable.api.types import RecordDict
from pyairtable.formulas import Formula

from .formula import ID
from .helpers import validate_keys
from .table_helpers import DictType, FieldType, ORMType, ViewType, sanitize_record_dict


class ORMTable(Generic[ORMType, ViewType, FieldType]):
    """An abstraction of pyAirtable's `Table` for ORM models."""

    _orm_cls: type[ORMType]
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
        model_cls: type[ORMType],
        calculated_field_names: list[str],
        calculated_field_ids: list[str],
        view_name_id_mapping: "dict[ViewType, str]",
        field_names: list[str],
    ) -> "ORMTable[ORMType, ViewType, FieldType]":
        instance = cls()
        instance._table = table
        instance._orm_cls = model_cls
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
        use_field_ids: bool = True,
        fields: list[FieldType] | None = None,
        **options,
    ) -> ORMType:
        """
        Retrieves a single Airtable record as an ORM model.

        Args:
            record_id (str): Airtable record ID
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to True.
            fields (list[str] | None, optional): A list of fields to retrieve. If None, retrieves all fields. Defaults to None.
            **options: Additional options to pass to the pyAirtable `get` method.
        """
        ...

    @overload
    def get(
        self,
        record_ids: list[str],
        use_field_ids: bool = True,
        fields: list[FieldType] | None = None,
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
        formula: Optional[Formula] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = True,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
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
        record_id: str = "",
        record_ids: list[str] = [],
        formula: Optional[Formula] = None,
        view: Optional[ViewType] = None,
        use_field_ids: bool = True,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        **options,
    ) -> ORMType | list[ORMType]:
        if fields is not None:
            validate_keys(fields, self._field_names)

        if record_id:
            record_dict: RecordDict = self._table.get(
                record_id,
                use_field_ids=use_field_ids,
                fields=fields,
                **options,
            )
            record_dict: DictType = sanitize_record_dict(record_dict)
            record_orm: ORMType = self._orm_cls.from_record(record_dict)
            return record_orm
        elif len(record_ids) > 0:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            record_dicts: list[RecordDict] = self._table.all(
                formula=ID.in_list(record_ids),
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                **options,
            )
            record_dicts: list[DictType] = [sanitize_record_dict(r) for r in record_dicts]
            record_orms: list[ORMType] = [self._orm_cls.from_record(r) for r in record_dicts]
            return record_orms
        else:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            record_dicts: list[RecordDict] = self._table.all(
                formula=formula.flatten() if formula else None,
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                **options,
            )
            record_dicts: list[DictType] = [sanitize_record_dict(r) for r in record_dicts]
            record_orms: list[ORMType] = [self._orm_cls.from_record(r) for r in record_dicts]
            return record_orms

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

    def create(self, record_s: ORMType | list[ORMType]) -> ORMType | list[ORMType]:
        if isinstance(record_s, list):
            self._orm_cls.batch_save(record_s)
            new_records = self.get(record_ids=[r.id for r in record_s])
            return new_records
        else:
            if not record_s:
                raise ValueError("Record to create cannot be None.")
            record_s.save()  # type: ignore
            new_record = self.get(record_id=record_s.id)  # type: ignore
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

    def update(self, record_s: ORMType | list[ORMType]) -> ORMType | list[ORMType]:
        if isinstance(record_s, list):
            self._orm_cls.batch_save(record_s)
            updated_records = self.get(record_ids=[r.id for r in record_s])
            return updated_records
        else:
            if not record_s:
                raise ValueError("Record cannot be None.")
            record_s.save()  # type: ignore
            updated_record = self.get(record_id=record_s.id)  # type: ignore
            return updated_record

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
        if record:
            record.delete()
        elif record_id:
            self._table.delete(record_id)
        elif records:
            self._orm_cls.batch_delete(records)
        elif record_ids:
            self._table.batch_delete(record_ids)
