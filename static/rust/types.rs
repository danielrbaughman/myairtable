use serde::{Deserialize, Serialize};

/// A record ID string (e.g., "recXXXXXXXXXXXXXX").
pub type RecordId = String;

/// An Airtable record wrapper.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Record<T> {
    pub id: RecordId,
    pub fields: T,
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
