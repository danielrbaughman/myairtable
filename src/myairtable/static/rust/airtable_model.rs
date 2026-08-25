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

    /// The full writable field payload for this model, independent of dirty state.
    ///
    /// `to_save_json()` deliberately returns a *diff* once a snapshot exists, so a model that
    /// was read back from Airtable and not modified serializes to `{}`. Copying a record needs
    /// the opposite: every writable field, exactly as `to_json()` produces it (`id`,
    /// `created_time` and `_meta` are `#[serde(skip)]`, computed fields are
    /// `#[serde(skip_serializing)]`), with attachments reduced to the shape create accepts.
    fn to_insert_json(&self) -> serde_json::Value {
        let mut fields = self.to_json();
        project_attachments_for_create(&mut fields);
        fields
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

/// Reduce attachment cells to the only shape Airtable accepts when inserting.
///
/// Airtable returns attachments carrying read-only metadata (`id`, `size`, `type`, `width`,
/// `height`). On **create** it accepts only `{"url": ...}` (optionally with `"filename"`) —
/// sending an `id`, alone or echoed alongside `url`, fails with `INVALID_ATTACHMENT_OBJECT`.
/// Airtable re-ingests the file and mints a fresh attachment id, which is what makes a
/// duplicated record's attachment independent of its source rather than an alias.
///
/// Create-only: on **update** an `id` is legal and means "retain this attachment".
///
/// Attachment cells are recognised by shape rather than by field id, so this needs no
/// generated metadata: no other Airtable cell type is an array of objects carrying a `url`
/// alongside an `att`-prefixed id.
pub(crate) fn project_attachments_for_create(fields: &mut serde_json::Value) {
    let serde_json::Value::Object(map) = fields else {
        return;
    };
    for (_key, value) in map.iter_mut() {
        let serde_json::Value::Array(items) = value else {
            continue;
        };
        let is_attachment_cell = !items.is_empty()
            && items.iter().all(|item| {
                item.get("url").is_some_and(|u| u.is_string())
                    && item
                        .get("id")
                        .and_then(|i| i.as_str())
                        .is_some_and(|i| i.starts_with("att"))
            });
        if !is_attachment_cell {
            continue;
        }
        for item in items.iter_mut() {
            let url = item.get("url").cloned().unwrap_or(serde_json::Value::Null);
            let filename = item.get("filename").cloned();
            let mut projected = serde_json::Map::new();
            projected.insert("url".to_string(), url);
            if let Some(filename) = filename {
                if !filename.is_null() {
                    projected.insert("filename".to_string(), filename);
                }
            }
            *item = serde_json::Value::Object(projected);
        }
    }
}

#[cfg(test)]
mod project_attachments_tests {
    use super::project_attachments_for_create;
    use serde_json::json;

    #[test]
    fn strips_readonly_metadata_that_create_rejects() {
        // Verified against the live API: create accepts only {url} / {url, filename}. An `id` --
        // alone or echoed alongside `url` -- fails with INVALID_ATTACHMENT_OBJECT.
        let mut fields = json!({
            "fldAtt": [{
                "id": "attServerSide0001",
                "url": "https://example.com/a.png",
                "filename": "a.png",
                "size": 1234,
                "type": "image/png",
                "width": 10,
                "height": 10,
            }]
        });
        project_attachments_for_create(&mut fields);
        assert_eq!(
            fields,
            json!({"fldAtt": [{"url": "https://example.com/a.png", "filename": "a.png"}]})
        );
    }

    #[test]
    fn passes_through_caller_built_attachments() {
        let mut fields = json!({"fldAtt": [{"url": "u"}]});
        project_attachments_for_create(&mut fields);
        assert_eq!(fields, json!({"fldAtt": [{"url": "u"}]}));
    }

    #[test]
    fn leaves_other_cell_types_alone() {
        // Linked records, collaborators and plain arrays must not be mistaken for attachments.
        let mut fields = json!({
            "fldLink": ["rec1", "rec2"],
            "fldUser": {"id": "usrX", "email": "e@x.com"},
            "fldUsers": [{"id": "usrX", "email": "e@x.com"}],
            "fldEmpty": [],
            "fldText": "https://example.com",
        });
        let before = fields.clone();
        project_attachments_for_create(&mut fields);
        assert_eq!(fields, before);
    }
}
