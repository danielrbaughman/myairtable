"""Tests for computed field read-only property generation in TS, JS, and Python generators."""

from pathlib import Path

from src.meta import Base, Choice, Field, Options, Result, Table
from src.meta_types import FieldType


def make_test_base(fields_spec: list[tuple[str, str, FieldType]], formula_map: dict[str, str] | None = None) -> Base:
    """Create a Base with one Table from (name, field_id, field_type) tuples.

    Uses model_construct() to bypass API calls and validation.
    """
    base = Base.model_construct(
        id="appTEST123",
        tables=[],
        _original_metadata={"tables": []},
        _csv_cache=None,
        _involves_lookup_cache={},
        _involves_rollup_cache={},
        _field_index={},
        _table_index={},
        _select_fields_cache=None,
        _select_field_ids_cache=None,
    )

    table = Table.model_construct(
        id="tblTEST123",
        name="Test Table",
        primary_field_id="fld000",
        fields=[],
        views=[],
        base=base,
        _field_id_to_name_cache=None,
    )
    # Initialize PrivateAttr caches on the table
    table.__pydantic_private__ = {"_field_id_to_name_cache": None, "_snake": None, "_pascal": None, "_model": None, "_upper": None, "_name_cache": {}}

    formula_map = formula_map or {}

    for field_name, field_id, field_type in fields_spec:
        formula_str = formula_map.get(field_id)
        result_obj = Result.model_construct(type="number", options=None) if field_type == "formula" else None
        field = Field.model_construct(
            id=field_id,
            name=field_name,
            type=field_type,
            description=None,
            options=Options.model_construct(
                formula=formula_str,
                view_id_for_record_selection=None,
                is_reversed=None,
                precision=None,
                choices=None,
                linked_table_id=None,
                prefers_single_record_link=None,
                inverse_link_field_id=None,
                icon=None,
                color=None,
                is_valid=True,
                date_format=None,
                duration_format=None,
                record_link_field_id=None,
                field_id_in_linked_table=None,
                referenced_field_ids=None,
                result=result_obj,
                field_id=field_id,
            ),
            table=table,
            base=base,
        )
        # Initialize PrivateAttr caches on the field
        field.__pydantic_private__ = {
            "_select_options_cache": None,
            "_python_type_csv": None,
            "_typescript_type_csv": None,
            "_formula_cache": {},
            "_generic_type": None,
            "_python_type": None,
            "_typescript_type": None,
            "_zod_type": None,
            "_snake": None,
            "_pascal": None,
            "_model": None,
            "_upper": None,
            "_name_cache": {},
        }
        table.fields.append(field)
        base._field_index[field_id] = field

    base.tables.append(table)
    base._table_index[table.id] = table

    return base


# All computed types as defined in Field.is_computed()
COMPUTED_TYPES: list[FieldType] = [
    "formula",
    "rollup",
    "lookup",
    "multipleLookupValues",
    "createdTime",
    "lastModifiedTime",
    "lastModifiedBy",
    "createdBy",
    "count",
    "button",
    "autoNumber",
]

# A representative writable type
WRITABLE_TYPES: list[FieldType] = [
    "singleLineText",
    "number",
    "checkbox",
    "date",
    "email",
]


def _read_generated_model(output_folder: Path, language: str) -> str:
    """Read the generated model file content."""
    if language == "typescript":
        model_path = output_folder / "dynamic" / "models" / "testTable.ts"
    elif language == "javascript":
        model_path = output_folder / "dynamic" / "models" / "testTable.js"
    else:
        raise ValueError(f"Unknown language: {language}")
    return model_path.read_text()


class TestTypeScriptComputedFields:
    """TypeScript generator should emit getter-only for computed fields."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from src.generators.typescript import write_models

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "ts_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "typescript")

    def test_formula_field_is_getter(self, tmp_path: Path):
        """A formula field should be a getter, not a method."""
        content = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content
        assert "set myFormula(" not in content

    def test_writable_field_has_getter_and_setter(self, tmp_path: Path):
        """A singleLineText field should have both getter and setter."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "get myText()" in content
        assert "set myText(" in content

    def test_non_formula_computed_types_getter_only(self, tmp_path: Path):
        """Non-formula computed field types should generate getter-only."""
        non_formula_computed = [ft for ft in COMPUTED_TYPES if ft != "formula"]
        fields_spec = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(non_formula_computed)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(non_formula_computed):
            field = make_test_base([(f"Field {i}", f"fld{i:03d}", ft)]).tables[0].fields[0]
            camel_name = field.name_camel()
            assert f"get {camel_name}()" in content, f"Missing getter for computed type {ft}"
            assert f"set {camel_name}(" not in content, f"Unexpected setter for computed type {ft}"

    def test_mixed_table_correct_accessors(self, tmp_path: Path):
        """A table with both computed and writable fields should have correct accessors."""
        fields_spec = [
            ("My Formula", "fld001", "formula"),
            ("My Text", "fld002", "singleLineText"),
            ("Created", "fld003", "createdTime"),
            ("Rating", "fld004", "rating"),
        ]
        content = self._generate(fields_spec, tmp_path)

        # Formula: getter
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content
        # Non-formula computed: getter only
        assert "get created()" in content
        assert "set created(" not in content

        # Writable: both
        assert "get myText()" in content
        assert "set myText(" in content
        assert "get rating()" in content
        assert "set rating(" in content


class TestJavaScriptComputedFields:
    """JavaScript generator should emit getter-only for computed fields."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from src.generators.javascript import write_models

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "js_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "javascript")

    def test_formula_field_is_getter(self, tmp_path: Path):
        """A formula field should be a getter, not a method."""
        content = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content
        assert "set myFormula(" not in content

    def test_writable_field_has_getter_and_setter(self, tmp_path: Path):
        """A singleLineText field should have both getter and setter."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "get myText()" in content
        assert "set myText(" in content

    def test_non_formula_computed_types_getter_only(self, tmp_path: Path):
        """Non-formula computed field types should generate getter-only."""
        non_formula_computed = [ft for ft in COMPUTED_TYPES if ft != "formula"]
        fields_spec = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(non_formula_computed)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(non_formula_computed):
            field = make_test_base([(f"Field {i}", f"fld{i:03d}", ft)]).tables[0].fields[0]
            camel_name = field.name_camel()
            assert f"get {camel_name}()" in content, f"Missing getter for computed type {ft}"
            assert f"set {camel_name}(" not in content, f"Unexpected setter for computed type {ft}"


class TestPythonComputedFields:
    """Python generator should use readonly=True for computed fields."""

    def test_computed_field_has_readonly(self):
        """A createdTime field's ORM type should include readonly=True."""
        from src.generators.python import pyairtable_orm_type

        base = make_test_base([("Created", "fld001", "createdTime")])
        field = base.tables[0].fields[0]
        result = pyairtable_orm_type(field, base, Path("output"), "")
        assert "readonly=True" in result

    def test_writable_field_no_readonly(self):
        """A singleLineText field's ORM type should NOT include readonly=True."""
        from src.generators.python import pyairtable_orm_type

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        field = base.tables[0].fields[0]
        result = pyairtable_orm_type(field, base, Path("output"), "")
        assert "readonly=True" not in result


# region Formula Function Generation Tests


class TestTypeScriptFormulaFunctions:
    """TypeScript generator should emit getters for formula fields with transpilable formulas."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path, formula_map: dict[str, str] | None = None) -> str:
        from src.generators.typescript import write_models

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "ts_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "typescript")

    def test_formula_field_generates_getter(self, tmp_path: Path):
        """A formula field with a transpilable formula should generate a getter."""
        fields_spec = [
            ("My Number", "fld001", "number"),
            ("My Formula", "fld002", "formula"),
        ]
        formula_map = {"fld002": "COUNTA({fld001})"}
        content = self._generate(fields_spec, tmp_path, formula_map=formula_map)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content
        assert "F.COUNTA(this.myNumber)" in content
        assert "evaluateFormulasAtRuntime" in content
        assert "AirtableRuntime as F" in content

    def test_formula_field_without_formula_is_still_getter(self, tmp_path: Path):
        """A formula field without a transpilable formula is still a getter."""
        fields_spec = [("My Formula", "fld001", "formula")]
        content = self._generate(fields_spec, tmp_path)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content

    def test_rollup_still_generates_getter(self, tmp_path: Path):
        """Rollup fields should still generate getter-only, not functions."""
        fields_spec = [("My Rollup", "fld001", "rollup")]
        content = self._generate(fields_spec, tmp_path)
        assert "get myRollup()" in content
        assert "myRollup(recalculate" not in content

    def test_no_runtime_import_without_formulas(self, tmp_path: Path):
        """Runtime import should only appear when there are formula fields."""
        fields_spec = [("My Text", "fld001", "singleLineText")]
        content = self._generate(fields_spec, tmp_path)
        assert "AirtableRuntime" not in content and "F." not in content

    def test_formula_references_another_formula(self, tmp_path: Path):
        """A formula referencing another formula field should access it as a property."""
        fields_spec = [
            ("Base Value", "fld001", "number"),
            ("Formula A", "fld002", "formula"),
            ("Formula B", "fld003", "formula"),
        ]
        formula_map = {
            "fld002": "{fld001} + 1",
            "fld003": "{fld002} * 2",
        }
        content = self._generate(fields_spec, tmp_path, formula_map=formula_map)
        # Formula B should reference Formula A as a property
        assert "this.formulaA" in content
        assert "this.formulaA(recalculate)" not in content


class TestJavaScriptFormulaFunctions:
    """JavaScript generator should emit getters for formula fields with transpilable formulas."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path, formula_map: dict[str, str] | None = None) -> str:
        from src.generators.javascript import write_models

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "js_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "javascript")

    def test_formula_field_generates_getter(self, tmp_path: Path):
        """A formula field with a transpilable formula should generate a getter."""
        fields_spec = [
            ("My Number", "fld001", "number"),
            ("My Formula", "fld002", "formula"),
        ]
        formula_map = {"fld002": "COUNTA({fld001})"}
        content = self._generate(fields_spec, tmp_path, formula_map=formula_map)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content
        assert "F.COUNTA(this.myNumber)" in content
        assert "evaluateFormulasAtRuntime" in content

    def test_formula_field_without_formula_is_still_getter(self, tmp_path: Path):
        """A formula field without a transpilable formula is still a getter."""
        fields_spec = [("My Formula", "fld001", "formula")]
        content = self._generate(fields_spec, tmp_path)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content


class TestPythonFormulaFunctions:
    """Python generator should emit hidden ORM descriptors + properties for formula fields."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path, formula_map: dict[str, str] | None = None) -> str:
        from src.generators.python import write_models

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "py_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, runtime=True, package_prefix="")
        model_path = output_folder / "dynamic" / "models" / "test_table.py"
        return model_path.read_text()

    def test_formula_field_generates_property(self, tmp_path: Path):
        """A formula field with a transpilable formula should generate a property."""
        fields_spec = [
            ("My Number", "fld001", "number"),
            ("My Formula", "fld002", "formula"),
        ]
        formula_map = {"fld002": "COUNTA({fld001})"}
        content = self._generate(fields_spec, tmp_path, formula_map=formula_map)
        # Should have hidden ORM descriptor
        assert "_orm_my_formula:" in content
        # Should have @property
        assert "@property" in content
        assert "def my_formula(self)" in content
        assert "recalculate" not in content
        assert "evaluate_formulas_at_runtime" in content
        assert "F.COUNTA(self.my_number)" in content
        assert "AirtableRuntime as F" in content

    def test_formula_field_without_formula_is_still_property(self, tmp_path: Path):
        """A formula field without a transpilable formula is still a property with hidden ORM descriptor."""
        fields_spec = [("My Formula", "fld001", "formula")]
        content = self._generate(fields_spec, tmp_path)
        assert "_orm_my_formula:" in content
        assert "@property" in content
        assert "def my_formula(self)" in content
        assert "recalculate" not in content


# endregion


# =============================================================================
# Swift generator (F3)
# =============================================================================


class TestSwiftGeneratorOutput:
    """Swift generator (F3 — dict-only path) content assertions.

    Verifies the generator emits the expected file structure and key code
    snippets without shelling out to `swift build` (which would require Swift
    on PATH in every test env). Compilation is separately verified by
    ``tests/swift_static/`` + the integration tests in ``myairtable-tests``.
    """

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> Path:
        """Generate Swift code to a fresh tmp dir and return the output folder."""
        from src.generators.swift import write_field_types, write_main, write_options, write_tables
        from src.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        write_field_types(base, output_folder)
        write_tables(base, output_folder)
        write_main(base, output_folder)
        return output_folder

    def test_field_types_emit_dual_id_and_name_constants(self, tmp_path: Path):
        """Every field must get both a `{field}Id` and `{field}Name` static constant."""
        fields_spec = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)

        fields_file = out / "dynamic" / "types" / "TestTableFields.swift"
        content = fields_file.read_text()

        assert "public enum TestTableFields" in content
        assert 'public static let primaryKeyId: String = "fld001"' in content
        assert 'public static let primaryKeyName: String = "Primary Key"' in content

    def test_field_types_emit_name_to_id_and_id_to_name_dictionaries(self, tmp_path: Path):
        """The nameToId / idToName maps enable dual-access lookup at runtime."""
        fields_spec = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.swift").read_text()

        assert "public static let nameToId: [String: String]" in content
        assert "public static let idToName: [String: String]" in content
        assert '"Primary Key": "fld001"' in content
        assert '"fld001": "Primary Key"' in content
        assert "public static func idByName(" in content
        assert "public static func nameById(" in content

    def test_field_types_all_ids_contains_every_field(self, tmp_path: Path):
        """allIds: [String] should list every field ID in schema order."""
        fields_spec = [
            ("A", "fld001", "singleLineText"),
            ("B", "fld002", "number"),
            ("C", "fld003", "checkbox"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.swift").read_text()

        assert 'public static let allIds: [String] = ["fld001", "fld002", "fld003"]' in content

    def test_writable_fields_exclude_computed_from_create_enum(self, tmp_path: Path):
        """Create{Table}Fields enum omits computed fields (formula, createdTime, etc.)."""
        fields_spec = [
            ("My Text", "fld001", "singleLineText"),
            ("My Formula", "fld002", "formula"),
            ("Created", "fld003", "createdTime"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.swift").read_text()

        assert "public enum CreateTestTableFields" in content
        # Writable field appears in Create enum
        create_block = content.split("public enum CreateTestTableFields")[1]
        assert "myTextId" in create_block
        # Computed fields are NOT in the Create enum
        assert "myFormulaId" not in create_block
        assert "createdId" not in create_block

    def test_tables_struct_exposes_dict_accessor(self, tmp_path: Path):
        """Each table gets a {Table}Table struct with a `.dict: DictTable` accessor."""
        fields_spec = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.swift").read_text()

        assert "public struct TestTableTable: Sendable" in content
        assert 'public static let tableId: String = "tblTEST123"' in content
        assert "public let dict: DictTable" in content
        assert "public init(client: AirtableClient)" in content
        assert "nameToId: TestTableFields.nameToId" in content

    def test_main_airtable_actor_exposes_per_table_accessors(self, tmp_path: Path):
        """Airtable.swift should expose each table as a lowerCamelCase property."""
        fields_spec = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "Airtable.swift").read_text()

        assert "public struct Airtable: Sendable" in content
        assert "public let testTable: TestTableTable" in content
        # Dual init: baseId+apiKey with default baseId, plus client injection.
        assert "public init(baseId: String" in content
        assert "public init(client: AirtableClient)" in content
        # Default baseId is embedded so users can construct with just an API key.
        assert 'baseId: String = "appTEST123"' in content

    def test_no_package_swift_is_emitted(self, tmp_path: Path):
        """User decision #5: generator does NOT emit Package.swift."""
        fields_spec = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        assert not (out / "Package.swift").exists()


class TestSwiftComputedFields:
    """Swift generator should emit computed fields as `let` (decode-only) and
    writable fields as `var`. Also verifies manual `Codable` conformance,
    `@Observable` annotation, CodingKeys mapping to field IDs, and
    Create{Table}Model excludes computed fields. This is the Swift analog
    of TestTypeScriptComputedFields (and exercises the F4 generator).
    """

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from src.generators.swift import write_models
        from src.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        map_types(base)
        write_models(base, output_folder)
        model_path = output_folder / "dynamic" / "models" / "TestTableModel.swift"
        return model_path.read_text()

    def test_model_class_has_observable_attribute(self, tmp_path: Path):
        """The generated class must be annotated with @Observable."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "@Observable" in content
        assert "public final class TestTableModel: AirtableModel" in content

    def test_computed_fields_are_let(self, tmp_path: Path):
        """Each computed-type field should emit as `public let <prop>: T?`."""
        non_formula_computed = [ft for ft in COMPUTED_TYPES if ft != "formula"]
        fields_spec = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(non_formula_computed)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(non_formula_computed):
            # Use make_test_base's camel-naming so we get the right property string.
            field = make_test_base([(f"Field {i}", f"fld{i:03d}", ft)]).tables[0].fields[0]
            camel = field.name_camel()
            assert f"public let {camel}:" in content, f"Missing `let` for {ft}"
            assert f"public var {camel}:" not in content, f"Unexpected `var` for computed {ft}"

    def test_writable_fields_are_var(self, tmp_path: Path):
        """Writable field types should emit as `public var <prop>: T?`."""
        fields_spec = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(WRITABLE_TYPES)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(WRITABLE_TYPES):
            field = make_test_base([(f"Field {i}", f"fld{i:03d}", ft)]).tables[0].fields[0]
            camel = field.name_camel()
            assert f"public var {camel}:" in content, f"Missing `var` for {ft}"
            assert f"public let {camel}:" not in content, f"Unexpected `let` for writable {ft}"

    def test_mixed_table_respects_computed_vs_writable(self, tmp_path: Path):
        """A table with both kinds should emit each at the correct mutability."""
        content = self._generate(
            [
                ("My Formula", "fld001", "formula"),
                ("My Text", "fld002", "singleLineText"),
                ("Created", "fld003", "createdTime"),
                ("Rating", "fld004", "rating"),
            ],
            tmp_path,
        )
        # Computed
        assert "public let myFormula:" in content
        assert "public let created:" in content
        # Writable
        assert "public var myText:" in content
        assert "public var rating:" in content
        # No crossed wires
        assert "public var myFormula:" not in content
        assert "public let myText:" not in content

    def test_coding_keys_raw_values_are_field_ids(self, tmp_path: Path):
        """FieldsCodingKeys enum maps Swift property → Airtable field ID."""
        content = self._generate([("My Text", "fld_ABC_123", "singleLineText")], tmp_path)
        assert "private enum FieldsCodingKeys: String, CodingKey" in content
        assert 'case myText = "fld_ABC_123"' in content

    def test_manual_codable_conformance_present(self, tmp_path: Path):
        """Every model emits manual init(from:) + encode(to:) (not synthesized)."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "public required init(from decoder: any Decoder) throws" in content
        assert "public func encode(to encoder: any Encoder) throws" in content

    def test_snapshot_and_dirty_tracking_present(self, tmp_path: Path):
        """Explicit snapshot-dict dirty tracking, NOT @Observable-based."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "@ObservationIgnored" in content
        assert "private var _snapshot: [String: AirtableJSONValue]" in content
        assert "public func takeSnapshot()" in content
        assert "public func dirtyFields() -> [String: AirtableJSONValue]" in content

    def test_create_model_excludes_computed_fields(self, tmp_path: Path):
        """Create{Table}Model struct omits computed fields and has Encodable conformance."""
        content = self._generate(
            [
                ("My Text", "fld001", "singleLineText"),
                ("My Formula", "fld002", "formula"),
                ("Created", "fld003", "createdTime"),
            ],
            tmp_path,
        )
        assert "public struct CreateTestTableModel: Encodable, Sendable" in content
        # Find the CreateTestTableModel block and assert writable-only shape.
        create_block = content.split("public struct CreateTestTableModel")[1]
        assert "public var myText:" in create_block
        assert "myFormula" not in create_block  # computed field excluded
        assert "created" not in create_block  # computed field excluded
        # CodingKeys should map to field IDs, not names.
        assert 'case myText = "fld001"' in create_block


class TestSwiftFormulaFunctions:
    """Formula fields should still appear on the model as `let` (not getter
    methods) in F4 — runtime evaluation methods land in F8. This verifies
    the F4 shape is stable before F8 adds on to it."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from src.generators.swift import write_models
        from src.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        map_types(base)
        write_models(base, output_folder)
        return (output_folder / "dynamic" / "models" / "TestTableModel.swift").read_text()

    def test_formula_field_is_let_property(self, tmp_path: Path):
        """A formula field emits as `let myFormula: ...?` (decode-only)."""
        content = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert "public let myFormula:" in content
        # No setter, no method.
        assert "public var myFormula:" not in content
        assert "func myFormula(" not in content

    def test_formula_field_included_in_fields_coding_keys(self, tmp_path: Path):
        """Formula fields must be in FieldsCodingKeys to be decoded."""
        content = self._generate([("My Formula", "fld_formula", "formula")], tmp_path)
        assert 'case myFormula = "fld_formula"' in content


class TestSwiftOptionsGenerator:
    """Swift select-option enum generation."""

    def _generate_with_options(self, tmp_path: Path) -> str:
        """Build a table with a singleSelect field and return its options file content."""
        from src.generators.swift import write_options
        from src.utils.type_mapper import map_types

        base = make_test_base([("Status", "fld001", "singleSelect")])
        # Inject choices into the field's options (make_test_base gives us empty choices).
        field = base.tables[0].fields[0]
        assert field.options is not None  # make_test_base always populates Options
        field.options.choices = [
            Choice.model_construct(id="sel1", name="Open"),
            Choice.model_construct(id="sel2", name="In Progress"),
            Choice.model_construct(id="sel3", name="Closed"),
        ]
        # Invalidate the cached select options so it re-reads from options.choices.
        assert field.__pydantic_private__ is not None
        field.__pydantic_private__["_select_options_cache"] = None

        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        return (output_folder / "dynamic" / "options" / "TestTableOptions.swift").read_text()

    def test_options_enum_has_codable_sendable_caseiterable(self, tmp_path: Path):
        """Each options enum conforms to Codable + Sendable + CaseIterable."""
        content = self._generate_with_options(tmp_path)
        # Enum name is derived from field; for "Status" on "Test Table" it is
        # produced by field.options_name(). We just assert the conformances.
        assert ": String, Codable, Sendable, CaseIterable" in content

    def test_options_enum_cases_are_lower_camel_case(self, tmp_path: Path):
        """Choices with spaces should produce lowerCamelCase cases. Swift reserved
        words (like `open`) are backtick-escaped automatically."""
        content = self._generate_with_options(tmp_path)
        assert 'case `open` = "Open"' in content  # `open` is a Swift keyword
        assert 'case inProgress = "In Progress"' in content
        assert 'case closed = "Closed"' in content
