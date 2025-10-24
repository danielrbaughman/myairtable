from typing import Generic, Optional, overload

from pyairtable import Table
from pyairtable.api.types import RecordDict

from .formula import id_in_list
from .helpers import validate_keys
from .table_helpers import DictType, FieldType, ORMType, PydanticType, ViewType, prepare_fields_for_save, sanitize_record_dict


class PydanticTable(Generic[ORMType, PydanticType, ViewType, FieldType]):
    """An abstraction of pyAirtable's `Table` for Pydantic models."""

    _pydantic_cls: type[PydanticType]
    _table: Table
    """The original pyAirtable instance. Returns un-typed RecordDicts."""
    _calculated_field_names: list[str]
    _calculated_field_ids: list[str]
    _view_name_id_mapping: dict[ViewType, str]
    _field_names: list[str]
    _orm_cls: type[ORMType]

    @classmethod
    def from_table(
        cls,
        table: Table,
        pydantic_cls: type[PydanticType],
        calculated_field_names: list[str],
        calculated_field_ids: list[str],
        view_name_id_mapping: "dict[ViewType, str]",
        field_names: list[str],
        orm_cls: type[ORMType],
    ) -> "PydanticTable[ORMType, PydanticType, ViewType, FieldType]":
        instance = cls()
        instance._table = table
        instance._pydantic_cls = pydantic_cls
        instance._calculated_field_names = calculated_field_names
        instance._calculated_field_ids = calculated_field_ids
        instance._view_name_id_mapping = view_name_id_mapping
        instance._field_names = field_names
        instance._orm_cls = orm_cls
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
    ) -> PydanticType:
        """
        Retrieves a single Airtable record as a Pydantic model.

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
    ) -> list[PydanticType]:
        """
        Retrieves multiple Airtable records as Pydantic models.

        Args:
            record_ids (list[str]): Airtable record IDs
            use_field_ids (bool, optional): If True, returns field IDs instead of field names. Defaults to True.
            fields (list[str] | None, optional): A list of fields to retrieve. If None, retrieves all fields. Defaults to None.
            **options: Additional options to pass to the pyAirtable `get` method.
        """
        ...

    @overload
    def get(
        self,
        formula: str = "",
        view: Optional[ViewType] = None,
        use_field_ids: bool = True,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        **options,
    ) -> list[PydanticType]:
        """
        Retrieves multiple Airtable records as Pydantic models.

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
        formula: str = "",
        view: Optional[ViewType] = None,
        use_field_ids: bool = True,
        page_size: int = 100,
        fields: list[FieldType] | None = None,
        **options,
    ) -> PydanticType | list[PydanticType]:
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
            record_model: PydanticType = self._pydantic_cls.from_record_dict(record_dict)
            record_model._orm = self._orm_cls.from_record(record_dict)
            return record_model
        elif len(record_ids) > 0:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            record_dicts: list[RecordDict] = self._table.all(
                formula=id_in_list(record_ids),
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                **options,
            )
            record_dicts: list[DictType] = [sanitize_record_dict(r) for r in record_dicts]
            record_models: list[PydanticType] = [self._pydantic_cls.from_record_dict(r) for r in record_dicts]
            for record_model, record_dict in zip(record_models, record_dicts):
                record_model._orm = self._orm_cls.from_record(record_dict)
            return record_models
        else:
            if page_size > 100:
                raise ValueError("Page size cannot exceed 100.")
            record_dicts: list[RecordDict] = self._table.all(
                formula=formula,
                view=self.get_view_id(view) if view else None,
                use_field_ids=use_field_ids,
                page_size=page_size,
                fields=fields,
                **options,
            )
            record_dicts: list[DictType] = [sanitize_record_dict(r) for r in record_dicts]
            record_models: list[PydanticType] = [self._pydantic_cls.from_record_dict(r) for r in record_dicts]
            return record_models

    @overload
    def create(self, record: PydanticType) -> PydanticType:
        """
        Creates a single Airtable record.

        Args:
            record (Model): The record to create.
        """
        ...

    @overload
    def create(self, records: list[PydanticType]) -> list[PydanticType]:
        """
        Creates multiple Airtable records.

        Args:
            records (list[Model]): The records to create.
        """
        ...

    def create(self, record_s: PydanticType | list[PydanticType]) -> PydanticType | list[PydanticType]:
        if isinstance(record_s, list):
            record_dicts = [r.to_create_record_dict() for r in record_s]
            for r in record_dicts:
                r["fields"] = prepare_fields_for_save(r["fields"], self._calculated_field_ids)
            records = self._table.batch_create([r["fields"] for r in record_dicts], use_field_ids=True)
            records = [sanitize_record_dict(r) for r in records]
            record_models = []
            for record in records:
                record_orm = self._orm_cls.from_record(record)
                record_model = self._pydantic_cls.from_record_dict(record)
                record_models.append(record_model)
            return record_models
        else:
            record_dict = record_s.to_create_record_dict()
            record_dict["fields"] = prepare_fields_for_save(record_dict["fields"], self._calculated_field_ids)
            record = self._table.create(fields=record_dict["fields"], use_field_ids=True)
            record = sanitize_record_dict(record)
            record_orm = self._orm_cls.from_record(record)
            record_model = self._pydantic_cls.from_record_dict(record)
            record_model._orm = record_orm
            return record_model

    @overload
    def update(self, record: PydanticType) -> PydanticType:
        """
        Updates a single Airtable record.

        Args:
            record (Model): The record to update.
        """
        ...

    @overload
    def update(self, records: list[PydanticType]) -> list[PydanticType]:
        """
        Updates multiple Airtable records.

        Args:
            records (list[Model]): The records to update.
        """
        ...

    def update(self, record_s: PydanticType | list[PydanticType]) -> PydanticType | list[PydanticType] | None:
        if isinstance(record_s, list):
            record_dicts = [r.to_update_record_dict(use_field_ids=True) for r in record_s]
            for r in record_dicts:
                r["fields"] = prepare_fields_for_save(r["fields"], self._calculated_field_ids)
            records = self._table.batch_update(record_dicts, use_field_ids=True)
            records = [sanitize_record_dict(r) for r in records]
            record_models = []
            for record in records:
                record_orm = self._orm_cls.from_record(record)
                record_model = self._pydantic_cls.from_record_dict(record)
                record_model._orm = record_orm
                record_models.append(record_model)
            return record_models
        else:
            record_dict = record_s.to_update_record_dict(use_field_ids=True)
            record_dict["fields"] = prepare_fields_for_save(record_dict["fields"], self._calculated_field_ids)
            record = self._table.update(record_id=record_dict["id"], fields=record_dict["fields"], use_field_ids=True)
            record = sanitize_record_dict(record)
            record_orm = self._orm_cls.from_record(record)
            record_model = self._pydantic_cls.from_record_dict(record)
            record_model._orm = record_orm
            return record_model

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
    def delete(self, record: PydanticType) -> None:
        """
        Deletes a single Airtable record.

        Args:
            record (PydanticType): The record to delete.
        """
        ...

    @overload
    def delete(self, records: list[PydanticType]) -> None:
        """
        Deletes multiple Airtable records.

        Args:
            records (list[PydanticType]): The records to delete.
        """
        ...

    def delete(
        self,
        record: PydanticType | None = None,
        records: list[PydanticType] = [],
        record_id: str = "",
        record_ids: list[str] = [],
    ) -> None:
        if record:
            self._table.delete(record.id)
        elif record_id:
            self._table.delete(record_id)
        elif records:
            self._table.batch_delete([r.id for r in records])
        elif record_ids:
            self._table.batch_delete(record_ids)
