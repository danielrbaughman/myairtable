use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::client::AirtableClient;
use crate::error::AirtableError;
use crate::types::{AirtableQuery, Fields, Record, RecordId};

/// A table accessor for dict-style (field ID / field name) record access.
pub struct StructTable {
    client: Arc<AirtableClient>,
    table_id: &'static str,
    table_name: &'static str,
    cache: Mutex<HashMap<String, (serde_json::Value, Instant)>>,
    cache_seconds: u64,
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
            cache: Mutex::new(HashMap::new()),
            cache_seconds: 0,
        }
    }

    /// Set cache TTL in seconds. 0 = disabled (default).
    pub fn set_cache_seconds(&mut self, seconds: u64) {
        self.cache_seconds = seconds;
    }

    /// The Airtable table ID.
    pub fn table_id(&self) -> &'static str {
        self.table_id
    }

    /// The Airtable table name.
    pub fn table_name(&self) -> &'static str {
        self.table_name
    }

    /// Get the Airtable web URL for this table.
    pub fn url(&self) -> String {
        crate::types::build_url(self.client.base_id(), self.table_id, "", "")
    }

    /// Clear the response cache.
    pub fn invalidate_cache(&self) {
        self.cache.lock().unwrap().clear();
    }

    fn cache_get(&self, key: &str) -> Option<serde_json::Value> {
        if self.cache_seconds == 0 {
            return None;
        }
        let cache = self.cache.lock().unwrap();
        if let Some((value, expires_at)) = cache.get(key) {
            if Instant::now() < *expires_at {
                return Some(value.clone());
            }
        }
        None
    }

    fn cache_set(&self, key: String, value: &serde_json::Value) {
        if self.cache_seconds == 0 {
            return;
        }
        let expires_at = Instant::now() + Duration::from_secs(self.cache_seconds);
        self.cache
            .lock()
            .unwrap()
            .insert(key, (value.clone(), expires_at));
    }

    /// Get a single record by ID.
    pub async fn get_one(
        &self,
        record_id: &RecordId,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        let cache_key = format!("get_one:{}:{}", record_id, use_field_ids);
        if let Some(cached) = self.cache_get(&cache_key) {
            return Ok(serde_json::from_value(cached)?);
        }
        let record = self
            .client
            .get_record(self.table_id, record_id, use_field_ids)
            .await?;
        self.cache_set(cache_key, &serde_json::to_value(&record)?);
        Ok(record)
    }

    /// Get all records matching the query, automatically paginating.
    pub async fn get_many(&self, params: &AirtableQuery) -> Result<Vec<Record>, AirtableError> {
        let cache_key = format!(
            "get_many:{}",
            serde_json::to_string(params).unwrap_or_default()
        );
        if let Some(cached) = self.cache_get(&cache_key) {
            return Ok(serde_json::from_value(cached)?);
        }

        let mut all_records = Vec::new();
        let mut list_params = params.clone();

        loop {
            let page = self
                .client
                .list_records(self.table_id, &list_params)
                .await?;
            all_records.extend(page.records);
            match page.offset {
                Some(offset) => list_params.offset = Some(offset),
                None => break,
            }
        }

        self.cache_set(cache_key, &serde_json::to_value(&all_records)?);
        Ok(all_records)
    }

    /// Create a new record.
    pub async fn create_one(
        &self,
        fields: &Fields,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        self.invalidate_cache();
        self.client
            .create_record(self.table_id, fields, use_field_ids, false)
            .await
    }

    /// Create multiple records (batched in groups of 10).
    pub async fn create_many(
        &self,
        records: &[Fields],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        self.invalidate_cache();
        self.client
            .create_records(self.table_id, records, use_field_ids, false)
            .await
    }

    /// Update an existing record.
    pub async fn update_one(
        &self,
        record_id: &RecordId,
        fields: &Fields,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        self.invalidate_cache();
        self.client
            .update_record(self.table_id, record_id, fields, use_field_ids, false)
            .await
    }

    /// Update multiple records (batched in groups of 10).
    pub async fn update_many(
        &self,
        records: &[(&RecordId, &Fields)],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        self.invalidate_cache();
        self.client
            .update_records(self.table_id, records, use_field_ids, false)
            .await
    }

    /// Upsert a single record. Creates if record_id is None, updates if Some.
    pub async fn upsert_one(
        &self,
        record_id: Option<&RecordId>,
        fields: &Fields,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        self.invalidate_cache();
        match record_id {
            Some(id) => {
                self.client
                    .update_record(self.table_id, id, fields, use_field_ids, false)
                    .await
            }
            None => {
                self.client
                    .create_record(self.table_id, fields, use_field_ids, false)
                    .await
            }
        }
    }

    /// Delete a record.
    pub async fn delete_one(&self, record_id: &RecordId) -> Result<(), AirtableError> {
        self.invalidate_cache();
        self.client.delete_record(self.table_id, record_id).await
    }

    /// Delete multiple records (batched in groups of 10).
    pub async fn delete_many(&self, record_ids: &[RecordId]) -> Result<(), AirtableError> {
        self.invalidate_cache();
        self.client.delete_records(self.table_id, record_ids).await
    }
}
