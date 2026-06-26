use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Client;
use serde::Serialize;

use crate::error::AirtableError;
use crate::pagination::PaginatedResponse;
use crate::types::{AirtableQuery, Record, RecordId};

/// Max retry attempts (after the initial request) for transient failures: 429, 5xx, and
/// connect/timeout transport errors.
const RETRY_MAX_ATTEMPTS: u32 = 5;
/// Base for exponential backoff, in seconds.
const RETRY_BASE_SECS: f64 = 1.0;
/// Cap on a single backoff delay, in seconds.
const RETRY_MAX_DELAY_SECS: f64 = 30.0;

/// Parse a numeric `Retry-After` header (delta-seconds) into seconds.
fn parse_retry_after(headers: &reqwest::header::HeaderMap) -> Option<f64> {
    headers
        .get(reqwest::header::RETRY_AFTER)?
        .to_str()
        .ok()?
        .trim()
        .parse::<f64>()
        .ok()
}

/// A cheap, dependency-free jitter fraction in [0, 1) derived from the wall clock.
fn jitter_fraction() -> f64 {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    f64::from(nanos % 1000) / 1000.0
}

/// Airtable API client.
#[derive(Debug)]
pub struct AirtableClient {
    client: Client,
    base_id: String,
    headers: HeaderMap,
}

impl AirtableClient {
    /// Create a new Airtable client.
    pub fn new(api_key: &str, base_id: &str) -> Self {
        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("Bearer {api_key}")).expect("Invalid API key"),
        );
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));

        Self {
            client: Client::new(),
            base_id: base_id.to_string(),
            headers,
        }
    }

    /// The base ID this client is configured for.
    pub fn base_id(&self) -> &str {
        &self.base_id
    }

    fn table_url(&self, table_id: &str) -> String {
        format!("https://api.airtable.com/v0/{}/{}", self.base_id, table_id)
    }

    /// Backoff delay (seconds) before the next retry. A 429 `Retry-After` (seconds) is honored as
    /// the delay; otherwise exponential `base * 2^attempt` capped at the max. Decorrelated jitter of
    /// `jitter * delay/4` (with `jitter` in [0, 1)) is added so concurrent clients don't stampede.
    /// Pure + deterministic given `jitter`, so it can be unit-tested.
    pub fn retry_delay_secs(retry_after: Option<f64>, attempt: u32, jitter: f64) -> f64 {
        let delay = match retry_after {
            Some(s) if s >= 0.0 => s,
            _ => (RETRY_BASE_SECS * 2f64.powi(attempt as i32)).min(RETRY_MAX_DELAY_SECS),
        };
        delay + jitter * (delay / 4.0)
    }

    /// Send a request, retrying transient failures (429 / 5xx, and connect/timeout transport errors)
    /// up to [`RETRY_MAX_ATTEMPTS`] times with jittered exponential backoff (honoring a 429
    /// `Retry-After`). The builder is cloned per attempt; a non-cloneable (streamed) body is sent
    /// once without retry.
    async fn send_with_retry(
        &self,
        builder: reqwest::RequestBuilder,
    ) -> Result<reqwest::Response, AirtableError> {
        let mut attempt: u32 = 0;
        loop {
            let Some(attempt_builder) = builder.try_clone() else {
                return Ok(builder.send().await?);
            };
            match attempt_builder.send().await {
                Ok(resp) => {
                    let status = resp.status().as_u16();
                    let retryable = status == 429 || (500..600).contains(&status);
                    if retryable && attempt < RETRY_MAX_ATTEMPTS {
                        let delay = Self::retry_delay_secs(
                            parse_retry_after(resp.headers()),
                            attempt,
                            jitter_fraction(),
                        );
                        tokio::time::sleep(std::time::Duration::from_secs_f64(delay)).await;
                        attempt += 1;
                        continue;
                    }
                    return Ok(resp);
                }
                Err(e) if attempt < RETRY_MAX_ATTEMPTS && (e.is_timeout() || e.is_connect()) => {
                    let delay = Self::retry_delay_secs(None, attempt, jitter_fraction());
                    tokio::time::sleep(std::time::Duration::from_secs_f64(delay)).await;
                    attempt += 1;
                }
                Err(e) => return Err(AirtableError::from(e)),
            }
        }
    }

    /// Fetch the base schema from Airtable's metadata API.
    pub async fn get_schema(&self) -> Result<serde_json::Value, AirtableError> {
        let url = format!(
            "https://api.airtable.com/v0/meta/bases/{}/tables",
            self.base_id
        );
        let resp = self
            .send_with_retry(self.client.get(&url).headers(self.headers.clone()))
            .await?;
        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(AirtableError::from_response(status, body));
        }
        Ok(resp.json().await?)
    }

    /// List records from a table.
    pub async fn list_records(
        &self,
        table_id: &str,
        params: &AirtableQuery,
    ) -> Result<PaginatedResponse, AirtableError> {
        let mut query_params = params.to_query_params();
        if params.use_field_ids {
            query_params.push(("returnFieldsByFieldId".to_string(), "true".to_string()));
        }

        let url = self.table_url(table_id);
        let response = self
            .send_with_retry(
                self.client
                    .get(&url)
                    .query(&query_params)
                    .headers(self.headers.clone()),
            )
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::from_response(status, body));
        }

        Ok(response.json().await?)
    }

    /// Get a single record by ID.
    pub async fn get_record(
        &self,
        table_id: &str,
        record_id: &RecordId,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        let url = if use_field_ids {
            format!(
                "{}/{}?returnFieldsByFieldId=true",
                self.table_url(table_id),
                record_id
            )
        } else {
            format!("{}/{}", self.table_url(table_id), record_id)
        };

        let response = self
            .send_with_retry(self.client.get(&url).headers(self.headers.clone()))
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::from_response(status, body));
        }

        Ok(response.json().await?)
    }

    /// Create a record.
    pub async fn create_record<U: Serialize>(
        &self,
        table_id: &str,
        fields: &U,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        let url = self.table_url(table_id);
        let mut body = serde_json::json!({ "fields": fields });
        if use_field_ids {
            body["returnFieldsByFieldId"] = serde_json::json!(true);
        }

        let response = self
            .send_with_retry(
                self.client
                    .post(&url)
                    .headers(self.headers.clone())
                    .json(&body),
            )
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::from_response(status, body));
        }

        Ok(response.json().await?)
    }

    /// Update a record.
    pub async fn update_record<U: Serialize>(
        &self,
        table_id: &str,
        record_id: &RecordId,
        fields: &U,
        use_field_ids: bool,
    ) -> Result<Record, AirtableError> {
        let url = format!("{}/{}", self.table_url(table_id), record_id);
        let mut body = serde_json::json!({ "fields": fields });
        if use_field_ids {
            body["returnFieldsByFieldId"] = serde_json::json!(true);
        }

        let response = self
            .send_with_retry(
                self.client
                    .patch(&url)
                    .headers(self.headers.clone())
                    .json(&body),
            )
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::from_response(status, body));
        }

        Ok(response.json().await?)
    }

    /// Delete a record.
    pub async fn delete_record(
        &self,
        table_id: &str,
        record_id: &RecordId,
    ) -> Result<(), AirtableError> {
        let url = format!("{}/{}", self.table_url(table_id), record_id);

        let response = self
            .send_with_retry(self.client.delete(&url).headers(self.headers.clone()))
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::from_response(status, body));
        }

        Ok(())
    }

    /// Create multiple records in batches of 10 (Airtable API limit).
    pub async fn create_records<U: Serialize>(
        &self,
        table_id: &str,
        records: &[U],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        let url = self.table_url(table_id);
        let mut results = Vec::with_capacity(records.len());

        for chunk in records.chunks(10) {
            let recs: Vec<_> = chunk
                .iter()
                .map(|f| serde_json::json!({"fields": f}))
                .collect();
            let mut body = serde_json::json!({ "records": recs });
            if use_field_ids {
                body["returnFieldsByFieldId"] = serde_json::json!(true);
            }

            let response = self
                .send_with_retry(
                    self.client
                        .post(&url)
                        .headers(self.headers.clone())
                        .json(&body),
                )
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::from_response(status, body));
            }

            let batch: serde_json::Value = response.json().await?;
            if let Some(recs) = batch["records"].as_array() {
                for rec in recs {
                    results.push(serde_json::from_value(rec.clone())?);
                }
            }
        }

        Ok(results)
    }

    /// Update multiple records in batches of 10 (Airtable API limit).
    pub async fn update_records<U: Serialize>(
        &self,
        table_id: &str,
        records: &[(&RecordId, &U)],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        let url = self.table_url(table_id);
        let mut results = Vec::with_capacity(records.len());

        for chunk in records.chunks(10) {
            let recs: Vec<_> = chunk
                .iter()
                .map(|(id, fields)| {
                    serde_json::json!({
                        "id": id,
                        "fields": fields,
                    })
                })
                .collect();
            let mut body = serde_json::json!({ "records": recs });
            if use_field_ids {
                body["returnFieldsByFieldId"] = serde_json::json!(true);
            }

            let response = self
                .send_with_retry(
                    self.client
                        .patch(&url)
                        .headers(self.headers.clone())
                        .json(&body),
                )
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::from_response(status, body));
            }

            let batch: serde_json::Value = response.json().await?;
            if let Some(recs) = batch["records"].as_array() {
                for rec in recs {
                    results.push(serde_json::from_value(rec.clone())?);
                }
            }
        }

        Ok(results)
    }

    /// Upsert records via Airtable's `performUpsert` (match each record against existing ones by
    /// `fields_to_merge_on`), in batches of 10. Records with an `id` are matched by id; the rest by
    /// the merge fields (exactly-one match updates, no match inserts, more than one match errors).
    pub async fn upsert_records<U: Serialize>(
        &self,
        table_id: &str,
        records: &[(Option<&RecordId>, &U)],
        fields_to_merge_on: &[&str],
        use_field_ids: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        let url = self.table_url(table_id);
        let mut results = Vec::with_capacity(records.len());

        for chunk in records.chunks(10) {
            let recs: Vec<_> = chunk
                .iter()
                .map(|(id, fields)| {
                    let mut rec = serde_json::json!({ "fields": fields });
                    if let Some(id) = id {
                        rec["id"] = serde_json::json!(id);
                    }
                    rec
                })
                .collect();
            let mut body = serde_json::json!({
                "records": recs,
                "performUpsert": { "fieldsToMergeOn": fields_to_merge_on },
            });
            if use_field_ids {
                body["returnFieldsByFieldId"] = serde_json::json!(true);
            }

            let response = self
                .send_with_retry(
                    self.client
                        .patch(&url)
                        .headers(self.headers.clone())
                        .json(&body),
                )
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::from_response(status, body));
            }

            let batch: serde_json::Value = response.json().await?;
            if let Some(recs) = batch["records"].as_array() {
                for rec in recs {
                    results.push(serde_json::from_value(rec.clone())?);
                }
            }
        }

        Ok(results)
    }

    /// Delete multiple records in batches of 10 (Airtable API limit).
    pub async fn delete_records(
        &self,
        table_id: &str,
        record_ids: &[RecordId],
    ) -> Result<(), AirtableError> {
        for chunk in record_ids.chunks(10) {
            let params: Vec<String> = chunk.iter().map(|id| format!("records[]={id}")).collect();
            let url = format!("{}?{}", self.table_url(table_id), params.join("&"));

            let response = self
                .send_with_retry(self.client.delete(&url).headers(self.headers.clone()))
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::from_response(status, body));
            }
        }

        Ok(())
    }
}
