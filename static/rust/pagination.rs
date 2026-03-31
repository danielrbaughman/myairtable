use serde::Deserialize;

use crate::types::Record;

/// A paginated response from the Airtable API.
#[derive(Debug, Deserialize)]
pub struct PaginatedResponse<T> {
    pub records: Vec<Record<T>>,
    pub offset: Option<String>,
}
