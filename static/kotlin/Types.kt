// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.InternalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.SerialKind
import kotlinx.serialization.descriptors.buildSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonEncoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeParseException
import kotlin.time.Duration
import kotlin.time.DurationUnit
import kotlin.time.toDuration

/**
 * Airtable record IDs are opaque strings like `recXXXXXXXXXXXXXX`. Alias to
 * [String] for ergonomics; using the alias consistently documents intent at
 * call sites and in generated code.
 */
typealias RecordId = String

/** Sort direction for Airtable list queries. */
@Serializable
enum class SortDirection(
    val wire: String,
) {
    @SerialName("asc")
    ASC("asc"),

    @SerialName("desc")
    DESC("desc"),
}

/**
 * A single sort clause. Airtable supports multiple sort clauses per query
 * and applies them left-to-right.
 */
@Serializable
data class Sort(
    val field: String,
    val direction: SortDirection = SortDirection.ASC,
)

/** Airtable attachment (file/image) as returned in field values. */
@Serializable
data class AirtableAttachment(
    val id: String? = null,
    val url: String? = null,
    val filename: String? = null,
    val size: Long? = null,
    val type: String? = null,
    val thumbnails: AirtableThumbnails? = null,
)

/** Attachment thumbnail variants (`small`, `large`, `full`). */
@Serializable
data class AirtableThumbnails(
    val small: Thumbnail? = null,
    val large: Thumbnail? = null,
    val full: Thumbnail? = null,
) {
    @Serializable
    data class Thumbnail(
        val url: String,
        val width: Long? = null,
        val height: Long? = null,
    )
}

/** Airtable collaborator (user/account). */
@Serializable
data class AirtableCollaborator(
    val id: String,
    val email: String? = null,
    val name: String? = null,
    val profilePicUrl: String? = null,
)

/** Airtable button field — read-only reference to a button click action. */
@Serializable
data class AirtableButton(
    val label: String? = null,
    val url: String? = null,
)

/**
 * Wrapping envelope for an Airtable record as returned by the API:
 * `{"id": "recXXX", "createdTime": "2024-...", "fields": {...}}`.
 */
@Serializable
data class AirtableRecord<T>(
    val id: RecordId,
    @Serializable(with = AirtableInstantSerializer::class)
    val createdTime: Instant? = null,
    val fields: T,
)

/**
 * A value that can be either a single `T` or a `List<T?>` — decoded from
 * Airtable responses where the cardinality of lookup/rollup fields can't be
 * determined from metadata alone. Matches the Rust/Swift `VecOrValue<T>`.
 */
@Serializable(with = VecOrValueSerializer::class)
sealed interface VecOrValue<T> {
    data class Single<T>(
        val value: T,
    ) : VecOrValue<T>

    data class Multiple<T>(
        val items: List<T?>,
    ) : VecOrValue<T>

    /** The single value, or `null` if this is the list shape. */
    val single: T?
        get() = (this as? Single<T>)?.value

    /** The list of values, or `null` if this is the single shape. */
    val multiple: List<T?>?
        get() = (this as? Multiple<T>)?.items

    /** Flatten to non-null values regardless of shape. */
    val values: List<T>
        get() =
            when (this) {
                is Single -> listOf(value)
                is Multiple -> items.filterNotNull()
            }
}

/**
 * JSON-format serializer for [VecOrValue]: peeks at the raw element and
 * dispatches structurally (array → [VecOrValue.Multiple], else
 * [VecOrValue.Single]). kotlinx has no try-and-fallback decoding, so the
 * element-peek pattern replaces Swift's `try?` chain. List items are nullable:
 * Airtable rollup/lookup arrays can contain `null` entries when the source
 * field is missing on a linked record.
 */
class VecOrValueSerializer<T>(
    private val tSerializer: KSerializer<T>,
) : KSerializer<VecOrValue<T>> {
    @OptIn(ExperimentalSerializationApi::class, InternalSerializationApi::class)
    override val descriptor: SerialDescriptor = buildSerialDescriptor("myairtable.VecOrValue", SerialKind.CONTEXTUAL)

    override fun deserialize(decoder: Decoder): VecOrValue<T> {
        val jsonDecoder = decoder as? JsonDecoder ?: error("VecOrValue supports JSON only")
        val element = jsonDecoder.decodeJsonElement()
        return if (element is JsonArray) {
            VecOrValue.Multiple(
                element.map { item ->
                    if (item is JsonNull) null else jsonDecoder.json.decodeFromJsonElement(tSerializer, item)
                },
            )
        } else {
            VecOrValue.Single(jsonDecoder.json.decodeFromJsonElement(tSerializer, element))
        }
    }

    override fun serialize(
        encoder: Encoder,
        value: VecOrValue<T>,
    ) {
        val jsonEncoder = encoder as? JsonEncoder ?: error("VecOrValue supports JSON only")
        val element =
            when (value) {
                is VecOrValue.Single -> {
                    jsonEncoder.json.encodeToJsonElement(tSerializer, value.value)
                }

                is VecOrValue.Multiple -> {
                    JsonArray(value.items.map { if (it == null) JsonNull else jsonEncoder.json.encodeToJsonElement(tSerializer, it) })
                }
            }
        jsonEncoder.encodeJsonElement(element)
    }
}

/**
 * An Airtable special number value (NaN, Infinity, -Infinity).
 *
 * Returned by formula fields when the computation produces a non-finite
 * number. JSON shape: `{"specialValue": "NaN"}`. Only the object form is
 * accepted — a bare string or lookup-style array must not decode as this.
 */
@Serializable
data class SpecialNumber(
    val specialValue: String,
)

/**
 * An Airtable error value from a failed formula computation.
 *
 * JSON shape: `{"error": "#ERROR!"}`. Only the object form is accepted.
 */
@Serializable
data class ErrorValue(
    val error: String,
)

/**
 * Wraps a computed field that may be a value, special number, or error.
 *
 * Airtable returns `{"specialValue": ...}` / `{"error": ...}` objects for
 * formula / rollup / lookup fields whose computation is non-finite or fails.
 */
@Serializable(with = MaybeSpecialOrErrorSerializer::class)
sealed interface MaybeSpecialOrError<T> {
    data class Value<T>(
        val value: T,
    ) : MaybeSpecialOrError<T>

    data class Special<T>(
        val special: SpecialNumber,
    ) : MaybeSpecialOrError<T>

    data class Error<T>(
        val error: ErrorValue,
    ) : MaybeSpecialOrError<T>

    /** The wrapped value, or `null` for special/error variants. */
    val valueOrNull: T?
        get() = (this as? Value<T>)?.value

    val specialOrNull: SpecialNumber?
        get() = (this as? Special<T>)?.special

    val errorOrNull: ErrorValue?
        get() = (this as? Error<T>)?.error

    val isValue: Boolean
        get() = this is Value

    val isSpecial: Boolean
        get() = this is Special

    val isError: Boolean
        get() = this is Error
}

/**
 * JSON-format serializer for [MaybeSpecialOrError]: peeks at the raw element.
 * Objects carrying exactly the sentinel keys (`specialValue` / `error`)
 * dispatch to the special/error variants; everything else decodes as `T`.
 */
class MaybeSpecialOrErrorSerializer<T>(
    private val tSerializer: KSerializer<T>,
) : KSerializer<MaybeSpecialOrError<T>> {
    @OptIn(ExperimentalSerializationApi::class, InternalSerializationApi::class)
    override val descriptor: SerialDescriptor = buildSerialDescriptor("myairtable.MaybeSpecialOrError", SerialKind.CONTEXTUAL)

    override fun deserialize(decoder: Decoder): MaybeSpecialOrError<T> {
        val jsonDecoder = decoder as? JsonDecoder ?: error("MaybeSpecialOrError supports JSON only")
        val element = jsonDecoder.decodeJsonElement()
        if (element is JsonObject) {
            if (element.keys == setOf("specialValue")) {
                return MaybeSpecialOrError.Special(jsonDecoder.json.decodeFromJsonElement(SpecialNumber.serializer(), element))
            }
            if (element.keys == setOf("error")) {
                return MaybeSpecialOrError.Error(jsonDecoder.json.decodeFromJsonElement(ErrorValue.serializer(), element))
            }
        }
        return MaybeSpecialOrError.Value(jsonDecoder.json.decodeFromJsonElement(tSerializer, element))
    }

    override fun serialize(
        encoder: Encoder,
        value: MaybeSpecialOrError<T>,
    ) {
        val jsonEncoder = encoder as? JsonEncoder ?: error("MaybeSpecialOrError supports JSON only")
        val element =
            when (value) {
                is MaybeSpecialOrError.Value -> {
                    jsonEncoder.json.encodeToJsonElement(tSerializer, value.value)
                }

                is MaybeSpecialOrError.Special -> {
                    jsonEncoder.json.encodeToJsonElement(SpecialNumber.serializer(), value.special)
                }

                is MaybeSpecialOrError.Error -> {
                    jsonEncoder.json.encodeToJsonElement(ErrorValue.serializer(), value.error)
                }
            }
        jsonEncoder.encodeJsonElement(element)
    }
}

/**
 * Parses the date-string shapes Airtable actually returns: full ISO 8601 with
 * fractional seconds (`2024-01-15T10:30:00.000Z`), ISO 8601 without
 * (`2024-01-15T10:30:00Z` or with a UTC offset), and date-only fields
 * (`2024-01-15`, decoded as UTC midnight). [Instant.parse] alone rejects the
 * offset and date-only forms.
 */
object AirtableDateParser {
    fun parse(s: String): Instant? {
        try {
            return Instant.parse(s)
        } catch (_: DateTimeParseException) {
            // fall through
        }
        try {
            return OffsetDateTime.parse(s).toInstant()
        } catch (_: DateTimeParseException) {
            // fall through
        }
        return try {
            LocalDate.parse(s).atStartOfDay(ZoneOffset.UTC).toInstant()
        } catch (_: DateTimeParseException) {
            null
        }
    }
}

/**
 * Serializer for every wire date: accepts the ISO 8601 and date-only string
 * shapes Airtable returns (see [AirtableDateParser]); encodes ISO 8601 UTC.
 */
object AirtableInstantSerializer : KSerializer<Instant> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("myairtable.AirtableInstant", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): Instant {
        val s = decoder.decodeString()
        return AirtableDateParser.parse(s)
            ?: throw IllegalArgumentException("Expected ISO 8601 or YYYY-MM-DD date string, got '$s'.")
    }

    override fun serialize(
        encoder: Encoder,
        value: Instant,
    ) {
        encoder.encodeString(value.toString())
    }
}

/**
 * Serializer for Airtable duration fields. Wire value is numeric **seconds**
 * (confirmed against real data during the Swift target's development).
 */
object AirtableDurationSerializer : KSerializer<Duration> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("myairtable.AirtableDuration", PrimitiveKind.DOUBLE)

    override fun deserialize(decoder: Decoder): Duration = decoder.decodeDouble().toDuration(DurationUnit.SECONDS)

    override fun serialize(
        encoder: Encoder,
        value: Duration,
    ) {
        encoder.encodeDouble(value.toDouble(DurationUnit.SECONDS))
    }
}
