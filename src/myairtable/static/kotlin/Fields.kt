// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

/**
 * A raw Airtable `fields` container with **dual ID/name lookup**.
 *
 * Wraps a `Map<String, JsonElement>` keyed by field ID but accepts either an
 * ID (e.g. `"fldABC123"`) or a name (e.g. `"Primary Key"`) when looking up or
 * mutating. Generated `{Table}Fields` objects expose both `...Id` and `...Name`
 * constants so call sites can use whichever is ergonomic — without sacrificing
 * ID-stability across field renames.
 *
 * Not thread-safe: a `Fields` instance is a plain mutable container (unlike
 * Swift's value-semantics struct) — confine each instance to one coroutine.
 *
 * Matches the Rust target's `Fields` helper and the Swift `Fields` struct.
 * Decoded form: JSON object keyed by field IDs (because
 * [AirtableQuery.returnFieldsByFieldId] defaults to `true`). Name-based lookups
 * require a name→ID map, which generated field-type objects provide.
 */
@Serializable(with = FieldsSerializer::class)
class Fields(
    storage: Map<String, JsonElement> = emptyMap(),
    /**
     * Optional name→ID map provided by generated `{Table}Fields` types. When
     * present, [get] and [set] accept either a field name or field ID: IDs are
     * tried first, then names are translated to IDs.
     */
    var nameToId: Map<String, String> = emptyMap(),
) {
    /** Storage is always keyed by Airtable field ID. */
    private val storage: MutableMap<String, JsonElement> = storage.toMutableMap()

    /** Number of populated fields. */
    val count: Int get() = storage.size

    /** All field IDs currently present. */
    val ids: List<String> get() = storage.keys.toList()

    /** Immutable view of the underlying ID-keyed storage. */
    fun toMap(): Map<String, JsonElement> = storage.toMap()

    /**
     * Retrieve by field ID or field name (`fields["..."]` or `fields.get("...")`).
     * IDs are tried first; if that misses and a [nameToId] mapping is
     * installed, the key is translated.
     */
    operator fun get(key: String): JsonElement? = storage[key] ?: nameToId[key]?.let { storage[it] }

    /**
     * Store by field ID or field name. IDs are tried first (mirroring [get]):
     * a key that is already a known field ID is never treated as a name, even
     * if a pathological field name collides with it. Otherwise names are
     * translated via [nameToId] — if no translation is available, the key is
     * stored as-is ("store what you got", mirroring the Rust behavior). A
     * `null` value removes the entry.
     */
    operator fun set(
        key: String,
        value: JsonElement?,
    ) {
        val resolved =
            if (key in storage || nameToId.containsValue(key)) key else nameToId[key] ?: key
        if (value != null) {
            storage[resolved] = value
        } else {
            storage.remove(resolved)
        }
    }

    // region Typed convenience getters

    fun getString(key: String): String? = (get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content

    fun getLong(key: String): Long? {
        val p = get(key) as? JsonPrimitive ?: return null
        if (p.isString) return null
        return p.longOrNull ?: p.doubleOrNull?.toLong()
    }

    fun getDouble(key: String): Double? {
        val p = get(key) as? JsonPrimitive ?: return null
        if (p.isString) return null
        return p.doubleOrNull
    }

    fun getBoolean(key: String): Boolean? = (get(key) as? JsonPrimitive)?.booleanOrNull

    fun getArray(key: String): List<JsonElement>? = (get(key) as? JsonArray)?.toList()

    // endregion

    // region Typed convenience setters

    fun setString(
        key: String,
        value: String?,
    ) = set(key, value?.let { JsonPrimitive(it) })

    fun setLong(
        key: String,
        value: Long?,
    ) = set(key, value?.let { JsonPrimitive(it) })

    fun setDouble(
        key: String,
        value: Double?,
    ) = set(key, value?.let { JsonPrimitive(it) })

    fun setBoolean(
        key: String,
        value: Boolean?,
    ) = set(key, value?.let { JsonPrimitive(it) })

    fun setStrings(
        key: String,
        value: List<String>?,
    ) = set(key, value?.let { list -> JsonArray(list.map { JsonPrimitive(it) }) })

    // endregion

    override fun equals(other: Any?): Boolean = other is Fields && other.storage == storage && other.nameToId == nameToId

    override fun hashCode(): Int = 31 * storage.hashCode() + nameToId.hashCode()

    override fun toString(): String = "Fields($storage)"
}

/**
 * Serializes [Fields] as its raw ID-keyed object; [Fields.nameToId] is a
 * runtime-installed convenience and never round-trips.
 */
object FieldsSerializer : KSerializer<Fields> {
    private val mapSerializer = MapSerializer(String.serializer(), JsonElement.serializer())

    override val descriptor: SerialDescriptor = mapSerializer.descriptor

    override fun deserialize(decoder: Decoder): Fields = Fields(mapSerializer.deserialize(decoder))

    override fun serialize(
        encoder: Encoder,
        value: Fields,
    ) {
        mapSerializer.serialize(encoder, value.toMap())
    }
}
