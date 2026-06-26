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

/// Parse a `Retry-After` header (RFC 9110) into seconds, accepting BOTH forms: delta-seconds
/// (`"120"` / `"1.5"`) and an HTTP-date (`"Wed, 21 Oct 2015 07:28:00 GMT"`). For the date form the
/// result is `max(0, date - now)`. A garbage or negative value floors to 0 so it can never reach the
/// sleep call as a negative.
fn parse_retry_after(headers: &reqwest::header::HeaderMap) -> Option<f64> {
    let raw = headers
        .get(reqwest::header::RETRY_AFTER)?
        .to_str()
        .ok()?
        .trim();
    if let Ok(secs) = raw.parse::<f64>() {
        return Some(secs.max(0.0));
    }
    // HTTP-date form (RFC 9110 IMF-fixdate, e.g. "Wed, 21 Oct 2015 07:28:00 GMT" -> RFC 2822):
    // compute remaining seconds until the given instant, flooring past dates to 0.
    let target = chrono::DateTime::parse_from_rfc2822(raw).ok()?;
    let secs =
        (target.timestamp_millis() as f64 - chrono::Utc::now().timestamp_millis() as f64) / 1000.0;
    Some(secs.max(0.0))
}

/// A cheap, dependency-free jitter fraction in [0, 1) derived from the wall clock. NOTE: nanosecond
/// wall-clock entropy is weak under correlated clocks (e.g. many hosts booted from the same image and
/// NTP-synced can land on near-identical nanos), so this does not fully prevent a thundering herd; a
/// real PRNG would be stronger but is avoided here to stay dependency-free.
fn jitter_fraction() -> f64 {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    // Use the full sub-second nanos range (0..1_000_000_000) for wider entropy.
    f64::from(nanos) / 1_000_000_000.0
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

    /// Apply the optional write flags to a request `body`, mutating it in place: set
    /// `returnFieldsByFieldId` when `use_field_ids`, and set `typecast` ONLY when `typecast` is true
    /// (omitted otherwise, so default behavior is unchanged and matches the other language clients).
    /// Pure given its inputs, so the typecast/field-id body shaping can be unit-tested without a server.
    pub fn apply_write_options(body: &mut serde_json::Value, use_field_ids: bool, typecast: bool) {
        if use_field_ids {
            body["returnFieldsByFieldId"] = serde_json::json!(true);
        }
        if typecast {
            body["typecast"] = serde_json::json!(true);
        }
    }

    /// Backoff delay (seconds) before the next retry, with `jitter` in [0, 1). Two paths:
    ///
    /// - Server `Retry-After` present: honor it, but CAP at [`RETRY_MAX_DELAY_SECS`] (a broken
    ///   `Retry-After: 999999` must never hang the call), then add a small bounded jitter
    ///   (`jitter * delay/4`) so clients released by the same window don't stampede.
    /// - Otherwise: FULL jitter on exponential backoff — `jitter * min(cap, base * 2^attempt)` —
    ///   which spreads retries uniformly across the backoff window.
    ///
    /// Pure + deterministic given `jitter`, so it can be unit-tested.
    pub fn retry_delay_secs(retry_after: Option<f64>, attempt: u32, jitter: f64) -> f64 {
        match retry_after {
            Some(s) if s >= 0.0 => {
                let capped = s.min(RETRY_MAX_DELAY_SECS);
                capped + jitter * (capped / 4.0)
            }
            _ => {
                let cap = (RETRY_BASE_SECS * 2f64.powi(attempt as i32)).min(RETRY_MAX_DELAY_SECS);
                jitter * cap
            }
        }
    }

    /// The retry DECISION for an HTTP status: should the loop retry an attempt that produced `status`,
    /// given whether the request is `idempotent` and how many retries have already happened (`attempt`)?
    ///
    /// - HTTP 429: ALWAYS retry (the request was rejected, nothing was applied).
    /// - HTTP 5xx: retry ONLY IF `idempotent` (a non-idempotent op may have been partially applied).
    /// - Any other status (2xx/3xx/4xx): never retry.
    ///
    /// In all cases retrying stops once `attempt` reaches [`RETRY_MAX_ATTEMPTS`]. Pure + deterministic,
    /// so it can be unit-tested exhaustively. (Transport errors use the same idempotency rule inline in
    /// [`Self::send_with_retry`], gated on `e.is_timeout() || e.is_connect()`.)
    pub fn should_retry(status: u16, idempotent: bool, attempt: u32) -> bool {
        let is_429 = status == 429;
        let is_5xx = (500..600).contains(&status);
        (is_429 || (is_5xx && idempotent)) && attempt < RETRY_MAX_ATTEMPTS
    }

    /// Send a request, retrying transient failures with jittered, capped exponential backoff (honoring
    /// a 429 `Retry-After`), up to [`RETRY_MAX_ATTEMPTS`] times. The retry policy depends on whether the
    /// caller classified the request as `idempotent`:
    ///
    /// - HTTP 429: ALWAYS retry (the request was rejected, nothing was applied).
    /// - HTTP 5xx: retry ONLY IF `idempotent` (a non-idempotent op may have been partially applied).
    /// - transport/IO error: retry ONLY IF `idempotent`. We deliberately do NOT distinguish
    ///   connect-before-send from a read-timeout — that is not portably available, and the conservative
    ///   uniform rule (retry only when idempotent) is correct.
    ///
    /// When retries are exhausted on a 429, returns [`AirtableError::RateLimited`] carrying the parsed
    /// `Retry-After` rather than the raw response. The builder is cloned per attempt; a non-cloneable
    /// (streamed) body is sent once without retry.
    async fn send_with_retry(
        &self,
        builder: reqwest::RequestBuilder,
        idempotent: bool,
    ) -> Result<reqwest::Response, AirtableError> {
        let mut attempt: u32 = 0;
        loop {
            let Some(attempt_builder) = builder.try_clone() else {
                return Ok(builder.send().await?);
            };
            match attempt_builder.send().await {
                Ok(resp) => {
                    let status = resp.status().as_u16();
                    let is_429 = status == 429;
                    // 429 always retries; 5xx only when the request is idempotent; capped at MAX.
                    if Self::should_retry(status, idempotent, attempt) {
                        let delay = Self::retry_delay_secs(
                            parse_retry_after(resp.headers()),
                            attempt,
                            jitter_fraction(),
                        );
                        tokio::time::sleep(std::time::Duration::from_secs_f64(delay)).await;
                        attempt += 1;
                        continue;
                    }
                    // Retries exhausted on a 429: surface the typed rate-limit error with the
                    // server's (capped) Retry-After instead of the raw response.
                    if is_429 {
                        let retry_after =
                            parse_retry_after(resp.headers()).map(|s| s.min(RETRY_MAX_DELAY_SECS));
                        return Err(AirtableError::rate_limited(retry_after));
                    }
                    return Ok(resp);
                }
                // Transport errors retry only when idempotent.
                Err(e)
                    if attempt < RETRY_MAX_ATTEMPTS
                        && idempotent
                        && (e.is_timeout() || e.is_connect()) =>
                {
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
            .send_with_retry(self.client.get(&url).headers(self.headers.clone()), true)
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
                true,
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
            .send_with_retry(self.client.get(&url).headers(self.headers.clone()), true)
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
        typecast: bool,
    ) -> Result<Record, AirtableError> {
        let url = self.table_url(table_id);
        let mut body = serde_json::json!({ "fields": fields });
        Self::apply_write_options(&mut body, use_field_ids, typecast);

        let response = self
            .send_with_retry(
                self.client
                    .post(&url)
                    .headers(self.headers.clone())
                    .json(&body),
                false, // POST create is not idempotent.
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
        typecast: bool,
    ) -> Result<Record, AirtableError> {
        let url = format!("{}/{}", self.table_url(table_id), record_id);
        let mut body = serde_json::json!({ "fields": fields });
        Self::apply_write_options(&mut body, use_field_ids, typecast);

        let response = self
            .send_with_retry(
                self.client
                    .patch(&url)
                    .headers(self.headers.clone())
                    .json(&body),
                true, // update-by-id is idempotent.
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
            .send_with_retry(
                self.client.delete(&url).headers(self.headers.clone()),
                true, // delete-by-id is idempotent.
            )
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
        typecast: bool,
    ) -> Result<Vec<Record>, AirtableError> {
        let url = self.table_url(table_id);
        let mut results = Vec::with_capacity(records.len());

        for chunk in records.chunks(10) {
            let recs: Vec<_> = chunk
                .iter()
                .map(|f| serde_json::json!({"fields": f}))
                .collect();
            let mut body = serde_json::json!({ "records": recs });
            Self::apply_write_options(&mut body, use_field_ids, typecast);

            let response = self
                .send_with_retry(
                    self.client
                        .post(&url)
                        .headers(self.headers.clone())
                        .json(&body),
                    false, // batch POST create is not idempotent.
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
        typecast: bool,
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
            Self::apply_write_options(&mut body, use_field_ids, typecast);

            let response = self
                .send_with_retry(
                    self.client
                        .patch(&url)
                        .headers(self.headers.clone())
                        .json(&body),
                    true, // batch update-by-id is idempotent.
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
        typecast: bool,
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
            Self::apply_write_options(&mut body, use_field_ids, typecast);

            // Upsert is idempotent only when a merge key identifies records (a retried insert with
            // no merge key would create duplicates). With merge fields, a retried PATCH converges to
            // the same row.
            let idempotent = !fields_to_merge_on.is_empty();
            let response = self
                .send_with_retry(
                    self.client
                        .patch(&url)
                        .headers(self.headers.clone())
                        .json(&body),
                    idempotent,
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
                .send_with_retry(
                    self.client.delete(&url).headers(self.headers.clone()),
                    true, // batch delete-by-id is idempotent.
                )
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
