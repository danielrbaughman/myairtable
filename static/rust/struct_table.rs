use std::sync::Arc;

use crate::client::AirtableClient;
use crate::error::AirtableError;
use crate::pagination::PaginatedResponse;
use crate::types::{Fields, Record, RecordId};

/// A table accessor for dict-style (field ID / field name) record access.
pub struct StructTable {
    client: Arc<AirtableClient>,
    table_id: &'static str,
    table_name: &'static str,
}

impl StructTable {
    /// Create a new StructTable.
    pub fn new(
        client: Arc<AirtableClient>,
        table_id: &'static str,
        table_name: &'static str,
    ) -> Self {
        Self {
            client,
            table_id,
            table_name,
        }
    }

    /// The Airtable table ID.
    pub fn table_id(&self) -> &'static str {
        self.table_id
    }

    /// The Airtable table name.
    pub fn table_name(&self) -> &'static str {
        self.table_name
    }

    /// List records.
    pub async fn list(
        &self,
        use_field_ids: bool,
        offset: Option<&str>,
    ) -> Result<PaginatedResponse, AirtableError> {
        self.client
            .list_records(self.table_id, use_field_ids, offset)
            .await
    }

    /// Get a single record by ID.
    pub async fn get(
        &self,
        record_id: &RecordId,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        self.client
            .get_record(self.table_id, record_id, use_field_ids)
            .await
    }

    /// Create a new record.
    pub async fn create(
        &self,
        fields: &Fields,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        self.client
            .create_record(self.table_id, fields, use_field_ids)
            .await
    }

    /// Create multiple records (batched in groups of 10).
    pub async fn create_many(
        &self,
        records: &[Fields],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        self.client
            .create_records(self.table_id, records, use_field_ids)
            .await
    }

    /// Update an existing record.
    pub async fn update(
        &self,
        record_id: &RecordId,
        fields: &Fields,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        self.client
            .update_record(self.table_id, record_id, fields, use_field_ids)
            .await
    }

    /// Update multiple records (batched in groups of 10).
    pub async fn update_many(
        &self,
        records: &[(&RecordId, &Fields)],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        self.client
            .update_records(self.table_id, records, use_field_ids)
            .await
    }

    /// Delete a record.
    pub async fn delete(&self, record_id: &RecordId) -> Result<(), AirtableError> {
        self.client.delete_record(self.table_id, record_id).await
    }

    /// Delete multiple records (batched in groups of 10).
    pub async fn delete_many(&self, record_ids: &[RecordId]) -> Result<(), AirtableError> {
        self.client.delete_records(self.table_id, record_ids).await
    }
}
