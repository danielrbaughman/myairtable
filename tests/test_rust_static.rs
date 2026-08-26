use myairtable_static::*;

#[test]
fn creates_client() {
    let _client = AirtableClient::new("test_key", "appTEST123");
}

#[test]
fn apply_write_options_adds_typecast_only_when_set() {
    // The create/update/upsert write methods all build their JSON body and then call
    // `apply_write_options`, which is where typecast reaches the request body. Assert that helper
    // directly so the body shaping is verified without standing up an HTTP server.

    // Default (typecast = false): the body MUST NOT carry "typecast" (no behavior change).
    let mut body = serde_json::json!({ "fields": { "Name": "x" } });
    AirtableClient::apply_write_options(&mut body, false, false);
    assert!(
        body.get("typecast").is_none(),
        "typecast must be absent by default, got: {body}"
    );
    assert!(
        body.get("returnFieldsByFieldId").is_none(),
        "returnFieldsByFieldId must be absent when use_field_ids=false"
    );

    // typecast = true: the body carries "typecast": true.
    let mut body = serde_json::json!({ "fields": { "Name": "x" } });
    AirtableClient::apply_write_options(&mut body, false, true);
    assert_eq!(
        body.get("typecast"),
        Some(&serde_json::json!(true)),
        "typecast must be true when opted in, got: {body}"
    );

    // The two flags are independent: use_field_ids on, typecast off.
    let mut body = serde_json::json!({ "records": [] });
    AirtableClient::apply_write_options(&mut body, true, false);
    assert_eq!(
        body.get("returnFieldsByFieldId"),
        Some(&serde_json::json!(true))
    );
    assert!(body.get("typecast").is_none());

    // Both on.
    let mut body = serde_json::json!({ "records": [] });
    AirtableClient::apply_write_options(&mut body, true, true);
    assert_eq!(
        body.get("returnFieldsByFieldId"),
        Some(&serde_json::json!(true))
    );
    assert_eq!(body.get("typecast"), Some(&serde_json::json!(true)));
}

#[test]
fn retry_delay_honors_retry_after_and_caps_backoff() {
    // Retry-After path: the (capped) value plus a small bounded jitter of up to value/4.
    // With jitter=0.0 the value is used directly.
    assert_eq!(AirtableClient::retry_delay_secs(Some(5.0), 0, 0.0), 5.0);
    // A huge/broken Retry-After is capped at the 30s max even with jitter=0.0.
    assert_eq!(
        AirtableClient::retry_delay_secs(Some(999999.0), 0, 0.0),
        30.0
    );
    // Retry-After jitter adds up to value/4 on top of the (capped) value.
    let d = AirtableClient::retry_delay_secs(Some(8.0), 0, 0.999);
    assert!(
        (8.0..=10.0).contains(&d),
        "jittered Retry-After {d} out of [8.0, 10.0]"
    );

    // No Retry-After: FULL jitter on exponential backoff -> jitter * min(cap, base * 2^attempt).
    // With jitter=0.0 the delay is 0 (full jitter spans [0, window)).
    assert_eq!(AirtableClient::retry_delay_secs(None, 0, 0.0), 0.0);
    assert_eq!(AirtableClient::retry_delay_secs(None, 2, 0.0), 0.0);
    // With jitter just under 1.0, the delay approaches the backoff window (base * 2^attempt).
    let d0 = AirtableClient::retry_delay_secs(None, 0, 0.999);
    assert!(
        (0.0..=1.0).contains(&d0),
        "attempt 0 jittered delay {d0} out of [0.0, 1.0]"
    );
    let d2 = AirtableClient::retry_delay_secs(None, 2, 0.999);
    assert!(
        (0.0..=4.0).contains(&d2),
        "attempt 2 jittered delay {d2} out of [0.0, 4.0]"
    );
    // The backoff window is capped at the 30s max (1 * 2^10 = 1024 -> 30).
    let dcap = AirtableClient::retry_delay_secs(None, 10, 0.999);
    assert!(
        (0.0..=30.0).contains(&dcap),
        "capped jittered delay {dcap} out of [0.0, 30.0]"
    );
}

#[test]
fn should_retry_429_regardless_of_idempotency() {
    // 429 means the request was rejected and nothing was applied, so it is always safe to retry
    // whether or not the operation is idempotent.
    assert!(AirtableClient::should_retry(429, true, 0));
    assert!(AirtableClient::should_retry(429, false, 0));
}

#[test]
fn should_retry_5xx_only_when_idempotent() {
    // A non-idempotent op (e.g. POST create) may have been partially applied on a 5xx, so it must
    // NOT be retried; an idempotent op is safe to retry.
    for status in [500u16, 502, 503, 599] {
        assert!(
            AirtableClient::should_retry(status, true, 0),
            "idempotent {status} should retry"
        );
        assert!(
            !AirtableClient::should_retry(status, false, 0),
            "non-idempotent {status} must not retry"
        );
    }
}

#[test]
fn should_retry_never_retries_success_or_4xx() {
    // 2xx/3xx and non-429 4xx are terminal regardless of idempotency.
    for status in [200u16, 201, 204, 301, 400, 401, 403, 404, 422] {
        assert!(
            !AirtableClient::should_retry(status, true, 0),
            "idempotent {status} must not retry"
        );
        assert!(
            !AirtableClient::should_retry(status, false, 0),
            "non-idempotent {status} must not retry"
        );
    }
    // 499 is below the 5xx range and must not retry even though 599 (in range) does.
    assert!(!AirtableClient::should_retry(499, true, 0));
}

#[test]
fn should_retry_respects_attempt_cap() {
    // RETRY_MAX_ATTEMPTS is 5: attempts 0..=4 may retry, attempt 5+ must stop, even for a 429.
    assert!(AirtableClient::should_retry(429, false, 4));
    assert!(!AirtableClient::should_retry(429, false, 5));
    assert!(!AirtableClient::should_retry(429, true, 5));
    // The cap also applies to retryable 5xx on idempotent requests.
    assert!(AirtableClient::should_retry(503, true, 4));
    assert!(!AirtableClient::should_retry(503, true, 5));
    assert!(!AirtableClient::should_retry(503, true, 100));
}

#[test]
fn vec_or_value_deserializes_single() {
    let json = r#""hello""#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    assert!(matches!(val, VecOrValue::Single(s) if s == "hello"));
}

#[test]
fn vec_or_value_deserializes_multiple() {
    let json = r#"["a", "b"]"#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 2);
    assert_eq!(v[0].as_deref(), Some("a"));
    assert_eq!(v[1].as_deref(), Some("b"));
}

#[test]
fn vec_or_value_deserializes_multiple_with_nulls() {
    let json = r#"[null, "a", null, "b"]"#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 4);
    assert!(v[0].is_none());
    assert_eq!(v[1].as_deref(), Some("a"));
    assert!(v[2].is_none());
    assert_eq!(v[3].as_deref(), Some("b"));
}

#[test]
fn vec_or_value_deserializes_all_nulls() {
    let json = r#"[null, null]"#;
    let val: VecOrValue<i64> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 2);
    assert!(v.iter().all(|x| x.is_none()));
}

#[test]
fn vec_or_value_deserializes_empty() {
    let json = r#"[]"#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    assert!(matches!(val, VecOrValue::Multiple(v) if v.is_empty()));
}

#[test]
fn vec_or_value_serializes_multiple_with_nulls() {
    let val: VecOrValue<String> =
        VecOrValue::Multiple(vec![Some("a".into()), None, Some("b".into())]);
    let json = serde_json::to_string(&val).unwrap();
    assert_eq!(json, r#"["a",null,"b"]"#);
}

// =============================================================================
// SpecialNumber / ErrorValue / MaybeSpecialOrError / MaybeError
// =============================================================================

#[test]
fn special_number_deserializes() {
    let v: SpecialNumber = serde_json::from_str(r#"{"specialValue":"NaN"}"#).unwrap();
    assert_eq!(v.special_value, "NaN");
    let v: SpecialNumber = serde_json::from_str(r#"{"specialValue":"Infinity"}"#).unwrap();
    assert_eq!(v.special_value, "Infinity");
}

#[test]
fn error_value_deserializes() {
    let v: ErrorValue = serde_json::from_str(r##"{"error":"#ERROR!"}"##).unwrap();
    assert_eq!(v.error, "#ERROR!");
}

#[test]
fn maybe_special_or_error_deserializes_value() {
    let v: MaybeSpecialOrError<f64> = serde_json::from_str("42").unwrap();
    assert!(matches!(v, MaybeSpecialOrError::Value(n) if n == 42.0));
}

#[test]
fn maybe_special_or_error_deserializes_special() {
    let v: MaybeSpecialOrError<f64> = serde_json::from_str(r#"{"specialValue":"NaN"}"#).unwrap();
    assert!(matches!(v, MaybeSpecialOrError::Special(s) if s.special_value == "NaN"));
}

#[test]
fn maybe_special_or_error_deserializes_error() {
    let v: MaybeSpecialOrError<f64> = serde_json::from_str(r##"{"error":"#ERROR!"}"##).unwrap();
    assert!(matches!(v, MaybeSpecialOrError::Error(e) if e.error == "#ERROR!"));
}

#[test]
fn maybe_error_deserializes_value() {
    let v: MaybeError<String> = serde_json::from_str(r#""hello""#).unwrap();
    assert!(matches!(v, MaybeError::Value(s) if s == "hello"));
}

#[test]
fn maybe_error_deserializes_error() {
    let v: MaybeError<String> = serde_json::from_str(r##"{"error":"#ERROR!"}"##).unwrap();
    assert!(matches!(v, MaybeError::Error(e) if e.error == "#ERROR!"));
}

#[test]
fn maybe_special_or_error_helpers() {
    let v: MaybeSpecialOrError<i64> = 42.into();
    assert!(v.is_value());
    assert_eq!(v.value(), Some(&42));
    assert_eq!(v.clone().into_value(), Some(42));
    assert!(!v.is_special());
    assert!(!v.is_error());

    let e: MaybeSpecialOrError<i64> = MaybeSpecialOrError::Error(ErrorValue {
        error: "#ERROR!".into(),
    });
    assert!(e.is_error());
    assert!(e.value().is_none());
    assert_eq!(e.error().map(|x| x.error.as_str()), Some("#ERROR!"));
}

#[test]
fn maybe_error_helpers() {
    let v: MaybeError<String> = "hi".to_string().into();
    assert!(v.is_value());
    assert_eq!(v.value().map(String::as_str), Some("hi"));
    assert!(!v.is_error());

    let e: MaybeError<String> = MaybeError::Error(ErrorValue {
        error: "#ERROR!".into(),
    });
    assert!(e.is_error());
    assert_eq!(e.error().map(|x| x.error.as_str()), Some("#ERROR!"));
}

#[test]
fn vec_or_value_of_maybe_special_or_error_mixed_array() {
    let json = r##"[1, {"specialValue":"NaN"}, {"error":"#ERROR!"}, null]"##;
    let val: VecOrValue<MaybeSpecialOrError<i64>> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 4);
    assert!(matches!(v[0], Some(MaybeSpecialOrError::Value(1))));
    assert!(matches!(&v[1], Some(MaybeSpecialOrError::Special(s)) if s.special_value == "NaN"));
    assert!(matches!(&v[2], Some(MaybeSpecialOrError::Error(e)) if e.error == "#ERROR!"));
    assert!(v[3].is_none());
}

// =============================================================================
// URL building
// =============================================================================

#[test]
fn build_url_base_only() {
    assert_eq!(
        build_url("appXXX", "", "", ""),
        "https://airtable.com/appXXX"
    );
}

#[test]
fn build_url_base_and_table() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "", ""),
        "https://airtable.com/appXXX/tblYYY"
    );
}

#[test]
fn build_url_with_view() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "viwZZZ", ""),
        "https://airtable.com/appXXX/tblYYY/viwZZZ"
    );
}

#[test]
fn build_url_with_record() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "", "recAAA"),
        "https://airtable.com/appXXX/tblYYY/recAAA"
    );
}

#[test]
fn build_url_all_params() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "viwZZZ", "recAAA"),
        "https://airtable.com/appXXX/tblYYY/viwZZZ/recAAA"
    );
}

#[test]
fn build_url_empty() {
    assert_eq!(build_url("", "", "", ""), "https://airtable.com");
}

// ---------------------------------------------------------------------------
// copy() -- the local, no-I/O half of duplicate() (myairtable-6q37.4)
// ---------------------------------------------------------------------------
//
// duplicate_one() is fetch + copy + create; copy() is that middle step alone, handing back a
// detached unsaved model the caller mutates and passes to create_one(). It touches no network, so
// every bit of its behaviour is pinned here rather than in the live suite. Three things are easy
// to get wrong and silent in Rust when you do:
//
//   * the SNAPSHOT. to_save_json() returns a *diff* unless `is_new() || snapshot.is_none()`, so a
//     copy that kept the source's snapshot would POST {"fields": {}} and create a blank record.
//   * ATTACHMENTS. create_one() serializes the whole struct, so a server-shaped attachment object
//     (carrying `id`, `type`, `size`, `width`, `height`) goes straight to Airtable and is rejected
//     with INVALID_ATTACHMENT_OBJECT.
//   * COMPUTED values. They are carried so the copy reads like its source; that is only safe
//     because every computed field is `#[serde(skip_serializing)]` and so never reaches the body.
mod copy_verb {
    use myairtable_static::*;
    use serde::{Deserialize, Serialize};
    use std::sync::Arc;

    const TEXT_FIELD: &str = "fldText00000000001";
    const TAGS_FIELD: &str = "fldTags00000000001";
    const ATTACH_FIELD: &str = "fldAttach000000001";
    const COMPUTED_FIELD: &str = "fldFormula00000001";
    const COMPUTED_ATTACH_FIELD: &str = "fldLookupAtt000001";

    /// Stands in for a generated ORM model: field ids as serde names, `#[serde(skip)]` record
    /// metadata, writable fields dropped when `None`, computed fields deserialized but never
    /// re-encoded. Mirrors exactly what `write_models()` in `generators/rust.py` emits, including
    /// the `project_attachments_for_copy` override over the writable attachment field only.
    #[derive(Debug, Clone, Serialize, Deserialize, Default)]
    struct Copyable {
        #[serde(skip)]
        pub id: Option<RecordId>,
        #[serde(skip)]
        pub created_time: Option<String>,
        #[serde(skip)]
        pub _meta: ModelMeta,

        #[serde(rename = "fldText00000000001")]
        #[serde(default)]
        #[serde(skip_serializing_if = "Option::is_none")]
        pub text: Option<String>,

        #[serde(rename = "fldTags00000000001")]
        #[serde(default)]
        #[serde(skip_serializing_if = "Option::is_none")]
        pub tags: Option<Vec<String>>,

        #[serde(rename = "fldAttach000000001")]
        #[serde(default)]
        #[serde(skip_serializing_if = "Option::is_none")]
        pub attachments: Option<Vec<Attachment>>,

        #[serde(rename = "fldFormula00000001")]
        #[serde(default)]
        #[serde(skip_serializing)]
        pub computed: Option<String>,

        #[serde(rename = "fldLookupAtt000001")]
        #[serde(default)]
        #[serde(skip_serializing)]
        pub computed_attachments: Option<Vec<Attachment>>,
    }

    impl OrmModel for Copyable {
        fn meta(&self) -> &ModelMeta {
            &self._meta
        }
        fn meta_mut(&mut self) -> &mut ModelMeta {
            &mut self._meta
        }
        fn get_id(&self) -> &Option<RecordId> {
            &self.id
        }
        fn set_id(&mut self, id: Option<RecordId>) {
            self.id = id;
        }
        fn get_created_time(&self) -> &Option<String> {
            &self.created_time
        }
        fn set_created_time(&mut self, ct: Option<String>) {
            self.created_time = ct;
        }
        /// Writable attachment cells only -- `computed_attachments` is deliberately absent.
        fn project_attachments_for_copy(&mut self) {
            if let Some(items) = self.attachments.as_mut() {
                for item in items.iter_mut() {
                    project_attachment_for_copy(item);
                }
            }
        }
    }

    /// An attachment exactly as the API hands it back, metadata and all.
    fn server_attachment() -> Attachment {
        Attachment {
            id: Some("attServerSide00001".to_string()),
            url: "https://example.com/a.png".to_string(),
            filename: Some("a.png".to_string()),
            mime_type: Some("image/png".to_string()),
            size: Some(1234),
            width: Some(10),
            height: Some(10),
        }
    }

    /// A model in the state `copy()` actually meets: read back from the API, so it carries an id,
    /// a created_time, a snapshot taken by `set_record_meta()`, and server-shaped attachments.
    fn source() -> Copyable {
        let mut model = Copyable {
            text: Some("hello".to_string()),
            tags: Some(vec!["a".to_string(), "b".to_string()]),
            attachments: Some(vec![server_attachment()]),
            computed: Some("computed value".to_string()),
            computed_attachments: Some(vec![server_attachment()]),
            ..Default::default()
        };
        model.set_client(
            Arc::new(AirtableClient::new(
                "keyFAKE0000000000",
                "appFAKE0000000000",
            )),
            "tblFAKE0000000001",
        );
        model.set_record_meta(
            "recSOURCE000000001".to_string(),
            Some("2026-01-01T00:00:00.000Z".to_string()),
        );
        model
    }

    // ---- the detach ----

    #[test]
    fn copy_clears_record_identity() {
        let copied = source().copy();
        assert!(copied.id.is_none(), "a carried id would UPDATE the source");
        assert!(copied.created_time.is_none());
        assert!(copied.is_new(), "is_new() is derived purely from the id");
    }

    #[test]
    fn copy_clears_the_dirty_snapshot() {
        // THE load-bearing assertion for Rust. With a snapshot in place, to_save_json() diffs
        // against it; an unmodified copy would diff to nothing and POST a blank record.
        let copied = source().copy();
        assert!(copied.meta().snapshot.is_none());
    }

    #[test]
    fn copy_keeps_the_client_handle() {
        // Kept by contract so `copy.save()` inserts without re-attaching a client. The Arc is
        // shared with the source on purpose -- AirtableClient is an immutable handle.
        let src = source();
        let copied = src.copy();
        let src_client = src.meta().client.as_ref().expect("source has a client");
        let copy_client = copied
            .meta()
            .client
            .as_ref()
            .expect("copy keeps the client");
        assert!(Arc::ptr_eq(src_client, copy_client));
        assert_eq!(copied.meta().table_id, Some("tblFAKE0000000001"));
    }

    // ---- the payload ----

    #[test]
    fn copy_serializes_the_full_writable_set_not_a_diff() {
        // The source itself, unmodified after a fetch, serializes to {} -- that is the trap the
        // snapshot reset exists to avoid. The copy must serialize everything writable instead.
        let src = source();
        assert_eq!(
            src.to_save_json(),
            serde_json::json!({}),
            "a fetched, unmodified model diffs to nothing -- this is the failure mode"
        );

        let payload = src.copy().to_save_json();
        let object = payload.as_object().expect("payload is an object");
        assert_eq!(
            object.len(),
            3,
            "expected all three writable cells: {payload}"
        );
        assert_eq!(object.get(TEXT_FIELD), Some(&serde_json::json!("hello")));
        assert_eq!(object.get(TAGS_FIELD), Some(&serde_json::json!(["a", "b"])));
        assert!(object.contains_key(ATTACH_FIELD));
    }

    #[test]
    fn computed_values_are_carried_but_never_serialized() {
        // Carrying them is what makes the copy read like its source; `#[serde(skip_serializing)]`
        // on every computed field is what keeps them out of the create body.
        let copied = source().copy();
        assert_eq!(copied.computed.as_deref(), Some("computed value"));
        assert!(copied.computed_attachments.is_some());

        let payload = copied.to_save_json();
        assert!(
            payload.get(COMPUTED_FIELD).is_none(),
            "computed leaked: {payload}"
        );
        assert!(payload.get(COMPUTED_ATTACH_FIELD).is_none());
    }

    #[test]
    fn writable_attachments_are_projected_to_url_and_filename() {
        // create accepts only {url} / {url, filename}; an echoed `id` fails with
        // INVALID_ATTACHMENT_OBJECT. Dropping the id is also what makes Airtable re-ingest the
        // file so the new record owns its attachment instead of aliasing the source's.
        let copied = source().copy();
        let attachment = &copied.attachments.as_ref().unwrap()[0];
        assert_eq!(attachment.url, "https://example.com/a.png");
        assert_eq!(attachment.filename.as_deref(), Some("a.png"));
        assert!(attachment.id.is_none());
        assert!(attachment.mime_type.is_none());
        assert!(attachment.size.is_none());
        assert!(attachment.width.is_none());
        assert!(attachment.height.is_none());

        let payload = copied.to_save_json();
        assert_eq!(
            payload.get(ATTACH_FIELD),
            Some(&serde_json::json!([{"url": "https://example.com/a.png", "filename": "a.png"}]))
        );
    }

    #[test]
    fn computed_attachment_cells_keep_their_metadata() {
        // A computed lookup can hold the very same attachment shape, but it is never written back,
        // so stripping its metadata would lose fidelity for nothing.
        let copied = source().copy();
        let attachment = &copied.computed_attachments.as_ref().unwrap()[0];
        assert_eq!(attachment.id.as_deref(), Some("attServerSide00001"));
        assert_eq!(attachment.mime_type.as_deref(), Some("image/png"));
        assert_eq!(attachment.size, Some(1234));
    }

    // ---- independence ----

    #[test]
    fn copy_shares_no_mutable_state_with_its_source() {
        let src = source();
        let mut copied = src.copy();
        copied.text = Some("changed".to_string());
        copied.tags.as_mut().unwrap().push("c".to_string());
        copied.attachments.as_mut().unwrap().clear();
        copied.computed = Some("stomped".to_string());

        assert_eq!(src.text.as_deref(), Some("hello"));
        assert_eq!(
            src.tags.as_ref().unwrap(),
            &["a".to_string(), "b".to_string()]
        );
        assert_eq!(src.attachments.as_ref().unwrap().len(), 1);
        assert_eq!(src.computed.as_deref(), Some("computed value"));
    }

    #[test]
    fn copy_leaves_the_source_completely_untouched() {
        let src = source();
        let before = format!("{src:?}");
        let _ = src.copy();
        assert_eq!(format!("{src:?}"), before);

        // Spelled out for the parts that matter most: the source is still a saved, clean record
        // with server-shaped attachments, so saving it still UPDATES rather than inserting.
        assert_eq!(src.id.as_deref(), Some("recSOURCE000000001"));
        assert_eq!(
            src.created_time.as_deref(),
            Some("2026-01-01T00:00:00.000Z")
        );
        assert!(src.meta().snapshot.is_some());
        assert!(!src.is_new());
        assert_eq!(
            src.attachments.as_ref().unwrap()[0].id.as_deref(),
            Some("attServerSide00001")
        );
    }

    #[test]
    fn copy_of_a_copy_is_still_detached() {
        // A copy is a legitimate source in its own right: no id, no snapshot, already-projected
        // attachments must survive a second round unharmed.
        let copied = source().copy().copy();
        assert!(copied.id.is_none());
        assert!(copied.meta().snapshot.is_none());
        assert_eq!(
            copied.attachments.as_ref().unwrap()[0].url,
            "https://example.com/a.png"
        );
        assert!(copied.attachments.as_ref().unwrap()[0].id.is_none());
    }

    #[test]
    fn clone_is_not_copy() {
        // `.clone()` already exists and keeps the id, the created_time and the snapshot -- a clone
        // still updates the source. This documents the difference the doc comment promises.
        let cloned = source().clone();
        assert_eq!(cloned.id.as_deref(), Some("recSOURCE000000001"));
        assert!(cloned.meta().snapshot.is_some());
        assert_eq!(cloned.to_save_json(), serde_json::json!({}));
    }
}
