// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

/**
 * Query parameters for Airtable list-records requests.
 *
 * Idiomatic Kotlin construction: named arguments and `copy(...)`:
 * ```kotlin
 * AirtableQuery(formula = "NOT({Name}=BLANK())", maxRecords = 10)
 *     .withSort("Name", SortDirection.DESC)
 * ```
 */
data class AirtableQuery(
    val formula: String? = null,
    val sort: List<Sort> = emptyList(),
    val fields: List<String> = emptyList(),
    val maxRecords: Int? = null,
    val pageSize: Int? = null,
    val view: String? = null,
    val returnFieldsByFieldId: Boolean = true,
    val cellFormat: CellFormat = CellFormat.JSON,
    val timeZone: String? = null,
    val userLocale: String? = null,
) {
    enum class CellFormat(
        val wire: String,
    ) {
        JSON("json"),
        STRING("string"),
    }

    /** Append a sort clause (chainable convenience over `copy`). */
    fun withSort(
        field: String,
        direction: SortDirection = SortDirection.ASC,
    ): AirtableQuery = copy(sort = sort + Sort(field, direction))

    /**
     * Convert to query parameters using Airtable's list-records shape:
     * `filterByFormula`, `fields[]`, `sort[i][field]`, `sort[i][direction]`,
     * `maxRecords`, `pageSize`, `view`, `returnFieldsByFieldId`, `cellFormat`,
     * `timeZone`, `userLocale`.
     */
    fun toParameters(): List<Pair<String, String>> =
        buildList {
            if (!formula.isNullOrEmpty()) add("filterByFormula" to formula)
            for (field in fields) add("fields[]" to field)
            sort.forEachIndexed { i, s ->
                add("sort[$i][field]" to s.field)
                add("sort[$i][direction]" to s.direction.wire)
            }
            maxRecords?.let { add("maxRecords" to it.toString()) }
            pageSize?.let { add("pageSize" to it.toString()) }
            if (!view.isNullOrEmpty()) add("view" to view)
            if (returnFieldsByFieldId) add("returnFieldsByFieldId" to "true")
            if (cellFormat != CellFormat.JSON) add("cellFormat" to cellFormat.wire)
            if (!timeZone.isNullOrEmpty()) add("timeZone" to timeZone)
            if (!userLocale.isNullOrEmpty()) add("userLocale" to userLocale)
        }
}
