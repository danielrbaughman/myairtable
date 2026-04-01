use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// A record ID string (e.g., "recXXXXXXXXXXXXXX").
pub type RecordId = String;

/// A map of field keys to JSON values.
///
/// Keys are either field IDs (e.g. "fldXXX") or field names (e.g. "Primary Key"),
/// depending on the client's `use_field_ids` setting.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Fields(pub HashMap<String, serde_json::Value>);

impl Fields {
    /// Create an empty Fields map.
    pub fn new() -> Self {
        Self(HashMap::new())
    }

    /// Get a field value by key (field ID or field name).
    pub fn get(&self, key: &str) -> Option<&serde_json::Value> {
        self.0.get(key)
    }

    /// Set a field value by key.
    pub fn set(&mut self, key: &str, value: impl Into<serde_json::Value>) {
        self.0.insert(key.to_string(), value.into());
    }

    /// Check if a field key is present.
    pub fn contains(&self, key: &str) -> bool {
        self.0.contains_key(key)
    }

    /// Get the number of fields.
    pub fn len(&self) -> usize {
        self.0.len()
    }

    /// Check if the map is empty.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

impl std::ops::Deref for Fields {
    type Target = HashMap<String, serde_json::Value>;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl std::ops::DerefMut for Fields {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

/// An Airtable record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Record {
    pub id: RecordId,
    pub fields: Fields,
    #[serde(rename = "createdTime")]
    pub created_time: Option<String>,
}

/// An Airtable attachment object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Attachment {
    pub id: String,
    pub url: String,
    pub filename: String,
    #[serde(rename = "type")]
    pub mime_type: Option<String>,
    pub size: Option<u64>,
    pub width: Option<u32>,
    pub height: Option<u32>,
}

/// An Airtable collaborator object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Collaborator {
    pub id: String,
    pub email: String,
    pub name: Option<String>,
}

/// An Airtable button object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AirtableButton {
    pub label: String,
    pub url: Option<String>,
}

/// Represents a value that can be either a single item or a list.
/// Used for lookup/rollup fields where the shape is ambiguous.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum VecOrValue<T> {
    Single(T),
    Multiple(Vec<T>),
}
