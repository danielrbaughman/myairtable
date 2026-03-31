use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Client;
use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::error::AirtableError;
use crate::pagination::PaginatedResponse;
use crate::types::RecordId;

/// Airtable API client.
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

    fn table_url(&self, table_id: &str) -> String {
        format!("https://api.airtable.com/v0/{}/{}", self.base_id, table_id)
    }

    /// List records from a table.
    pub async fn list_records<T: DeserializeOwned>(
        &self,
        table_id: &str,
        offset: Option<&str>,
    ) -> Result<PaginatedResponse<T>, AirtableError> {
        let mut url = format!("{}?returnFieldsByFieldId=true", self.table_url(table_id));
        if let Some(offset) = offset {
            url = format!("{url}&offset={offset}");
        }

        let response = self
            .client
            .get(&url)
            .headers(self.headers.clone())
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::Api { status, body });
        }

        Ok(response.json().await?)
    }

    /// Get a single record by ID.
    pub async fn get_record<T: DeserializeOwned>(
        &self,
        table_id: &str,
        record_id: &RecordId,
    ) -> Result<crate::types::Record<T>, AirtableError> {
        let url = format!(
            "{}/{}?returnFieldsByFieldId=true",
            self.table_url(table_id),
            record_id
        );

        let response = self
            .client
            .get(&url)
            .headers(self.headers.clone())
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::Api { status, body });
        }

        Ok(response.json().await?)
    }

    /// Create a record.
    pub async fn create_record<T: DeserializeOwned, U: Serialize>(
        &self,
        table_id: &str,
        fields: &U,
    ) -> Result<crate::types::Record<T>, AirtableError> {
        let url = self.table_url(table_id);
        let body = serde_json::json!({ "fields": fields, "returnFieldsByFieldId": true });

        let response = self
            .client
            .post(&url)
            .headers(self.headers.clone())
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::Api { status, body });
        }

        Ok(response.json().await?)
    }

    /// Update a record.
    pub async fn update_record<T: DeserializeOwned, U: Serialize>(
        &self,
        table_id: &str,
        record_id: &RecordId,
        fields: &U,
    ) -> Result<crate::types::Record<T>, AirtableError> {
        let url = format!("{}/{}", self.table_url(table_id), record_id);
        let body = serde_json::json!({ "fields": fields, "returnFieldsByFieldId": true });

        let response = self
            .client
            .patch(&url)
            .headers(self.headers.clone())
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::Api { status, body });
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
            .client
            .delete(&url)
            .headers(self.headers.clone())
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            return Err(AirtableError::Api { status, body });
        }

        Ok(())
    }

    /// Create multiple records in batches of 10 (Airtable API limit).
    pub async fn create_records<T: DeserializeOwned, U: Serialize>(
        &self,
        table_id: &str,
        records: &[U],
    ) -> Result<Vec<crate::types::Record<T>>, AirtableError> {
        let url = self.table_url(table_id);
        let mut results = Vec::with_capacity(records.len());

        for chunk in records.chunks(10) {
            let body = serde_json::json!({
                "records": chunk.iter().map(|f| serde_json::json!({"fields": f})).collect::<Vec<_>>(),
                "returnFieldsByFieldId": true,
            });

            let response = self
                .client
                .post(&url)
                .headers(self.headers.clone())
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::Api { status, body });
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
    pub async fn update_records<T: DeserializeOwned, U: Serialize>(
        &self,
        table_id: &str,
        records: &[(&RecordId, &U)],
    ) -> Result<Vec<crate::types::Record<T>>, AirtableError> {
        let url = self.table_url(table_id);
        let mut results = Vec::with_capacity(records.len());

        for chunk in records.chunks(10) {
            let body = serde_json::json!({
                "records": chunk.iter().map(|(id, fields)| serde_json::json!({
                    "id": id,
                    "fields": fields,
                })).collect::<Vec<_>>(),
                "returnFieldsByFieldId": true,
            });

            let response = self
                .client
                .patch(&url)
                .headers(self.headers.clone())
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::Api { status, body });
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
                .client
                .delete(&url)
                .headers(self.headers.clone())
                .send()
                .await?;

            if !response.status().is_success() {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                return Err(AirtableError::Api { status, body });
            }
        }

        Ok(())
    }
}
