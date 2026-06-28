using System.Threading;
using System.Threading.Tasks;

namespace MyAirtable;

/// <summary>
/// Static helpers backing the generated per-model fluent CRUD methods. C# has reified generics, so
/// these need no class token (unlike the Java target): the generated <c>{Table}Model</c> emits
/// covariant <c>SaveAsync</c>/<c>FetchAsync</c>/<c>DeleteAsync</c> methods that delegate here.
/// </summary>
public static class ModelOps
{
    /// <summary>
    /// Persist the model's dirty fields back to Airtable. Requires a saved record (<c>Id != null</c>)
    /// — construct a fresh model and pass it to the table's <c>CreateAsync(...)</c> to insert a
    /// brand-new row.
    /// </summary>
    public static Task<T> SaveAsync<T>(
        T model,
        bool typecast = false,
        CancellationToken ct = default
    )
        where T : AirtableModel
    {
        var client = model.RequireAttachedClient();
        if (model.IsNew)
            throw new AirtableException.ApiError(
                "UNSAVED_MODEL",
                "Cannot save a model without an id; use the table's CreateAsync(...) instead"
            );
        return new OrmTable<T>(model.TableId, client).UpdateAsync(model, typecast, ct);
    }

    /// <summary>Re-fetch the model from the server. Returns a fresh instance.</summary>
    public static Task<T> FetchAsync<T>(T model, CancellationToken ct = default)
        where T : AirtableModel
    {
        var client = model.RequireAttachedClient();
        if (model.IsNew)
            throw new AirtableException.ApiError("UNSAVED_MODEL", "Cannot fetch an unsaved model");
        return new OrmTable<T>(model.TableId, client).GetAsync(model.RequireId(), ct);
    }

    /// <summary>Delete the record referenced by this model's <c>Id</c>.</summary>
    public static Task DeleteAsync(AirtableModel model, CancellationToken ct = default)
    {
        var client = model.RequireAttachedClient();
        if (model.IsNew)
            throw new AirtableException.ApiError("UNSAVED_MODEL", "Cannot delete an unsaved model");
        return client.DeleteRecordAsync(model.TableId, model.RequireId(), ct);
    }
}
