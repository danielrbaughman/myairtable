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

/// Sort direction for list queries.
#[derive(Debug, Clone, Serialize)]
pub enum SortDirection {
    Asc,
    Desc,
}

/// Parameters for listing records.
#[derive(Debug, Clone, Serialize)]
pub struct AirtableQuery {
    pub use_field_ids: bool,
    pub formula: Option<String>,
    pub view: Option<String>,
    pub fields: Option<Vec<String>>,
    pub max_records: Option<usize>,
    pub page_size: Option<usize>,
    pub sort: Option<Vec<(String, SortDirection)>>,
    pub offset: Option<String>,
}

impl Default for AirtableQuery {
    fn default() -> Self {
        Self {
            use_field_ids: true,
            formula: None,
            view: None,
            fields: None,
            max_records: None,
            page_size: None,
            sort: None,
            offset: None,
        }
    }
}

impl AirtableQuery {
    pub fn new() -> Self {
        Self::default()
    }

    /// Return fields by field ID instead of name.
    pub fn use_field_ids(mut self, use_field_ids: bool) -> Self {
        self.use_field_ids = use_field_ids;
        self
    }

    /// Filter records by a formula.
    pub fn formula(mut self, formula: impl Into<String>) -> Self {
        self.formula = Some(formula.into());
        self
    }

    /// Filter records by a view.
    pub fn view(mut self, view: impl Into<String>) -> Self {
        self.view = Some(view.into());
        self
    }

    /// Specify which fields to return.
    pub fn fields(mut self, fields: Vec<String>) -> Self {
        self.fields = Some(fields);
        self
    }

    /// Limit the total number of records returned.
    pub fn max_records(mut self, n: usize) -> Self {
        self.max_records = Some(n);
        self
    }

    /// Set the page size for the query.
    pub fn page_size(mut self, n: usize) -> Self {
        self.page_size = Some(n);
        self
    }

    /// Add a sort field and direction.
    pub fn sort(mut self, field: impl Into<String>, direction: SortDirection) -> Self {
        self.sort
            .get_or_insert_with(Vec::new)
            .push((field.into(), direction));
        self
    }

    /// Set the offset for the query.
    pub fn offset(mut self, offset: impl Into<String>) -> Self {
        self.offset = Some(offset.into());
        self
    }

    /// Build query string parameters (excluding returnFieldsByFieldId).
    pub(crate) fn to_query_params(&self) -> Vec<(String, String)> {
        let mut params = Vec::new();

        if let Some(formula) = &self.formula {
            params.push(("filterByFormula".to_string(), formula.clone()));
        }
        if let Some(view) = &self.view {
            params.push(("view".to_string(), view.clone()));
        }
        if let Some(max) = self.max_records {
            params.push(("maxRecords".to_string(), max.to_string()));
        }
        if let Some(size) = self.page_size {
            params.push(("pageSize".to_string(), size.to_string()));
        }
        if let Some(offset) = &self.offset {
            params.push(("offset".to_string(), offset.clone()));
        }
        if let Some(fields) = &self.fields {
            for field in fields {
                params.push(("fields[]".to_string(), field.clone()));
            }
        }
        if let Some(sorts) = &self.sort {
            for (i, (field, dir)) in sorts.iter().enumerate() {
                params.push((format!("sort[{i}][field]"), field.clone()));
                params.push((
                    format!("sort[{i}][direction]"),
                    match dir {
                        SortDirection::Asc => "asc".to_string(),
                        SortDirection::Desc => "desc".to_string(),
                    },
                ));
            }
        }

        params
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

/// Build an Airtable web UI URL.
pub fn build_url(base_id: &str, table_id: &str, view_id: &str, record_id: &str) -> String {
    let mut url = "https://airtable.com".to_string();
    if base_id.is_empty() {
        return url;
    }
    url.push('/');
    url.push_str(base_id);
    if table_id.is_empty() {
        return url;
    }
    url.push('/');
    url.push_str(table_id);
    if !view_id.is_empty() {
        url.push('/');
        url.push_str(view_id);
    }
    if !record_id.is_empty() {
        url.push('/');
        url.push_str(record_id);
    }
    url
}

/// An Airtable attachment object.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Attachment {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    pub url: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub filename: Option<String>,
    #[serde(rename = "type")]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub size: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
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
