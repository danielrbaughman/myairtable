use std::marker::PhantomData;
use std::sync::Arc;

use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::client::AirtableClient;
use crate::error::AirtableError;
use crate::types::{Fields, ListParams, OrmModel, Record, RecordId};

/// A table accessor for typed ORM model access.
pub struct OrmTable<T, C> {
    client: Arc<AirtableClient>,
    table_id: &'static str,
    table_name: &'static str,
    _phantom: PhantomData<(T, C)>,
}

impl<T: DeserializeOwned + OrmModel, C: Serialize> OrmTable<T, C> {
    /// Create a new OrmTable.
    pub fn new(
        client: Arc<AirtableClient>,
        table_id: &'static str,
        table_name: &'static str,
    ) -> Self {
        Self {
            client,
            table_id,
            table_name,
            _phantom: PhantomData,
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

    /// Convert a Record (dict layer) into a typed ORM model.
    fn record_to_model(&self, record: Record) -> Result<T, AirtableError> {
        let fields_json = serde_json::to_value(&record.fields)?;
        let mut model: T = serde_json::from_value(fields_json)?;
        model.set_record_meta(record.id, record.created_time);
        Ok(model)
    }

    /// Get a single record by ID.
    pub async fn get_one(&self, record_id: &RecordId) -> Result<T, AirtableError> {
        let record = self
            .client
            .get_record(self.table_id, record_id, true)
            .await?;
        self.record_to_model(record)
    }

    /// Get multiple records.
    pub async fn get_many(
        &self,
        params: &ListParams,
    ) -> Result<(Vec<T>, Option<String>), AirtableError> {
        let mut list_params = params.clone();
        list_params.use_field_ids = true;
        let page = self
            .client
            .list_records(self.table_id, &list_params)
            .await?;
        let models: Result<Vec<T>, _> = page
            .records
            .into_iter()
            .map(|r| self.record_to_model(r))
            .collect();
        Ok((models?, page.offset))
    }

    /// Create a new record.
    pub async fn create_one(&self, fields: &C) -> Result<T, AirtableError> {
        let record = self
            .client
            .create_record(self.table_id, fields, true)
            .await?;
        self.record_to_model(record)
    }

    /// Create multiple records (batched in groups of 10).
    pub async fn create_many(&self, records: &[C]) -> Result<Vec<T>, AirtableError> {
        let raw = self
            .client
            .create_records(self.table_id, records, true)
            .await?;
        raw.into_iter().map(|r| self.record_to_model(r)).collect()
    }

    /// Update an existing record.
    pub async fn update_one(&self, record_id: &RecordId, fields: &C) -> Result<T, AirtableError> {
        let record = self
            .client
            .update_record(self.table_id, record_id, fields, true)
            .await?;
        self.record_to_model(record)
    }

    /// Update multiple records (batched in groups of 10).
    pub async fn update_many(&self, records: &[(&RecordId, &C)]) -> Result<Vec<T>, AirtableError> {
        let raw = self
            .client
            .update_records(self.table_id, records, true)
            .await?;
        raw.into_iter().map(|r| self.record_to_model(r)).collect()
    }

    /// Delete a record.
    pub async fn delete_one(&self, record_id: &RecordId) -> Result<(), AirtableError> {
        self.client.delete_record(self.table_id, record_id).await
    }

    /// Delete multiple records (batched in groups of 10).
    pub async fn delete_many(&self, record_ids: &[RecordId]) -> Result<(), AirtableError> {
        self.client.delete_records(self.table_id, record_ids).await
    }
}
