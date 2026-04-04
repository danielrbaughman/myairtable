use serde::Deserialize;

use crate::types::Record;

/// A paginated response from the Airtable API.
#[derive(Debug, Deserialize)]
pub struct PaginatedResponse {
    pub records: Vec<Record>,
    pub offset: Option<String>,
}
