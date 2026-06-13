// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.BooleanNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.LongNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * A raw Airtable {@code fields} container with <b>dual ID/name lookup</b>.
 *
 * <p>Wraps a {@code Map<String, JsonNode>} keyed by field ID but accepts either an ID (e.g. {@code
 * "fldABC123"}) or a name (e.g. {@code "Primary Key"}) when looking up or mutating. Generated
 * {@code {Table}Fields} classes expose both {@code ...Id} and {@code ...Name} constants so call
 * sites can use whichever is ergonomic — without sacrificing ID-stability across field renames.
 *
 * <p>Not thread-safe: a {@code Fields} instance is a plain mutable container — confine each
 * instance to one thread.
 *
 * <p>Matches the Rust/Swift/Kotlin {@code Fields} helpers. Decoded form: JSON object keyed by field
 * IDs (because {@link AirtableQuery#isReturnFieldsByFieldId} defaults to {@code true}). Name-based
 * lookups require a name→ID map, which generated field-type classes provide.
 */
public final class Fields {

  /** Storage is always keyed by Airtable field ID. */
  private final Map<String, JsonNode> storage;

  /**
   * Optional name→ID map provided by generated {@code {Table}Fields} types. When present, {@link
   * #get} and {@link #set} accept either a field name or field ID: IDs are tried first, then names
   * are translated to IDs.
   */
  private Map<String, String> nameToId;

  public Fields() {
    this(Map.of(), Map.of());
  }

  public Fields(Map<String, JsonNode> storage) {
    this(storage, Map.of());
  }

  public Fields(Map<String, JsonNode> storage, Map<String, String> nameToId) {
    this.storage = new LinkedHashMap<>(storage);
    this.nameToId = nameToId;
  }

  /** Jackson decode hook: a {@code Fields} is its raw ID-keyed JSON object. */
  @JsonCreator
  static Fields fromJson(Map<String, JsonNode> storage) {
    return new Fields(storage);
  }

  /**
   * Jackson encode hook + view of the underlying ID-keyed storage in insertion order. {@link
   * #getNameToId} is a runtime-installed convenience and never round-trips.
   *
   * <p>Order-preserving (the backing map is a {@link LinkedHashMap}) so create/update payloads and
   * logs emit fields in a stable order; {@link Map#copyOf} would reorder by hash (JR-L1). The view
   * is shallowly unmodifiable — contained Jackson nodes remain mutable, so do not mutate them.
   */
  @JsonValue
  public Map<String, JsonNode> toMap() {
    return java.util.Collections.unmodifiableMap(new LinkedHashMap<>(storage));
  }

  public Map<String, String> getNameToId() {
    return nameToId;
  }

  public void setNameToId(Map<String, String> nameToId) {
    this.nameToId = nameToId;
  }

  /** Number of populated fields. */
  public int count() {
    return storage.size();
  }

  /** All field IDs currently present. */
  public List<String> ids() {
    return List.copyOf(storage.keySet());
  }

  /**
   * Retrieve by field ID or field name. IDs are tried first; if that misses and a {@code nameToId}
   * mapping is installed, the key is translated.
   */
  public JsonNode get(String key) {
    JsonNode direct = storage.get(key);
    if (direct != null) {
      return direct;
    }
    String id = nameToId.get(key);
    return id != null ? storage.get(id) : null;
  }

  /**
   * Store by field ID or field name. IDs are tried first (mirroring {@link #get}): a key that is
   * already a known field ID is never treated as a name, even if a pathological field name collides
   * with it. Otherwise names are translated via {@code nameToId} — if no translation is available,
   * the key is stored as-is ("store what you got", mirroring the Rust behavior). A Java {@code
   * null} value removes the entry; an explicit {@link com.fasterxml.jackson.databind.node.NullNode}
   * is stored and clears the field server-side.
   */
  public void set(String key, JsonNode value) {
    String resolved =
        storage.containsKey(key) || nameToId.containsValue(key)
            ? key
            : nameToId.getOrDefault(key, key);
    // A Java null removes the entry; an explicit NullNode is STORED and
    // serializes as JSON `null` — the only way to clear a field server-side
    // (matches Kotlin/Swift/Rust). Collapsing NullNode into "remove" here would
    // make field clears a silent no-op on the dict path (JR-H2).
    if (value != null) {
      storage.put(resolved, value);
    } else {
      storage.remove(resolved);
    }
  }

  // ---- Typed convenience getters ----

  public String getString(String key) {
    JsonNode node = get(key);
    return node != null && node.isTextual() ? node.asText() : null;
  }

  public Long getLong(String key) {
    JsonNode node = get(key);
    if (node == null || !node.isNumber()) {
      return null;
    }
    return node.asLong();
  }

  public Double getDouble(String key) {
    JsonNode node = get(key);
    if (node == null || !node.isNumber()) {
      return null;
    }
    return node.asDouble();
  }

  public Boolean getBoolean(String key) {
    JsonNode node = get(key);
    return node != null && node.isBoolean() ? node.asBoolean() : null;
  }

  public List<JsonNode> getArray(String key) {
    JsonNode node = get(key);
    if (node == null || !node.isArray()) {
      return null;
    }
    List<JsonNode> items = new ArrayList<>(node.size());
    node.forEach(items::add);
    return items;
  }

  // ---- Typed convenience setters ----

  public void setString(String key, String value) {
    set(key, value == null ? null : TextNode.valueOf(value));
  }

  public void setLong(String key, Long value) {
    set(key, value == null ? null : LongNode.valueOf(value));
  }

  public void setDouble(String key, Double value) {
    set(key, value == null ? null : DoubleNode.valueOf(value));
  }

  public void setBoolean(String key, Boolean value) {
    set(key, value == null ? null : BooleanNode.valueOf(value));
  }

  public void setStrings(String key, List<String> value) {
    if (value == null) {
      set(key, null);
      return;
    }
    ArrayNode array = AirtableJson.MAPPER.createArrayNode();
    value.forEach(array::add);
    set(key, array);
  }

  @Override
  public boolean equals(Object other) {
    return other instanceof Fields f && f.storage.equals(storage) && f.nameToId.equals(nameToId);
  }

  @Override
  public int hashCode() {
    return 31 * storage.hashCode() + Objects.hashCode(nameToId);
  }

  @Override
  public String toString() {
    return "Fields(" + storage + ")";
  }
}
