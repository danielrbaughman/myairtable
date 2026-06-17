using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyAirtable;

/// <summary>
/// The single shared <see cref="JsonSerializerOptions"/> for the runtime. Owns ONLY the options;
/// all value coercions live on <see cref="AirtableRuntime"/> (one transpiler qualifier). The two
/// sum-type factories are registered GLOBALLY here, so nested generics resolve without any
/// field-level converter attributes.
/// </summary>
public static class AirtableJson
{
    public static readonly JsonSerializerOptions Options = CreateOptions();

    private static JsonSerializerOptions CreateOptions()
    {
        var o = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            // Value carriers (AirtableAttachment/Collaborator/Button/thumbnails) and the REST
            // envelope records carry no [JsonPropertyName], so their property names follow this
            // policy — Airtable's wire format is camelCase (url, profilePicUrl, createdTime).
            // Generated model properties are unaffected: they all carry explicit [JsonPropertyName]
            // field-id attributes, which override the policy.
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        };
        o.Converters.Add(new VecOrValueConverterFactory());
        o.Converters.Add(new MaybeSpecialOrErrorConverterFactory());
        o.Converters.Add(new AirtableDateConverter());
        o.Converters.Add(new AirtableDurationConverter());
        return o;
    }
}
