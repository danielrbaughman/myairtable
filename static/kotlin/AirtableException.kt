// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * Errors raised by the MyAirtable runtime.
 *
 * A sealed exception hierarchy: catch [AirtableException] for everything, or a
 * specific subclass for targeted handling.
 */
sealed class AirtableException(
    message: String,
    cause: Throwable? = null,
) : Exception(message, cause) {
    /** Non-2xx HTTP response. [body] is the raw response body if decodable as UTF-8. */
    class Http(
        val statusCode: Int,
        val body: String?,
    ) : AirtableException(if (body.isNullOrEmpty()) "AirtableException.Http($statusCode)" else "AirtableException.Http($statusCode): $body") {
        override fun equals(other: Any?): Boolean = other is Http && other.statusCode == statusCode && other.body == body

        override fun hashCode(): Int = 31 * statusCode + (body?.hashCode() ?: 0)
    }

    /** Airtable returned a structured error envelope (`{"error": {"type": ..., "message": ...}}`). */
    class Api(
        val code: String,
        val apiMessage: String,
    ) : AirtableException("AirtableException.Api($code): $apiMessage") {
        override fun equals(other: Any?): Boolean = other is Api && other.code == code && other.apiMessage == apiMessage

        override fun hashCode(): Int = 31 * code.hashCode() + apiMessage.hashCode()
    }

    /** JSON decoding failed. [cause] originates from kotlinx.serialization. */
    class Decoding(
        cause: Throwable,
    ) : AirtableException("AirtableException.Decoding: ${cause.message}", cause) {
        // Underlying decode errors are not comparable; treat all decoding errors as equal.
        override fun equals(other: Any?): Boolean = other is Decoding

        override fun hashCode(): Int = javaClass.hashCode()
    }

    /** A request URL could not be constructed. */
    class InvalidUrl : AirtableException("AirtableException.InvalidUrl") {
        override fun equals(other: Any?): Boolean = other is InvalidUrl

        override fun hashCode(): Int = javaClass.hashCode()
    }

    /** [AirtableClient] was initialized without an API key or base ID. */
    class MissingCredentials : AirtableException("AirtableException.MissingCredentials") {
        override fun equals(other: Any?): Boolean = other is MissingCredentials

        override fun hashCode(): Int = javaClass.hashCode()
    }

    /**
     * A transport-level failure (connect, DNS, socket, request timeout) — the
     * request never produced an HTTP response. [cause] is the underlying I/O
     * or timeout exception. Coroutine cancellation is never wrapped here.
     */
    class Network(
        cause: Throwable,
    ) : AirtableException("AirtableException.Network: ${cause.message}", cause) {
        // Underlying transport errors are not comparable; treat all network errors as equal.
        override fun equals(other: Any?): Boolean = other is Network

        override fun hashCode(): Int = javaClass.hashCode()
    }

    /**
     * Airtable returned 429 Too Many Requests. [retryAfterSeconds] is the
     * `Retry-After` header value in seconds if present.
     */
    class RateLimited(
        val retryAfterSeconds: Double?,
    ) : AirtableException(
            if (retryAfterSeconds != null) "AirtableException.RateLimited(retryAfter: ${retryAfterSeconds}s)" else "AirtableException.RateLimited",
        ) {
        override fun equals(other: Any?): Boolean = other is RateLimited && other.retryAfterSeconds == retryAfterSeconds

        override fun hashCode(): Int = retryAfterSeconds?.hashCode() ?: 0
    }
}

/**
 * Wire-format Airtable error envelope. Matches the shape Airtable returns on
 * non-2xx responses: `{"error": {"type": "...", "message": "..."}}` or
 * `{"error": "STRING"}` for some legacy endpoints.
 */
@Serializable
internal data class AirtableErrorEnvelope(
    val error: JsonElement,
) {
    /** Convert to the public exception type. */
    fun toAirtableException(): AirtableException =
        when (error) {
            is JsonObject -> {
                val type = (error["type"] as? JsonPrimitive)?.contentOrNull ?: "UNKNOWN"
                val message = (error["message"] as? JsonPrimitive)?.contentOrNull ?: ""
                AirtableException.Api(code = type, apiMessage = message)
            }

            is JsonPrimitive -> {
                AirtableException.Api(code = "UNKNOWN", apiMessage = error.jsonPrimitive.content)
            }

            else -> {
                AirtableException.Api(code = "UNKNOWN", apiMessage = error.toString())
            }
        }
}
