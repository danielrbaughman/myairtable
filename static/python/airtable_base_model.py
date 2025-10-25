from datetime import datetime
from typing import Optional

from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict
from pydantic import BaseModel, ConfigDict


class AirtableBaseModel(BaseModel):
    """A shared basis for Pydantic models of Airtable records."""

    model_config: ConfigDict = ConfigDict(from_attributes=True)

    id: str = ""
    created_time: Optional[datetime] = None

    @classmethod
    def from_record_dict(cls, record: RecordDict) -> "AirtableBaseModel":
        instance = cls()
        instance.id = record.get("id", "")
        instance.created_time = record.get("createdTime", None)
        return instance

    def to_record_dict(self, use_field_ids: bool = False) -> RecordDict:
        """Converts the current instance into a typed RecordDict object."""
        return RecordDict(id=self.id, createdTime=self.created_time, fields={})

    def to_update_record_dict(self, use_field_ids: bool = False) -> UpdateRecordDict:
        """Converts the current instance into a typed UpdateRecordDict object."""
        return UpdateRecordDict(id=self.id, fields={})

    def to_create_record_dict(self, use_field_ids: bool = False) -> CreateRecordDict:
        """Converts the current instance into a typed CreateRecordDict object."""
        return CreateRecordDict(fields={})

    def _to_fields(self, use_field_ids: bool) -> dict:
        """Convert the current instance into a fields dict for Airtable."""
        return {}

    def _update_from_record_dict(self, record: RecordDict):
        """Update the current instance's fields from a RecordDict."""
        pass
