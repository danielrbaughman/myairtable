import { describe, it, expect } from "vitest";
import pkg from "../src/myairtable/static/javascript/airtable-model.js";

const { AirtableModel } = pkg;

/**
 * Hermetic guards on `copy()` — the local, no-I/O half of `duplicate()`.
 * Mirrors tests/copy.test.ts against the JavaScript runtime.
 *
 * The trap this feature exists to avoid is silent: a model read back from Airtable has
 * `_isNew === false` and an empty dirty set, so its create payload is `{}` and inserting it
 * produces a BLANK record. The second trap is aliasing: `_createLinkedField` bakes an
 * `onDirty` closure bound to the owning model, so a shared wrapper would make edits to the
 * COPY mark the SOURCE dirty.
 */

const SERVER_ATTACHMENT = {
	id: "attServerSide00001",
	url: "https://example.com/a.png",
	filename: "a.png",
	size: 1234,
	type: "image/png",
	width: 10,
	height: 10,
	thumbnails: { small: { url: "https://example.com/t.png" } },
};

const DESCRIPTORS = [
	{ propertyName: "text", fieldId: "fldText0000000001", fieldName: "Text", isComputed: false, fieldType: "generic" },
	{ propertyName: "tags", fieldId: "fldTags0000000001", fieldName: "Tags", isComputed: false, fieldType: "generic" },
	{
		propertyName: "attachments",
		fieldId: "fldAttach00000001",
		fieldName: "Attachments",
		isComputed: false,
		fieldType: "attachment",
	},
	{
		propertyName: "links",
		fieldId: "fldLinks000000001",
		fieldName: "Links",
		isComputed: false,
		fieldType: "linkedRecords",
		linkedModelFromId: (id) => ({ id }),
	},
	{ propertyName: "calc", fieldId: "fldCalc0000000001", fieldName: "Calc", isComputed: true, fieldType: "generic" },
	{
		propertyName: "lookupAttachments",
		fieldId: "fldLookAtt0000001",
		fieldName: "Lookup",
		isComputed: true,
		fieldType: "attachment",
	},
];

/** Stands in for a generated model: same constructor shape, minus the Record/Table wiring. */
class TestModel extends AirtableModel {
	static fieldDescriptors = DESCRIPTORS;

	constructor(data = {}) {
		super(data?.id ?? "");
		this.initializeFields(data ?? {});
	}

	// Test-only windows onto protected state.
	get isNew() {
		return this._isNew;
	}
	get dirtyFields() {
		return [...this._dirtyFields].sort();
	}
	raw(name) {
		return this._fields[name];
	}
	createPayload() {
		return this.writableFields(true);
	}
	/** Puts the model in the state a server read leaves it in. */
	asServerRead() {
		this.clearDirtyFlags();
		return this;
	}
}

function source(overrides = {}) {
	return new TestModel({
		id: "recSOURCE00000001",
		text: "hello",
		tags: ["a", "b"],
		attachments: [{ ...SERVER_ATTACHMENT }],
		links: ["recLINKED00000001"],
		calc: "computed value",
		lookupAttachments: [{ ...SERVER_ATTACHMENT }],
		...overrides,
	}).asServerRead();
}

describe("copy() detaches", () => {
	it("clears the record id", () => {
		expect(source().copy().id).toBe("");
	});

	it("marks the copy as new", () => {
		// Without this the create payload is {} and the insert is a blank record.
		expect(source().isNew).toBe(false);
		expect(source().copy().isNew).toBe(true);
	});

	it("emits a full writable payload rather than an empty one", () => {
		expect(source().createPayload()).toEqual({});
		const payload = source().copy().createPayload();
		expect(payload["fldText0000000001"]).toBe("hello");
		expect(payload["fldTags0000000001"]).toEqual(["a", "b"]);
	});

	it("starts with an empty dirty set", () => {
		expect(source().copy().dirtyFields).toEqual([]);
	});

	it("leaves the source untouched", () => {
		const original = source();
		const before = JSON.stringify(original.toJson());
		original.copy();
		expect(JSON.stringify(original.toJson())).toBe(before);
		expect(original.id).toBe("recSOURCE00000001");
		expect(original.dirtyFields).toEqual([]);
	});
});

describe("copy() carries values", () => {
	it("carries writable values", () => {
		const copied = source().copy();
		expect(copied.raw("text")).toBe("hello");
		expect(copied.raw("tags")).toEqual(["a", "b"]);
	});

	it("carries computed values so the copy reads like its source", () => {
		expect(source().copy().raw("calc")).toBe("computed value");
	});

	it("keeps computed values off the wire", () => {
		expect(source().copy().createPayload()["fldCalc0000000001"]).toBeUndefined();
	});

	it("carries linked record ids", () => {
		expect(source().copy().raw("links").ids).toEqual(["recLINKED00000001"]);
	});

	it("carries the runtime formula toggle", () => {
		const original = source();
		original.evaluateFormulasAtRuntime = true;
		expect(original.copy().evaluateFormulasAtRuntime).toBe(true);
	});
});

describe("copy() projects attachments", () => {
	it("reduces writable attachments to the shape create accepts", () => {
		expect(source().copy().raw("attachments")).toEqual([{ url: "https://example.com/a.png", filename: "a.png" }]);
	});

	it("leaves computed attachment-shaped cells with full metadata", () => {
		// A lookup can hold the same shape but is never written; stripping it loses fidelity.
		expect(source().copy().raw("lookupAttachments")).toEqual([SERVER_ATTACHMENT]);
	});
});

describe("copy() shares no mutable state", () => {
	it("does not alias arrays", () => {
		const original = source();
		const copied = original.copy();
		copied.raw("tags").push("c");
		expect(original.raw("tags")).toEqual(["a", "b"]);
	});

	it("does not alias nested attachment objects", () => {
		const original = source({ attachments: [{ url: "u", filename: "f" }] });
		const copied = original.copy();
		copied.raw("attachments")[0].filename = "mutated";
		expect(original.raw("attachments")[0].filename).toBe("f");
	});

	it("rebinds linked wrappers so editing the copy does not dirty the source", () => {
		// The onDirty closure is bound to whichever model owns the wrapper.
		const original = source();
		const copied = original.copy();
		expect(copied.raw("links")).not.toBe(original.raw("links"));
		copied.raw("links").ids = ["recOTHER000000001"];
		expect(copied.dirtyFields).toEqual(["links"]);
		expect(original.dirtyFields).toEqual([]);
	});
});
