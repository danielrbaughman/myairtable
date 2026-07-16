const z = require("zod");

const baseIdSchema = z.string().regex(/\bapp[a-zA-Z0-9]{14}\b/, "Invalid Airtable Base ID");
const recordIdSchema = z.string().regex(/\brec[a-zA-Z0-9]{14}\b/, "Invalid Airtable Record ID");
function validateRecordIds(idOrIds) {
	if (Array.isArray(idOrIds)) {
		idOrIds.forEach((id) => recordIdSchema.parse(id));
	} else {
		recordIdSchema.parse(idOrIds);
	}
}
const StringSchema = z.string("Value must be a string");
const NumberSchema = z.number("Value must be a number");
const BooleanSchema = z.boolean("Value must be a boolean");
const SpecialNumberSchema = z.object({ specialValue: z.string() });
const ErrorValueSchema = z.object({ error: z.string() });

const AirtableThumbnailSchema = z.object({
	url: z.string().optional(),
	width: z.number().optional(),
	height: z.number().optional(),
});

const AirtableThumbnailsSchema = z.object({
	small: AirtableThumbnailSchema.optional(),
	large: AirtableThumbnailSchema.optional(),
	full: AirtableThumbnailSchema.optional(),
});

const AirtableAttachmentSchema = z.object({
	id: z.string().optional(),
	url: z.string().optional(),
	filename: z.string().optional(),
	size: z.number().optional(),
	type: z.string().optional(),
	thumbnails: AirtableThumbnailsSchema.optional(),
});

const AirtableCollaboratorSchema = z.object({
	id: z.string().optional(),
	email: z.email().optional(),
	name: z.string().optional(),
});

const AirtableButtonSchema = z.object({
	label: z.string().optional(),
	url: z.string().optional(),
});

module.exports = {
	baseIdSchema,
	recordIdSchema,
	validateRecordIds,
	StringSchema,
	NumberSchema,
	BooleanSchema,
	SpecialNumberSchema,
	ErrorValueSchema,
	AirtableThumbnailSchema,
	AirtableThumbnailsSchema,
	AirtableAttachmentSchema,
	AirtableCollaboratorSchema,
	AirtableButtonSchema,
};
