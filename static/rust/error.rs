use std::fmt;

/// Errors that can occur when interacting with the Airtable API.
#[derive(Debug)]
pub enum AirtableError {
    /// HTTP/network error.
    Http(reqwest::Error),
    /// Airtable API returned an error response. `code` is the Airtable error code parsed from
    /// the response envelope (e.g. `NOT_FOUND`, `INVALID_VALUE_FOR_COLUMN`), or empty if absent.
    Api {
        status: u16,
        code: String,
        body: String,
    },
    /// HTTP 429 rate limit. `retry_after` is the Retry-After value in seconds when known.
    RateLimited { retry_after: Option<f64> },
    /// JSON serialization/deserialization error.
    Json(serde_json::Error),
}

impl AirtableError {
    /// Classify a non-success HTTP response into a typed error: 429 becomes
    /// [`AirtableError::RateLimited`]; everything else becomes [`AirtableError::Api`] with the
    /// Airtable error code parsed out of the envelope.
    pub fn from_response(status: u16, body: String) -> Self {
        if status == 429 {
            return Self::RateLimited { retry_after: None };
        }
        let code = parse_api_error_code(&body);
        Self::Api { status, code, body }
    }

    /// Build a [`AirtableError::RateLimited`] carrying the parsed `Retry-After` (seconds). Used when
    /// retries are exhausted on a 429 so the caller can see how long the server asked us to wait.
    pub fn rate_limited(retry_after: Option<f64>) -> Self {
        Self::RateLimited { retry_after }
    }
}

/// Extract the Airtable error code from either envelope shape: the legacy bare-string
/// `{"error": "NOT_FOUND"}` or the structured `{"error": {"type": ..., "message": ...}}`.
fn parse_api_error_code(body: &str) -> String {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| {
            let err = v.get("error")?;
            match err.as_str() {
                Some(s) => Some(s.to_string()),
                None => err.get("type").and_then(|t| t.as_str()).map(str::to_string),
            }
        })
        .unwrap_or_default()
}

impl fmt::Display for AirtableError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(e) => write!(f, "HTTP error: {e}"),
            Self::Api { status, code, body } => {
                write!(f, "Airtable API error ({status} {code}): {body}")
            }
            Self::RateLimited { retry_after } => match retry_after {
                Some(s) => write!(f, "Airtable rate limited (retry after {s}s)"),
                None => write!(f, "Airtable rate limited"),
            },
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
