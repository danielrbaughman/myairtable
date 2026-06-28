use std::sync::Arc;

use crate::client::AirtableClient;
use crate::error::AirtableError;
use crate::types::{Fields, Record, RecordId};

/// Shared internal state for ORM models.
#[derive(Debug, Clone, Default)]
pub struct ModelMeta {
    pub client: Option<Arc<AirtableClient>>,
    pub table_id: Option<&'static str>,
    pub snapshot: Option<serde_json::Value>,
}

/// Trait for ORM models with instance methods (save, fetch, delete).
///
/// Models only need to implement `meta()` and `meta_mut()` to access their `ModelMeta`.
/// All ORM logic (save, fetch, delete, change detection) is provided as default methods.
pub trait OrmModel: Sized + Send + Sync + serde::Serialize + serde::de::DeserializeOwned {
    /// Access the model's internal metadata.
    fn meta(&self) -> &ModelMeta;

    /// Mutably access the model's internal metadata.
    fn meta_mut(&mut self) -> &mut ModelMeta;

    /// Get a reference to the model's id field.
    fn get_id(&self) -> &Option<RecordId>;

    /// Set the model's id field.
    fn set_id(&mut self, id: Option<RecordId>);

    /// Get a reference to the model's created_time field.
    fn get_created_time(&self) -> &Option<String>;

    /// Set the model's created_time field.
    fn set_created_time(&mut self, created_time: Option<String>);

    /// Set record metadata after deserialization from API.
    fn set_record_meta(&mut self, id: RecordId, created_time: Option<String>) {
        self.set_id(Some(id));
        self.set_created_time(created_time);
        self.take_snapshot();
    }

    /// Attach a client and table ID so the model can make API calls.
    fn set_client(&mut self, client: Arc<AirtableClient>, table_id: &'static str) {
        let meta = self.meta_mut();
        meta.client = Some(client);
        meta.table_id = Some(table_id);
    }

    /// Whether this is a new record (no ID yet).
    fn is_new(&self) -> bool {
        self.get_id().is_none()
    }

    /// Take a snapshot of the current field state (called after fetch/save).
    fn take_snapshot(&mut self) {
        let snap = serde_json::to_value(&*self).unwrap_or_default();
        self.meta_mut().snapshot = Some(snap);
    }

    /// Serialize the model's field values to a JSON object. Keys are field IDs.
    fn to_json(&self) -> serde_json::Value {
        serde_json::to_value(self).unwrap_or_default()
    }

    /// Convert the model to a Record (dict layer type).
    fn to_record(&self) -> Record {
        let fields_json = serde_json::to_value(self).unwrap_or_default();
        let fields: Fields = serde_json::from_value(fields_json).unwrap_or_default();
        Record {
            id: self.get_id().clone().unwrap_or_default(),
            fields,
            created_time: self.get_created_time().clone(),
        }
    }

    /// Build a JSON value with only changed fields (for update) or all set fields (for create).
    fn to_save_json(&self) -> serde_json::Value {
        let current = serde_json::to_value(self).unwrap_or_default();
        let snapshot = &self.meta().snapshot;
        if self.is_new() || snapshot.is_none() {
            return current;
        }
        let snapshot = snapshot.as_ref().unwrap();
        let mut diff = serde_json::Map::new();
        if let (serde_json::Value::Object(cur), serde_json::Value::Object(snap)) =
            (&current, snapshot)
        {
            for (k, v) in cur {
                if snap.get(k) != Some(v) {
                    diff.insert(k.clone(), v.clone());
                }
            }
            for k in snap.keys() {
                if !cur.contains_key(k) {
                    diff.insert(k.clone(), serde_json::Value::Null);
                }
            }
        }
        serde_json::Value::Object(diff)
    }

    /// Apply an API record response to this model, updating all fields and taking a snapshot.
    fn apply_record(&mut self, record: Record) -> Result<(), AirtableError> {
        let fields_json = serde_json::to_value(&record.fields)?;
        let client = self.meta_mut().client.take();
        let table_id = self.meta_mut().table_id.take();
        *self = serde_json::from_value(fields_json)?;
        let meta = self.meta_mut();
        meta.client = client;
        meta.table_id = table_id;
        self.set_id(Some(record.id));
        self.set_created_time(record.created_time);
        self.take_snapshot();
        Ok(())
    }

    /// Save the record. Creates if new, updates if existing.
    fn save(&mut self) -> impl std::future::Future<Output = Result<(), AirtableError>> + Send {
        async {
            let client = self
                .meta()
                .client
                .as_ref()
                .expect("No client attached. Use OrmTable or set_client().")
                .clone();
            let table_id = self.meta().table_id.expect("No table_id attached.");
            let fields = self.to_save_json();
            let record = if self.is_new() {
                client.create_record(table_id, &fields, true, false).await?
            } else {
                let id = self.get_id().as_ref().expect("Record has no ID");
                client
                    .update_record(table_id, id, &fields, true, false)
                    .await?
            };
            self.apply_record(record)
        }
    }

    /// Fetch the record from the API by ID, populating all fields.
    fn fetch(&mut self) -> impl std::future::Future<Output = Result<(), AirtableError>> + Send {
        async {
            let client = self
                .meta()
                .client
                .as_ref()
                .expect("No client attached.")
                .clone();
            let table_id = self.meta().table_id.expect("No table_id attached.");
            let id = self
                .get_id()
                .as_ref()
                .expect("Cannot fetch without an ID.")
                .clone();
            let record = client.get_record(table_id, &id, true).await?;
            self.apply_record(record)
        }
    }

    /// Delete the record from the API.
    fn delete(&self) -> impl std::future::Future<Output = Result<(), AirtableError>> + Send {
        async {
            let client = self
                .meta()
                .client
                .as_ref()
                .expect("No client attached.")
                .clone();
            let table_id = self.meta().table_id.expect("No table_id attached.");
            let id = self
                .get_id()
                .as_ref()
                .expect("Cannot delete without an ID.");
            client.delete_record(table_id, id).await
        }
    }
}
