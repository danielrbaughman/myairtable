// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Static helpers backing the generated per-model fluent CRUD methods.
 *
 * <p>The other targets resolve the model's table reflectively (Kotlin: {@code inline reified}
 * extensions); Java has no reified generics, so the generator emits covariant {@code save()}/{@code
 * fetch()}/{@code delete()} methods on each model that delegate here with an explicit class token
 * (java-plan-v2 §2.3.12).
 */
public final class ModelOps {

  private ModelOps() {}

  /**
   * Persist the model's dirty fields back to Airtable. Requires a saved record ({@code id != null})
   * — construct a fresh model and pass it to the table's {@code create(...)} to insert a brand-new
   * row.
   */
  public static <T extends AirtableModel> T save(T model, Class<T> type) {
    AirtableClient client = model.requireAttachedClient();
    if (model.isNew()) {
      throw new AirtableException.Api(
          "UNSAVED_MODEL",
          "Cannot save a model without an id; use Airtable.<table>.create(...)" + " instead");
    }
    return new OrmTable<>(model.getTableId(), type, client).update(model);
  }

  /** Re-fetch the model from the server. Returns a fresh instance. */
  public static <T extends AirtableModel> T fetch(T model, Class<T> type) {
    AirtableClient client = model.requireAttachedClient();
    if (model.isNew()) {
      throw new AirtableException.Api("UNSAVED_MODEL", "Cannot fetch an unsaved model");
    }
    return new OrmTable<>(model.getTableId(), type, client).get(model.getId());
  }

  /** Delete the record referenced by this model's {@code id}. */
  public static void delete(AirtableModel model) {
    AirtableClient client = model.requireAttachedClient();
    if (model.isNew()) {
      throw new AirtableException.Api("UNSAVED_MODEL", "Cannot delete an unsaved model");
    }
    client.deleteRecord(model.getTableId(), model.getId());
  }
}
