import { describe, it, expect } from "vitest";
import {
	AND,
	OR,
	XOR,
	NOT,
	ID,
	Field,
	TextField,
	SingleSelectField,
	MultiSelectField,
	NumberField,
	BooleanField,
	AttachmentsField,
	DateField,
} from "../static/javascript/formula.js";

describe("Logic Functions", () => {
	describe("AND", () => {
		it("returns AND() for empty args", () => {
			expect(AND()).toBe("AND()");
		});

		it("filters empty strings", () => {
			expect(AND("a", "", "b")).toBe("AND(a,b)");
		});

		it("joins multiple args with comma", () => {
			expect(AND("a", "b", "c")).toBe("AND(a,b,c)");
		});

		it("handles single arg", () => {
			expect(AND("a")).toBe("AND(a)");
		});
	});

	describe("OR", () => {
		it("returns OR() for empty args", () => {
			expect(OR()).toBe("OR()");
		});

		it("filters empty strings", () => {
			expect(OR("a", "", "b")).toBe("OR(a,b)");
		});

		it("joins multiple args with comma", () => {
			expect(OR("a", "b", "c")).toBe("OR(a,b,c)");
		});

		it("handles single arg", () => {
			expect(OR("a")).toBe("OR(a)");
		});
	});

	describe("XOR", () => {
		it("returns XOR() for empty args", () => {
			expect(XOR()).toBe("XOR()");
		});

		it("filters empty strings", () => {
			expect(XOR("a", "", "b")).toBe("XOR(a,b)");
		});

		it("joins multiple args with comma", () => {
			expect(XOR("a", "b")).toBe("XOR(a,b)");
		});
	});

	describe("NOT", () => {
		it("returns NOT() for empty args", () => {
			expect(NOT()).toBe("NOT()");
		});

		it("filters empty strings", () => {
			expect(NOT("a", "")).toBe("NOT(a)");
		});

		it("handles single arg", () => {
			expect(NOT("a")).toBe("NOT(a)");
		});
	});
});

describe("ID", () => {
	const id = new ID();

	describe("equals", () => {
		it("returns correct formula for valid record ID", () => {
			expect(id.equals("rec12345678901234")).toBe("RECORD_ID()='rec12345678901234'");
		});

		it("throws for invalid record ID", () => {
			expect(() => id.equals("invalid")).toThrow();
		});

		it("throws for record ID with wrong length", () => {
			expect(() => id.equals("rec123")).toThrow();
		});
	});

	describe("inList", () => {
		it("returns FALSE() for empty array", () => {
			expect(id.inList([])).toBe("FALSE()");
		});

		it("returns equals for single ID", () => {
			expect(id.inList(["rec12345678901234"])).toBe("RECORD_ID()='rec12345678901234'");
		});

		it("returns OR for multiple IDs", () => {
			const result = id.inList(["rec12345678901234", "rec56789012345678"]);
			expect(result).toContain("OR(");
			expect(result).toContain("rec12345678901234");
			expect(result).toContain("rec56789012345678");
		});

		it("throws for invalid record IDs in array", () => {
			expect(() => id.inList(["invalid"])).toThrow();
		});
	});
});

describe("Field", () => {
	describe("constructor", () => {
		it("strips braces from input and adds them back in getter", () => {
			const field = new Field("{Name}");
			expect(field.field).toBe("{Name}");
		});

		it("removes newlines from name", () => {
			const field = new Field("Field\nName");
			expect(field.field).toBe("{FieldName}");
		});

		it("removes tabs from name", () => {
			const field = new Field("Field\tName");
			expect(field.field).toBe("{FieldName}");
		});

		it("removes carriage returns from name", () => {
			const field = new Field("Field\rName");
			expect(field.field).toBe("{FieldName}");
		});

		it("handles field without special chars", () => {
			const field = new Field("TestField");
			expect(field.field).toBe("{TestField}");
		});
	});

	describe("empty", () => {
		it("returns BLANK() formula", () => {
			const field = new Field("Name");
			expect(field.empty()).toBe("{Name}=BLANK()");
		});
	});

	describe("notEmpty", () => {
		it("returns field reference", () => {
			const field = new Field("Name");
			expect(field.notEmpty()).toBe("{Name}");
		});
	});

	describe("field getter", () => {
		it("returns nameOrId wrapped in braces", () => {
			const field = new Field("TestField");
			expect(field.field).toBe("{TestField}");
		});
	});
});

describe("TextField", () => {
	describe("equals", () => {
		it("case sensitive, no trim (default)", () => {
			const field = new TextField("Name");
			expect(field.equals("John")).toBe('{Name}="John"');
		});

		it("escapes quotes in value", () => {
			const field = new TextField("Name");
			expect(field.equals('Say "Hello"')).toBe('{Name}="Say \\"Hello\\""');
		});

		it("case sensitive with trim", () => {
			const field = new TextField("Name");
			const result = field.equals("John", true, true);
			expect(result).toContain("TRIM(");
		});

		it("case insensitive, no trim", () => {
			const field = new TextField("Name");
			const result = field.equals("John", false, false);
			expect(result).toContain("LOWER(");
		});

		it("case insensitive with trim", () => {
			const field = new TextField("Name");
			const result = field.equals("John", false, true);
			expect(result).toContain("LOWER(");
			expect(result).toContain("TRIM(");
		});

		it("throws for non-string value", () => {
			const field = new TextField("Name");
			expect(() => field.equals(123)).toThrow();
		});
	});

	describe("phoneEquals", () => {
		it("normalizes phone with spaces", () => {
			const field = new TextField("Phone");
			const result = field.phoneEquals("555 123 4567");
			expect(result).toContain("SUBSTITUTE");
		});

		it("normalizes phone with dashes", () => {
			const field = new TextField("Phone");
			const result = field.phoneEquals("555-123-4567");
			expect(result).toContain("SUBSTITUTE");
		});

		it("normalizes phone with parentheses", () => {
			const field = new TextField("Phone");
			const result = field.phoneEquals("(555) 123-4567");
			expect(result).toContain("SUBSTITUTE");
		});

		it("normalizes phone with plus sign", () => {
			const field = new TextField("Phone");
			const result = field.phoneEquals("+1 555 123 4567");
			expect(result).toContain("SUBSTITUTE");
		});

		it("normalizes phone with dots", () => {
			const field = new TextField("Phone");
			const result = field.phoneEquals("555.123.4567");
			expect(result).toContain("SUBSTITUTE");
		});

		it("throws for non-string value", () => {
			const field = new TextField("Phone");
			expect(() => field.phoneEquals(5551234567)).toThrow();
		});
	});

	describe("notEquals", () => {
		it("returns != formula", () => {
			const field = new TextField("Name");
			expect(field.notEquals("John")).toBe('{Name}!="John"');
		});

		it("escapes quotes in value", () => {
			const field = new TextField("Name");
			const result = field.notEquals('Say "Hello"');
			expect(result).toBe('{Name}!="Say \\"Hello\\""');
		});
	});

	describe("_find", () => {
		it("case sensitive with trim", () => {
			const field = new TextField("Name");
			const result = field.contains("test", true, true);
			expect(result).toContain("TRIM(");
			expect(result).toContain("FIND(");
		});

		it("case sensitive no trim", () => {
			const field = new TextField("Name");
			const result = field.contains("test", true, false);
			expect(result).toContain("FIND(");
			expect(result).not.toContain("TRIM(");
		});

		it("case insensitive with trim (default)", () => {
			const field = new TextField("Name");
			const result = field.contains("test");
			expect(result).toContain("LOWER(");
			expect(result).toContain("TRIM(");
		});

		it("case insensitive no trim", () => {
			const field = new TextField("Name");
			const result = field.contains("test", false, false);
			expect(result).toContain("LOWER(");
			expect(result).not.toContain("TRIM(");
		});
	});

	describe("contains", () => {
		it("returns FIND > 0", () => {
			const field = new TextField("Description");
			const result = field.contains("keyword");
			expect(result).toContain(">0");
		});
	});

	describe("containsAny", () => {
		it("returns OR() for empty array", () => {
			const field = new TextField("Tags");
			expect(field.containsAny([])).toBe("OR()");
		});

		it("returns single contains for one value", () => {
			const field = new TextField("Tags");
			const result = field.containsAny(["tag1"]);
			expect(result).toContain("FIND(");
		});

		it("returns OR for multiple values", () => {
			const field = new TextField("Tags");
			const result = field.containsAny(["tag1", "tag2"]);
			expect(result).toContain("OR(");
		});
	});

	describe("containsAll", () => {
		it("returns AND() for empty array", () => {
			const field = new TextField("Tags");
			expect(field.containsAll([])).toBe("AND()");
		});

		it("returns AND for multiple values", () => {
			const field = new TextField("Tags");
			const result = field.containsAll(["tag1", "tag2"]);
			expect(result).toContain("AND(");
		});
	});

	describe("equalsAny", () => {
		it("returns OR() for empty array", () => {
			const field = new TextField("Tags");
			expect(field.equalsAny([])).toBe("OR()");
		});

		it("returns single equals for one value", () => {
			const field = new TextField("Tags");
			const result = field.equalsAny(["tag1"]);
			expect(result).toContain('{Tags}="tag1"');
		});

		it("returns OR for multiple values", () => {
			const field = new TextField("Tags");
			const result = field.equalsAny(["tag1", "tag2"]);
			expect(result).toContain("OR(");
		});

		it("respects caseSensitive=false", () => {
			const field = new TextField("Tags");
			const result = field.equalsAny(["tag1"], false);
			expect(result).toContain("LOWER(");
		});

		it("respects trim=true", () => {
			const field = new TextField("Tags");
			const result = field.equalsAny(["tag1"], true, true);
			expect(result).toContain("TRIM(");
		});
	});

	describe("notContains", () => {
		it("returns FIND = 0", () => {
			const field = new TextField("Description");
			const result = field.notContains("keyword");
			expect(result).toContain("NOT");
		});
	});

	describe("startsWith", () => {
		it("returns FIND = 1", () => {
			const field = new TextField("Name");
			const result = field.startsWith("prefix");
			expect(result).toContain("=1");
		});
	});

	describe("notStartsWith", () => {
		it("returns FIND != 1", () => {
			const field = new TextField("Name");
			const result = field.notStartsWith("prefix");
			expect(result).toContain("!=1");
		});
	});

	describe("endsWith", () => {
		it("uses = comparison with LEN calculation", () => {
			const field = new TextField("Name");
			const result = field.endsWith("suffix");
			expect(result).toContain("LEN(");
			expect(result).toContain(" = ");
		});

		it("case sensitive with trim", () => {
			const field = new TextField("Name");
			const result = field.endsWith("suffix", true, true);
			expect(result).toContain("TRIM(");
		});

		it("case sensitive no trim", () => {
			const field = new TextField("Name");
			const result = field.endsWith("suffix", true, false);
			expect(result).not.toContain("TRIM(");
		});

		it("case insensitive with trim (default)", () => {
			const field = new TextField("Name");
			const result = field.endsWith("suffix");
			expect(result).toContain("LOWER(");
			expect(result).toContain("TRIM(");
		});

		it("case insensitive no trim", () => {
			const field = new TextField("Name");
			const result = field.endsWith("suffix", false, false);
			expect(result).toContain("LOWER(");
			expect(result).not.toContain("TRIM(");
		});
	});

	describe("notEndsWith", () => {
		it("uses != comparison", () => {
			const field = new TextField("Name");
			const result = field.notEndsWith("suffix");
			expect(result).toContain(" != ");
		});
	});

	describe("regexMatch", () => {
		it("produces REGEX formula", () => {
			const field = new TextField("Email");
			const result = field.regexMatch("^[a-z]+@");
			expect(result).toContain("REGEX(");
		});

		it("throws for non-string pattern", () => {
			const field = new TextField("Email");
			expect(() => field.regexMatch(123)).toThrow();
		});
	});
});

describe("SingleSelectField", () => {
	describe("equals", () => {
		it("delegates to TextField.equals", () => {
			const field = new SingleSelectField("Status");
			expect(field.equals("Active")).toBe('{Status}="Active"');
		});
	});

	describe("notEquals", () => {
		it("delegates to TextField.notEquals", () => {
			const field = new SingleSelectField("Status");
			expect(field.notEquals("Inactive")).toBe('{Status}!="Inactive"');
		});
	});
});

describe("MultiSelectField", () => {
	describe("containsOption", () => {
		it("uses contains with default params", () => {
			const field = new MultiSelectField("Tags");
			const result = field.contains("Option1");
			expect(result).toContain("FIND(");
		});

		it("respects caseSensitive flag", () => {
			const field = new MultiSelectField("Tags");
			const result = field.contains("Option1", false, false);
			expect(result).toContain("LOWER(");
		});
	});

	describe("containsAllOptions", () => {
		it("produces AND formula", () => {
			const field = new MultiSelectField("Tags");
			const result = field.containsAll(["A", "B"]);
			expect(result).toContain("AND(");
		});
	});

	describe("containsAnyOptions", () => {
		it("produces OR formula", () => {
			const field = new MultiSelectField("Tags");
			const result = field.containsAny(["A", "B"]);
			expect(result).toContain("OR(");
		});
	});

	describe("notContainsOption", () => {
		it("uses notContains", () => {
			const field = new MultiSelectField("Tags");
			const result = field.notContains("Option1");
			expect(result).toContain("NOT");
		});
	});
});

describe("NumberField", () => {
	describe("equals", () => {
		it("returns = formula", () => {
			const field = new NumberField("Amount");
			expect(field.equals(100)).toBe("{Amount}=100");
		});

		it("throws for non-number", () => {
			const field = new NumberField("Amount");
			expect(() => field.equals("100")).toThrow();
		});
	});

	describe("notEquals", () => {
		it("returns != formula", () => {
			const field = new NumberField("Amount");
			expect(field.notEquals(100)).toBe("{Amount}!=100");
		});
	});

	describe("greaterThan", () => {
		it("returns > formula", () => {
			const field = new NumberField("Amount");
			expect(field.greaterThan(100)).toBe("{Amount}>100");
		});
	});

	describe("lessThan", () => {
		it("returns < formula", () => {
			const field = new NumberField("Amount");
			expect(field.lessThan(100)).toBe("{Amount}<100");
		});
	});

	describe("greaterThanOrEquals", () => {
		it("returns >= formula", () => {
			const field = new NumberField("Amount");
			expect(field.greaterThanOrEquals(100)).toBe("{Amount}>=100");
		});
	});

	describe("lessThanOrEquals", () => {
		it("returns <= formula", () => {
			const field = new NumberField("Amount");
			expect(field.lessThanOrEquals(100)).toBe("{Amount}<=100");
		});
	});

	describe("between", () => {
		it("inclusive uses >= and <=", () => {
			const field = new NumberField("Amount");
			const result = field.between(10, 100, true);
			expect(result).toContain("AND(");
			expect(result).toContain(">=10");
			expect(result).toContain("<=100");
		});

		it("exclusive uses > and <", () => {
			const field = new NumberField("Amount");
			const result = field.between(10, 100, false);
			expect(result).toContain("AND(");
			expect(result).toContain(">10");
			expect(result).toContain("<100");
		});

		it("handles floats", () => {
			const field = new NumberField("Amount");
			const result = field.between(10.5, 100.5);
			expect(result).toContain("10.5");
			expect(result).toContain("100.5");
		});
	});
});

describe("BooleanField", () => {
	describe("equals", () => {
		it("returns TRUE() for true", () => {
			const field = new BooleanField("Active");
			expect(field.equals(true)).toBe("{Active}=TRUE()");
		});

		it("returns FALSE() for false", () => {
			const field = new BooleanField("Active");
			expect(field.equals(false)).toBe("{Active}=FALSE()");
		});

		it("throws for non-boolean", () => {
			const field = new BooleanField("Active");
			expect(() => field.equals("true")).toThrow();
		});
	});

	describe("true", () => {
		it("returns TRUE() formula", () => {
			const field = new BooleanField("Active");
			expect(field.true()).toBe("{Active}=TRUE()");
		});
	});

	describe("false", () => {
		it("returns FALSE() formula", () => {
			const field = new BooleanField("Active");
			expect(field.false()).toBe("{Active}=FALSE()");
		});
	});
});

describe("AttachmentsField", () => {
	describe("notEmpty", () => {
		it("uses LEN > 0", () => {
			const field = new AttachmentsField("Files");
			expect(field.notEmpty()).toBe("LEN({Files})>0");
		});
	});

	describe("empty", () => {
		it("uses LEN = 0", () => {
			const field = new AttachmentsField("Files");
			expect(field.empty()).toBe("LEN({Files})=0");
		});
	});

	describe("count", () => {
		it("returns LEN = count formula", () => {
			const field = new AttachmentsField("Files");
			expect(field.count(5)).toBe("LEN({Files})=5");
		});

		it("handles zero count", () => {
			const field = new AttachmentsField("Files");
			expect(field.count(0)).toBe("LEN({Files})=0");
		});
	});
});

describe("parseDate (via DateField)", () => {
	it("handles Date objects", () => {
		const field = new DateField("Created");
		const date = new Date("2024-01-15T00:00:00.000Z");
		const result = field.on(date);
		expect(result).toContain("2024-01-15");
	});

	it("handles ISO strings", () => {
		const field = new DateField("Created");
		const result = field.on("2024-01-15");
		expect(result).toContain("DATETIME_PARSE");
	});

	it("throws for invalid date strings", () => {
		const field = new DateField("Created");
		expect(() => field.on("not a date")).toThrow("Could not parse date");
	});
});

describe("DateField", () => {
	describe("on", () => {
		it("without date returns DateComparison", () => {
			const field = new DateField("Created");
			const result = field.on();
			expect(result).toHaveProperty("compare", "=");
		});

		it("with date returns formula", () => {
			const field = new DateField("Created");
			const result = field.on("2024-01-15");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("onOrAfter", () => {
		it("without date returns DateComparison with <=", () => {
			const field = new DateField("Created");
			const result = field.onOrAfter();
			expect(result).toHaveProperty("compare", "<=");
		});

		it("with date returns formula", () => {
			const field = new DateField("Created");
			const result = field.onOrAfter("2024-01-15");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("onOrBefore", () => {
		it("without date returns DateComparison with >=", () => {
			const field = new DateField("Created");
			const result = field.onOrBefore();
			expect(result).toHaveProperty("compare", ">=");
		});

		it("with date returns formula", () => {
			const field = new DateField("Created");
			const result = field.onOrBefore("2024-01-15");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("after", () => {
		it("without date returns DateComparison with < (reversed)", () => {
			const field = new DateField("Created");
			const result = field.after();
			expect(result).toHaveProperty("compare", "<");
		});

		it("with date returns formula", () => {
			const field = new DateField("Created");
			const result = field.after("2024-01-15");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("before", () => {
		it("without date returns DateComparison with > (reversed)", () => {
			const field = new DateField("Created");
			const result = field.before();
			expect(result).toHaveProperty("compare", ">");
		});

		it("with date returns formula", () => {
			const field = new DateField("Created");
			const result = field.before("2024-01-15");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("notOn", () => {
		it("without date returns DateComparison with !=", () => {
			const field = new DateField("Created");
			const result = field.notOn();
			expect(result).toHaveProperty("compare", "!=");
		});

		it("with date returns formula", () => {
			const field = new DateField("Created");
			const result = field.notOn("2024-01-15");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("between", () => {
		it("inclusive uses onOrAfter and onOrBefore", () => {
			const field = new DateField("Created");
			const result = field.between("2024-01-01", "2024-12-31", true);
			expect(result).toContain("AND(");
		});

		it("exclusive uses after and before", () => {
			const field = new DateField("Created");
			const result = field.between("2024-01-01", "2024-12-31", false);
			expect(result).toContain("AND(");
		});

		it("handles Date objects", () => {
			const field = new DateField("Created");
			const result = field.between(new Date("2024-01-01"), new Date("2024-12-31"));
			expect(result).toContain("AND(");
		});
	});
});

describe("DateComparison", () => {
	const timeAgoMethods = [
		["millisecondsAgo", "milliseconds"],
		["secondsAgo", "seconds"],
		["minutesAgo", "minutes"],
		["hoursAgo", "hours"],
		["daysAgo", "days"],
		["weeksAgo", "weeks"],
		["monthsAgo", "months"],
		["quartersAgo", "quarters"],
		["yearsAgo", "years"],
	];

	timeAgoMethods.forEach(([method, unit]) => {
		describe(method, () => {
			it(`produces DATETIME_DIFF with ${unit}`, () => {
				const field = new DateField("Created");
				const comparison = field.onOrAfter();
				const result = comparison[method](10);
				expect(result).toContain("DATETIME_DIFF");
				expect(result).toContain(unit);
			});
		});
	});

	it("stores comparison operator", () => {
		const field = new DateField("Created");
		const comparison = field.onOrAfter();
		expect(comparison.compare).toBe("<=");
	});
});

describe("Complex Formula Integration", () => {
	describe("multi-field AND combinations", () => {
		it("combines text, number, and date fields", () => {
			const name = new TextField("Name");
			const amount = new NumberField("Amount");
			const created = new DateField("Created");

			const result = AND(name.contains("test"), amount.greaterThan(100), created.onOrAfter("2024-01-01"));

			expect(result).toContain("AND(");
			expect(result).toContain("FIND(");
			expect(result).toContain("{Amount}");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("multi-field OR combinations", () => {
		it("combines select fields and boolean", () => {
			const status = new SingleSelectField("Status");
			const urgent = new BooleanField("Urgent");

			const result = OR(status.equals("Active"), status.equals("Pending"), urgent.true());

			expect(result).toContain("OR(");
			expect(result).toContain("{Status}");
			expect(result).toContain("{Urgent}");
			expect(result).toContain("TRUE()");
		});
	});

	describe("nested logic", () => {
		it("handles OR within AND", () => {
			const name = new TextField("Name");
			const amount = new NumberField("Amount");

			const result = AND(OR(name.contains("John"), name.contains("Jane")), amount.between(100, 1000));

			expect(result).toContain("AND(");
			expect(result).toContain("OR(");
			expect(result).toContain("John");
			expect(result).toContain("Jane");
			expect(result).toContain(">=100");
			expect(result).toContain("<=1000");
		});

		it("handles AND within OR", () => {
			const type = new TextField("Type");
			const value = new NumberField("Value");

			const result = OR(AND(type.equals("A"), value.greaterThan(50)), AND(type.equals("B"), value.lessThan(25)));

			expect(result).toContain("OR(");
			expect(result.match(/AND\(/g)).toHaveLength(2);
			expect(result).toContain('"A"');
			expect(result).toContain('"B"');
			expect(result).toContain(">50");
			expect(result).toContain("<25");
		});
	});

	describe("NOT with compound conditions", () => {
		it("combines NOT with AND for exclusion", () => {
			const status = new TextField("Status");
			const tags = new TextField("Tags");

			const result = AND(status.equals("Active"), NOT(tags.contains("archived")));

			expect(result).toContain("AND(");
			expect(result).toContain("NOT(");
			expect(result).toContain('"Active"');
			expect(result).toContain("archived");
		});

		it("handles multiple NOT conditions", () => {
			const tags = new TextField("Tags");
			const status = new TextField("Status");

			const result = AND(NOT(tags.contains("deleted")), NOT(status.equals("Archived")));

			expect(result).toContain("AND(");
			expect(result.match(/NOT\(/g)).toHaveLength(2);
			expect(result).toContain("deleted");
			expect(result).toContain('"Archived"');
		});
	});

	describe("date range with other filters", () => {
		it("combines date between with text and number", () => {
			const created = new DateField("Created");
			const status = new TextField("Status");
			const score = new NumberField("Score");

			const result = AND(
				created.between("2024-01-01", "2024-12-31"),
				status.equals("Complete"),
				score.greaterThanOrEquals(80),
			);

			expect(result).toContain("AND(");
			expect(result).toContain("DATETIME_PARSE");
			expect(result).toContain('"Complete"');
			expect(result).toContain(">=80");
		});
	});

	describe("time-relative with status", () => {
		it("combines days_ago with status filter", () => {
			const modified = new DateField("Modified");
			const status = new SingleSelectField("Status");

			const result = AND(modified.onOrAfter().daysAgo(7), status.equals("Active"));

			expect(result).toContain("AND(");
			expect(result).toContain("DATETIME_DIFF");
			expect(result).toContain("days");
			expect(result).toContain("<=7");
			expect(result).toContain('"Active"');
		});
	});

	describe("deeply nested formulas", () => {
		it("handles three levels of nesting", () => {
			const category = new TextField("Category");
			const priority = new NumberField("Priority");
			const active = new BooleanField("Active");

			const result = OR(
				AND(category.equals("Sales"), priority.greaterThan(5)),
				AND(category.equals("Support"), active.true()),
			);

			expect(result).toContain("OR(");
			expect(result.match(/AND\(/g)).toHaveLength(2);
			expect(result).toContain('"Sales"');
			expect(result).toContain('"Support"');
			expect(result).toContain(">5");
			expect(result).toContain("TRUE()");
		});
	});

	describe("XOR with field comparisons", () => {
		it("combines boolean fields with XOR", () => {
			const statusA = new BooleanField("StatusA");
			const statusB = new BooleanField("StatusB");

			const result = XOR(statusA.true(), statusB.true());

			expect(result).toContain("XOR(");
			expect(result).toContain("{StatusA}=TRUE()");
			expect(result).toContain("{StatusB}=TRUE()");
		});
	});

	describe("complex date with number range", () => {
		it("combines time-relative date with number between", () => {
			const created = new DateField("Created");
			const amount = new NumberField("Amount");
			const count = new NumberField("Count");

			const result = AND(created.after().weeksAgo(4), amount.between(1000, 5000), count.greaterThan(0));

			expect(result).toContain("AND(");
			expect(result).toContain("DATETIME_DIFF");
			expect(result).toContain("weeks");
			expect(result).toContain(">=1000");
			expect(result).toContain("<=5000");
			expect(result).toContain(">0");
		});
	});

	describe("phone normalization with other conditions", () => {
		it("combines phoneEquals with status and date filters", () => {
			const phone = new TextField("Phone");
			const status = new SingleSelectField("Status");
			const created = new DateField("Created");

			const result = AND(phone.phoneEquals("555-123-4567"), status.equals("Active"), created.onOrAfter("2024-01-01"));

			expect(result).toContain("AND(");
			expect(result).toContain("SUBSTITUTE");
			expect(result).toContain("{Status}");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("string operations with case/trim combinations", () => {
		it("combines startsWith and endsWith with different flags", () => {
			const name = new TextField("Name");
			const code = new TextField("Code");

			const result = AND(name.startsWith("Dr.", true, false), code.endsWith("-v2", false, true));

			expect(result).toContain("AND(");
			expect(result).toContain("FIND");
			expect(result).toContain("Dr.");
			expect(result).toContain("-v2");
		});

		it("combines case-insensitive contains with case-sensitive equals", () => {
			const description = new TextField("Description");
			const category = new TextField("Category");

			const result = AND(description.contains("urgent", false, true), category.equals("Support", true, false));

			expect(result).toContain("AND(");
			expect(result).toContain("LOWER");
			expect(result).toContain('"Support"');
		});
	});

	describe("ID.inList with field conditions", () => {
		it("combines record ID list with status filter", () => {
			const id = new ID();
			const status = new SingleSelectField("Status");

			const result = AND(id.inList(["rec12345678901234", "rec98765432109876"]), status.equals("Active"));

			expect(result).toContain("AND(");
			expect(result).toContain("RECORD_ID()");
			expect(result).toContain("OR(");
			expect(result).toContain('"Active"');
		});

		it("handles single ID in list with other conditions", () => {
			const id = new ID();
			const amount = new NumberField("Amount");

			const result = AND(id.inList(["rec12345678901234"]), amount.greaterThan(100));

			expect(result).toContain("AND(");
			expect(result).toContain("RECORD_ID()='rec12345678901234'");
			expect(result).toContain(">100");
		});
	});

	describe("attachment field in complex formulas", () => {
		it("combines attachment count with status and boolean", () => {
			const files = new AttachmentsField("Files");
			const verified = new BooleanField("Verified");
			const status = new TextField("Status");

			const result = AND(files.count(3), verified.true(), status.equals("Complete"));

			expect(result).toContain("AND(");
			expect(result).toContain("LEN({Files})=3");
			expect(result).toContain("TRUE()");
			expect(result).toContain('"Complete"');
		});

		it("combines notEmpty attachments with date filter", () => {
			const docs = new AttachmentsField("Documents");
			const submitted = new DateField("Submitted");

			const result = AND(docs.notEmpty(), submitted.onOrBefore("2024-06-30"));

			expect(result).toContain("AND(");
			expect(result).toContain("LEN({Documents})>0");
			expect(result).toContain("DATETIME_PARSE");
		});
	});

	describe("empty/notEmpty in compound scenarios", () => {
		it("combines empty check with OR alternatives", () => {
			const notes = new TextField("Notes");
			const status = new SingleSelectField("Status");

			const result = OR(notes.empty(), status.equals("Draft"));

			expect(result).toContain("OR(");
			expect(result).toContain("{Notes}=BLANK()");
			expect(result).toContain('"Draft"');
		});

		it("combines notEmpty with NOT contains", () => {
			const description = new TextField("Description");
			const tags = new TextField("Tags");

			const result = AND(description.notEmpty(), NOT(tags.contains("archived")));

			expect(result).toContain("AND(");
			expect(result).toContain("{Description}");
			expect(result).toContain("NOT(");
		});
	});

	describe("regex with other conditions", () => {
		it("combines regex match with number and boolean", () => {
			const email = new TextField("Email");
			const score = new NumberField("Score");
			const active = new BooleanField("Active");

			const result = AND(email.regexMatch("^[a-z]+@company\\.com$"), score.greaterThanOrEquals(90), active.true());

			expect(result).toContain("AND(");
			expect(result).toContain("REGEX(");
			expect(result).toContain(">=90");
			expect(result).toContain("TRUE()");
		});
	});

	describe("four-level deep nesting", () => {
		it("handles deeply nested logic", () => {
			const type = new TextField("Type");
			const priority = new NumberField("Priority");
			const active = new BooleanField("Active");
			const status = new SingleSelectField("Status");

			const result = OR(
				AND(OR(type.equals("A"), type.equals("B")), priority.greaterThan(5)),
				AND(active.true(), status.equals("Urgent")),
			);

			expect(result).toContain("OR(");
			expect(result.match(/AND\(/g)).toHaveLength(2);
			expect(result.match(/OR\(/g)).toHaveLength(2);
			expect(result).toContain('"A"');
			expect(result).toContain('"B"');
			expect(result).toContain(">5");
		});
	});

	describe("multiple time units in date comparisons", () => {
		it("combines different time-ago units", () => {
			const created = new DateField("Created");
			const modified = new DateField("Modified");

			const result = AND(created.after().daysAgo(30), modified.onOrAfter().hoursAgo(24));

			expect(result).toContain("AND(");
			expect(result).toContain("days");
			expect(result).toContain("hours");
			expect(result.match(/DATETIME_DIFF/g)).toHaveLength(2);
		});
	});

	describe("quote escaping in complex scenarios", () => {
		it("handles quotes in text values with other conditions", () => {
			const title = new TextField("Title");
			const count = new NumberField("Count");

			const result = AND(title.equals('Say "Hello"'), count.greaterThan(0));

			expect(result).toContain("AND(");
			expect(result).toContain('\\"Hello\\"');
			expect(result).toContain(">0");
		});
	});

	describe("exclusive vs inclusive ranges", () => {
		it("combines exclusive number range with date filter", () => {
			const amount = new NumberField("Amount");
			const date = new DateField("Date");

			const result = AND(amount.between(100, 500, false), date.onOrAfter("2024-01-01"));

			expect(result).toContain("AND(");
			expect(result).toContain(">100");
			expect(result).toContain("<500");
			expect(result).not.toContain(">=100");
			expect(result).not.toContain("<=500");
		});

		it("combines exclusive date range with status", () => {
			const created = new DateField("Created");
			const status = new SingleSelectField("Status");

			const result = AND(created.between("2024-01-01", "2024-12-31", false), status.equals("Active"));

			expect(result).toContain("AND(");
			expect(result).toContain("DATETIME_PARSE");
			expect(result).toContain('"Active"');
		});
	});
});
