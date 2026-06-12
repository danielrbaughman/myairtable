// ==========================================
// MyAirtable static runtime.
// ==========================================

// The V/N/S/A/AN/AS/D coercion helpers deliberately use the cross-language
// runtime naming shared with the Rust/Swift targets; the formula transpiler
// emits calls to these exact names.
@file:Suppress("ktlint:standard:function-naming")

package myairtable

import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.modules.SerializersModule
import kotlinx.serialization.modules.contextual
import kotlinx.serialization.serializer
import java.time.Instant
import kotlin.math.abs
import kotlin.math.floor
import kotlin.time.Duration
import kotlin.time.DurationUnit

/** Shared JSON configuration for every wire payload and runtime coercion. */
object AirtableJson {
    val instance: Json =
        Json {
            ignoreUnknownKeys = true
            encodeDefaults = false
            explicitNulls = false
            serializersModule =
                SerializersModule {
                    // Required so reified serializer<T>() lookups resolve Instant
                    // when it is nested inside generics (MaybeSpecialOrError<Instant>,
                    // VecOrValue<...>) — bare Instant/Duration fields use the explicit
                    // V() overloads below, and model properties use
                    // @file:UseSerializers. Without this, V() on computed date
                    // fields silently degraded to JsonNull (myairtable-w3rk).
                    // NOTE kotlin.time.Duration cannot be registered here: its
                    // BUILT-IN ISO-8601 serializer always wins over contextual,
                    // so Duration nested in generics emits "PT…" strings — a
                    // known cross-format quirk affecting only computed duration
                    // roll-ups (decode of those fields is unaffected;
                    // AirtableDurationSerializer handles wire decode via
                    // @file:UseSerializers).
                    contextual(Instant::class, AirtableInstantSerializer)
                }
        }
}

// =============================================================================
// region Runtime value coercion
//
// The formula runtime operates on `JsonElement?` (kotlinx's JSON sum type —
// the analog of Swift's custom AirtableJSONValue). These top-level helpers
// mirror the Swift AirtableRuntime coercion section; the formula transpiler
// emits calls to them directly (flat package — no qualifier needed).
// =============================================================================

/**
 * Convert any serializable value to [JsonElement] for runtime composition.
 * Used by the transpiler to wrap model field references (e.g. `V(this.numberInt)`).
 * `null` inputs produce [JsonNull]; failures fall through to [JsonNull] rather
 * than throwing.
 */
inline fun <reified T> V(value: T?): JsonElement {
    if (value == null) return JsonNull
    return try {
        val serializer = AirtableJson.instance.serializersModule.serializer<T>()
        AirtableJson.instance.encodeToJsonElement(serializer, value)
    } catch (_: SerializationException) {
        // Unserializable types degrade to null rather than throwing inside a
        // formula evaluation (matches the Swift target's V() behavior).
        JsonNull
    }
}

/** Pass-through for values already in [JsonElement] form. */
fun V(value: JsonElement?): JsonElement = value ?: JsonNull

/** Dates compose into formulas as ISO 8601 strings (matches the Swift target). */
fun V(value: Instant?): JsonElement = value?.let { JsonPrimitive(it.toString()) } ?: JsonNull

/**
 * Durations compose into formulas as numeric seconds — the Airtable wire form.
 * (The built-in kotlin.time.Duration serializer would emit ISO "PT…" strings.)
 */
fun V(value: Duration?): JsonElement = value?.let { JsonPrimitive(it.toDouble(DurationUnit.SECONDS)) } ?: JsonNull

/** Coerce to [Double]. Mirrors Airtable's numeric coercion rules. */
fun N(value: JsonElement?): Double =
    when (value) {
        null, is JsonNull -> {
            0.0
        }

        is JsonPrimitive -> {
            if (value.isString) {
                value.content.trim().toDoubleOrNull() ?: 0.0
            } else {
                value.booleanOrNull?.let { if (it) 1.0 else 0.0 }
                    ?: value.doubleOrNull
                    ?: 0.0
            }
        }

        is JsonArray -> {
            if (value.isEmpty()) 0.0 else N(value[0])
        }

        is JsonObject -> {
            0.0
        }
    }

/** Coerce to [String]. Airtable strips `.0` from whole-number floats. */
fun S(value: JsonElement?): String =
    when (value) {
        null, is JsonNull -> {
            ""
        }

        is JsonPrimitive -> {
            if (value.isString) {
                value.content
            } else {
                value.booleanOrNull?.let { if (it) "1" else "0" }
                    ?: value.longOrNull?.toString()
                    ?: value.doubleOrNull?.let { d ->
                        if (d.isFinite() && d == floor(d) && abs(d) < 1e15) d.toLong().toString() else d.toString()
                    }
                    ?: value.content
            }
        }

        is JsonArray -> {
            if (value.isEmpty()) "" else S(value[0])
        }

        is JsonObject -> {
            ""
        }
    }

/** Flatten args into a single `List<JsonElement>` (one level; Kotlin nulls dropped). */
fun A(args: List<JsonElement?>): List<JsonElement> =
    buildList {
        for (arg in args) {
            when (arg) {
                null -> {}

                is JsonArray -> {
                    addAll(arg)
                }

                else -> {
                    add(arg)
                }
            }
        }
    }

/** Flatten + coerce to numbers. */
fun AN(args: List<JsonElement?>): List<Double> = A(args).map { N(it) }

/** Flatten + coerce to strings. */
fun AS(args: List<JsonElement?>): List<String> = A(args).map { S(it) }

/** Coerce to [Instant]. ISO 8601 strings, Unix timestamps, or `null`. */
fun D(value: JsonElement?): Instant? =
    when (value) {
        null, is JsonNull -> {
            null
        }

        is JsonPrimitive -> {
            if (value.isString) {
                AirtableDateParser.parse(value.content)
            } else {
                value.doubleOrNull?.let { Instant.ofEpochMilli((it * 1000).toLong()) }
            }
        }

        is JsonArray -> {
            if (value.isEmpty()) null else D(value[0])
        }

        is JsonObject -> {
            null
        }
    }

/** Airtable truthiness: null/0/NaN/""/empty array/empty object are falsy. */
fun isTruthy(value: JsonElement?): Boolean =
    when (value) {
        null, is JsonNull -> {
            false
        }

        is JsonPrimitive -> {
            if (value.isString) {
                value.content.isNotEmpty()
            } else {
                value.booleanOrNull
                    ?: value.doubleOrNull?.let { it != 0.0 && !it.isNaN() }
                    ?: value.content.isNotEmpty()
            }
        }

        is JsonArray -> {
            value.isNotEmpty()
        }

        is JsonObject -> {
            value.isNotEmpty()
        }
    }

// endregion
