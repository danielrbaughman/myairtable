from collections.abc import Mapping, Sequence
from typing import Generic, TypeVar

from pyairtable import Table

from .dict_table import DictTable
from .helpers import build_url
from .orm_table import ORMTable
from .table_helpers import CreateDictType, DictType, FieldType, ORMType, UpdateDictType, ViewType


class AirtableTable(ORMTable[ORMType, ViewType, FieldType], Generic[DictType, CreateDictType, UpdateDictType, ORMType, ViewType, FieldType]):
    """
    An abstraction of pyAirtable's `Api.table`, and an interface for working with custom-typed versions of the models/dicts created by the type generator.

    ```python
    record = Airtable().tablename.get("rec1234567890")
    ```

    You can also access the RecordDict tables with `.dict`.

    ```python
    record = Airtable().tablename.dict.get("rec1234567890")
    ```

    You can also use the ORM Models directly. See https://pyairtable.readthedocs.io/en/stable/orm.html#
    """

    api_key: str
    base_id: str
    id: str

    _dict_cls: type[DictType]
    _create_cls: type[CreateDictType]
    _update_cls: type[UpdateDictType]
    _orm_cls: type[ORMType]
    _table: Table
    """The original pyAirtable instance. Returns un-typed RecordDicts."""

    _calculated_field_names: Sequence[str]
    _calculated_field_ids: Sequence[str]
    _view_name_id_mapping: Mapping[ViewType, str]
    _field_names: Sequence[str]

    dict: DictTable[DictType, UpdateDictType, CreateDictType, ViewType, FieldType]
    """A table that returns typed RecordDicts."""

    @classmethod
    # Named-constructor override: AirtableTable needs the dict/create/update classes
    # that ORMTable.from_table doesn't take, so the signature intentionally differs.
    def from_table(  # ty: ignore[invalid-method-override]
        cls,
        table: Table,
        dict_cls: type[DictType],
        create_cls: type[CreateDictType],
        update_cls: type[UpdateDictType],
        orm_cls: type[ORMType],
        calculated_field_names: Sequence[str],
        calculated_field_ids: Sequence[str],
        view_name_id_mapping: "Mapping[ViewType, str]",
        field_names: Sequence[str],
        cache_seconds: int = 0,
    ) -> "AirtableTable[DictType, CreateDictType, UpdateDictType, ORMType, ViewType, FieldType]":
        instance = cls()
        instance._table = table
        instance.id = table.id
        instance.base_id = table.base.id
        instance._dict_cls = dict_cls
        instance._create_cls = create_cls
        instance._update_cls = update_cls
        instance._orm_cls = orm_cls

        instance._calculated_field_names = calculated_field_names
        instance._calculated_field_ids = calculated_field_ids
        instance._view_name_id_mapping = view_name_id_mapping
        instance._field_names = field_names
        instance._cache_seconds = cache_seconds
        instance._cache = {}

        instance.dict = DictTable[DictType, UpdateDictType, CreateDictType, ViewType, FieldType].from_table(
            table,
            dict_cls,
            instance._update_cls,
            instance._create_cls,
            calculated_field_names,
            calculated_field_ids,
            view_name_id_mapping,
            field_names,
            cache_seconds=cache_seconds,
        )

        return instance

    def invalidate_cache(self) -> None:
        """Clears the cache for both ORM and Dict tables."""
        super().invalidate_cache()
        self.dict.invalidate_cache()

    def url(self, view: ViewType | None = None) -> str:
        """Get the URL for the Airtable table, with optional view."""
        if view:
            return build_url(base_id=self.base_id, table_id=self.id, view_id=self.get_view_id(view))
        else:
            return build_url(base_id=self.base_id, table_id=self.id)


# endregion

TableType = TypeVar("TableType", bound=AirtableTable)
