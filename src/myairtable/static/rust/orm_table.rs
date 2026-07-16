use std::collections::HashMap;
use std::marker::PhantomData;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::de::DeserializeOwned;

use crate::airtable_model::OrmModel;
use crate::client::AirtableClient;
use crate::error::AirtableError;
use crate::types::{AirtableQuery, Record, RecordId};

/// A table accessor for typed ORM model access.
pub struct OrmTable<T> {
    client: Arc<AirtableClient>,
    table_id: &'static str,
    table_name: &'static str,
    cache: Mutex<HashMap<String, (serde_json::Value, Instant)>>,
    cache_seconds: u64,
    _phantom: PhantomData<T>,
}

impl<T: DeserializeOwned + OrmModel> OrmTable<T> {
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
            cache: Mutex::new(HashMap::new()),
            cache_seconds: 0,
            _phantom: PhantomData,
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

    /// Convert a Record (dict layer) into a typed ORM model with client attached.
    fn record_to_model(&self, record: Record) -> Result<T, AirtableError> {
        let fields_json = serde_json::to_value(&record.fields)?;
        let mut model: T = serde_json::from_value(fields_json)?;
        model.set_record_meta(record.id, record.created_time);
        model.set_client(self.client.clone(), self.table_id);
        Ok(model)
    }

    /// Get a single record by ID.
    pub async fn get_one(&self, record_id: &RecordId) -> Result<T, AirtableError> {
        let cache_key = format!("get_one:{}", record_id);
        if let Some(cached) = self.cache_get(&cache_key) {
            let record: Record = serde_json::from_value(cached)?;
            return self.record_to_model(record);
        }
        let record = self
            .client
            .get_record(self.table_id, record_id, true)
            .await?;
        self.cache_set(cache_key, &serde_json::to_value(&record)?);
        self.record_to_model(record)
    }

    /// Get all records matching the query.
    pub async fn get_many(&self, params: &AirtableQuery) -> Result<Vec<T>, AirtableError> {
        let cache_key = format!(
            "get_many:{}",
            serde_json::to_string(params).unwrap_or_default()
        );
        if let Some(cached) = self.cache_get(&cache_key) {
            let records: Vec<Record> = serde_json::from_value(cached)?;
            return records
                .into_iter()
                .map(|r| self.record_to_model(r))
                .collect();
        }

        let mut all_records: Vec<Record> = Vec::new();
        let mut list_params = params.clone();
        list_params.use_field_ids = true;

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
        all_records
            .into_iter()
            .map(|r| self.record_to_model(r))
            .collect()
    }

    /// Create a new record from an ORM model. Only writable fields are sent;
    /// computed fields and record metadata are omitted.
    pub async fn create_one(&self, model: &T, typecast: bool) -> Result<T, AirtableError> {
        self.invalidate_cache();
        let fields = model.to_save_json();
        let record = self
            .client
            .create_record(self.table_id, &fields, true, typecast)
            .await?;
        self.record_to_model(record)
    }

    /// Create multiple records from ORM models.
    pub async fn create_many(&self, models: &[T], typecast: bool) -> Result<Vec<T>, AirtableError> {
        self.invalidate_cache();
        let payloads: Vec<serde_json::Value> = models.iter().map(|m| m.to_save_json()).collect();
        let raw = self
            .client
            .create_records(self.table_id, &payloads, true, typecast)
            .await?;
        raw.into_iter().map(|r| self.record_to_model(r)).collect()
    }

    /// Update an existing record. Sends the model's dirty diff if a snapshot
    /// exists, otherwise the full set of writable fields.
    pub async fn update_one(
        &self,
        record_id: &RecordId,
        model: &T,
        typecast: bool,
    ) -> Result<T, AirtableError> {
        self.invalidate_cache();
        let fields = model.to_save_json();
        let record = self
            .client
            .update_record(self.table_id, record_id, &fields, true, typecast)
            .await?;
        self.record_to_model(record)
    }

    /// Update multiple records.
    pub async fn update_many(
        &self,
        records: &[(&RecordId, &T)],
        typecast: bool,
    ) -> Result<Vec<T>, AirtableError> {
        self.invalidate_cache();
        let payloads: Vec<(&RecordId, serde_json::Value)> = records
            .iter()
            .map(|(id, model)| (*id, model.to_save_json()))
            .collect();
        let borrowed: Vec<(&RecordId, &serde_json::Value)> =
            payloads.iter().map(|(id, v)| (*id, v)).collect();
        let raw = self
            .client
            .update_records(self.table_id, &borrowed, true, typecast)
            .await?;
        raw.into_iter().map(|r| self.record_to_model(r)).collect()
    }

    /// Install a freshly-returned `record` into `model` in place, preserving the ORM meta + snapshot.
    fn install_record(&self, model: &mut T, record: Record) -> Result<(), AirtableError> {
        let result = self.record_to_model(record)?;
        let meta = model.meta_mut();
        let client = meta.client.take();
        let table_id = meta.table_id.take();
        *model = result;
        let meta = model.meta_mut();
        meta.client = client;
        meta.table_id = table_id;
        model.take_snapshot();
        Ok(())
    }

    /// Upsert a single record, updating `model` in place with the server result. With
    /// `fields_to_merge_on`, Airtable matches an existing record by those field values (server-side
    /// performUpsert); otherwise it creates when the model is new / updates by id.
    pub async fn upsert(
        &self,
        model: &mut T,
        fields_to_merge_on: Option<&[&str]>,
        typecast: bool,
    ) -> Result<(), AirtableError> {
        self.invalidate_cache();
        let fields = model.to_save_json();
        let record = match fields_to_merge_on {
            Some(merge) => {
                let id = model.get_id().clone();
                let recs = [(id.as_ref(), &fields)];
                self.client
                    .upsert_records(self.table_id, &recs, merge, true, typecast)
                    .await?
                    .into_iter()
                    .next()
                    .ok_or_else(|| AirtableError::Api {
                        status: 500,
                        code: "UNEXPECTED_RESPONSE".to_string(),
                        body: "upsert returned no records".to_string(),
                    })?
            }
            None if model.is_new() => {
                self.client
                    .create_record(self.table_id, &fields, true, typecast)
                    .await?
            }
            None => {
                let id = model.get_id().as_ref().expect("Record has no ID");
                self.client
                    .update_record(self.table_id, id, &fields, true, typecast)
                    .await?
            }
        };
        self.install_record(model, record)
    }

    /// Upsert multiple records in one batched server-side performUpsert, matching by
    /// `fields_to_merge_on`. Returns the upserted models. (For id-based batch create/update, use
    /// `create_many` / `update_many`.)
    pub async fn upsert_many(
        &self,
        models: &[T],
        fields_to_merge_on: &[&str],
        typecast: bool,
    ) -> Result<Vec<T>, AirtableError> {
        self.invalidate_cache();
        if models.is_empty() {
            return Ok(Vec::new());
        }
        let fields: Vec<_> = models.iter().map(|m| m.to_save_json()).collect();
        let recs: Vec<(Option<&RecordId>, &serde_json::Value)> = models
            .iter()
            .zip(fields.iter())
            .map(|(m, f)| (m.get_id().as_ref(), f))
            .collect();
        let records = self
            .client
            .upsert_records(self.table_id, &recs, fields_to_merge_on, true, typecast)
            .await?;
        records
            .into_iter()
            .map(|r| self.record_to_model(r))
            .collect()
    }

    /// Delete a record.
    pub async fn delete_one(&self, record_id: &RecordId) -> Result<(), AirtableError> {
        self.invalidate_cache();
        self.client.delete_record(self.table_id, record_id).await
    }

    /// Delete multiple records.
    pub async fn delete_many(&self, record_ids: &[RecordId]) -> Result<(), AirtableError> {
        self.invalidate_cache();
        self.client.delete_records(self.table_id, record_ids).await
    }
}
