use std::fmt;

/// Errors that can occur when interacting with the Airtable API.
#[derive(Debug)]
pub enum AirtableError {
    /// HTTP/network error.
    Http(reqwest::Error),
    /// Airtable API returned an error response.
    Api { status: u16, body: String },
    /// JSON serialization/deserialization error.
    Json(serde_json::Error),
}

impl fmt::Display for AirtableError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(e) => write!(f, "HTTP error: {e}"),
            Self::Api { status, body } => write!(f, "Airtable API error ({status}): {body}"),
            Self::Json(e) => write!(f, "JSON error: {e}"),
        }
    }
}

impl std::error::Error for AirtableError {}

impl From<reqwest::Error> for AirtableError {
    fn from(e: reqwest::Error) -> Self {
        Self::Http(e)
    }
}

impl From<serde_json::Error> for AirtableError {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e)
    }
}
