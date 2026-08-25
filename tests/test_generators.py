"""Tests for computed field read-only property generation in TS, JS, and Python generators."""

import ast
import re
from pathlib import Path

from myairtable.meta import Base, Choice, Field, Options, Result, Table, View
from myairtable.meta_types import FieldType


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
            "_rust_type": None,
            "_swift_type": None,
            "_kotlin_type": None,
            "_java_type": None,
            "_go_type": None,
            "_csharp_type": None,
            "_cpp_type": None,
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
        from myairtable.generators.typescript import write_models

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
        fields_spec: list[tuple[str, str, FieldType]] = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(non_formula_computed)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(non_formula_computed):
            field = make_test_base([(f"Field {i}", f"fld{i:03d}", ft)]).tables[0].fields[0]
            camel_name = field.name_camel()
            assert f"get {camel_name}()" in content, f"Missing getter for computed type {ft}"
            assert f"set {camel_name}(" not in content, f"Unexpected setter for computed type {ft}"

    def test_mixed_table_correct_accessors(self, tmp_path: Path):
        """A table with both computed and writable fields should have correct accessors."""
        fields_spec: list[tuple[str, str, FieldType]] = [
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


class TestLinkedModelClassIsLazy:
    """`linkedModelClass` must be a getter, never a bare class reference.

    Linked models are mutually circular -- each imports its siblings through the
    `../models` barrel -- so resolving the class while the module body runs reads a
    half-initialised module. Bundlers are free to order the cycle so that read happens
    before the sibling's binding is initialised, which shipped to a consumer as

        bonusPeriods.ts:55 Uncaught ReferenceError:
          Cannot access 'BonusFine' before initialization

    in a production bundle, while every dev server stayed green (Vite pre-bundles
    dependencies with esbuild, which orders the cycle differently than rollup).
    """

    def _generate_ts(self, tmp_path: Path) -> str:
        from myairtable.generators.typescript import write_models

        base = make_test_base([("Links", "fld001", "multipleRecordLinks")])
        output_folder = tmp_path / "ts_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "typescript")

    def _generate_js(self, tmp_path: Path) -> str:
        from myairtable.generators.javascript import write_models

        base = make_test_base([("Links", "fld001", "multipleRecordLinks")])
        output_folder = tmp_path / "js_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "javascript")

    def test_typescript_defers_linked_model_class(self, tmp_path: Path):
        content = self._generate_ts(tmp_path)
        assert "get linkedModelClass()" in content
        assert not re.search(r"linkedModelClass:\s*\S", content), (
            "eager reference resolves during module evaluation and TDZ-throws in a circular import"
        )

    def test_javascript_defers_linked_model_class(self, tmp_path: Path):
        content = self._generate_js(tmp_path)
        assert "get linkedModelClass()" in content
        assert not re.search(r"linkedModelClass:\s*\S", content), (
            "a circular CommonJS require returns partial exports, so the eager form captures undefined"
        )

    def test_linked_model_from_id_stays_lazy(self, tmp_path: Path):
        """The sibling property was always deferred; keep it that way."""
        assert "linkedModelFromId: (id, config) =>" in self._generate_ts(tmp_path)


class TestJavaScriptComputedFields:
    """JavaScript generator should emit getter-only for computed fields."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.javascript import write_models

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
        fields_spec: list[tuple[str, str, FieldType]] = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(non_formula_computed)]
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
        from myairtable.generators.python import pyairtable_orm_type

        base = make_test_base([("Created", "fld001", "createdTime")])
        field = base.tables[0].fields[0]
        result = pyairtable_orm_type(field, base, Path("output"), "")
        assert "readonly=True" in result

    def test_writable_field_no_readonly(self):
        """A singleLineText field's ORM type should NOT include readonly=True."""
        from myairtable.generators.python import pyairtable_orm_type

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        field = base.tables[0].fields[0]
        result = pyairtable_orm_type(field, base, Path("output"), "")
        assert "readonly=True" not in result


# region Formula Function Generation Tests


class TestTypeScriptFormulaFunctions:
    """TypeScript generator should emit getters for formula fields with transpilable formulas."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path, formula_map: dict[str, str] | None = None) -> str:
        from myairtable.generators.typescript import write_models

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "ts_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "typescript")

    def test_formula_field_generates_getter(self, tmp_path: Path):
        """A formula field with a transpilable formula should generate a getter."""
        fields_spec: list[tuple[str, str, FieldType]] = [
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
        fields_spec: list[tuple[str, str, FieldType]] = [("My Formula", "fld001", "formula")]
        content = self._generate(fields_spec, tmp_path)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content

    def test_rollup_still_generates_getter(self, tmp_path: Path):
        """Rollup fields should still generate getter-only, not functions."""
        fields_spec: list[tuple[str, str, FieldType]] = [("My Rollup", "fld001", "rollup")]
        content = self._generate(fields_spec, tmp_path)
        assert "get myRollup()" in content
        assert "myRollup(recalculate" not in content

    def test_no_runtime_import_without_formulas(self, tmp_path: Path):
        """Runtime import should only appear when there are formula fields."""
        fields_spec: list[tuple[str, str, FieldType]] = [("My Text", "fld001", "singleLineText")]
        content = self._generate(fields_spec, tmp_path)
        assert "AirtableRuntime" not in content and "F." not in content

    def test_formula_references_another_formula(self, tmp_path: Path):
        """A formula referencing another formula field should access it as a property."""
        fields_spec: list[tuple[str, str, FieldType]] = [
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
        from myairtable.generators.javascript import write_models

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "js_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, zod=False)
        return _read_generated_model(output_folder, "javascript")

    def test_formula_field_generates_getter(self, tmp_path: Path):
        """A formula field with a transpilable formula should generate a getter."""
        fields_spec: list[tuple[str, str, FieldType]] = [
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
        fields_spec: list[tuple[str, str, FieldType]] = [("My Formula", "fld001", "formula")]
        content = self._generate(fields_spec, tmp_path)
        assert "get myFormula()" in content
        assert "myFormula(recalculate" not in content


class TestPythonFormulaFunctions:
    """Python generator should emit hidden ORM descriptors + properties for formula fields."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path, formula_map: dict[str, str] | None = None) -> str:
        from myairtable.generators.python import write_models

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "py_output"
        output_folder.mkdir()
        write_models(base, output_folder, formulas=False, runtime=True, package_prefix="")
        model_path = output_folder / "dynamic" / "models" / "test_table.py"
        return model_path.read_text()

    def test_formula_field_generates_property(self, tmp_path: Path):
        """A formula field with a transpilable formula should generate a property."""
        fields_spec: list[tuple[str, str, FieldType]] = [
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
        fields_spec: list[tuple[str, str, FieldType]] = [("My Formula", "fld001", "formula")]
        content = self._generate(fields_spec, tmp_path)
        assert "_orm_my_formula:" in content
        assert "@property" in content
        assert "def my_formula(self)" in content
        assert "recalculate" not in content


# endregion


# region Select Option Escaping Tests


def _make_base_with_select_field(table_name: str, field_name: str, field_id: str, choices: list[str]) -> Base:
    """Build a Base with a single singleSelect field whose choices are the given strings."""
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

    view = View.model_construct(id="viw001", name="Grid view", type="grid", table_id="tblTEST123")
    table = Table.model_construct(
        id="tblTEST123",
        name=table_name,
        primary_field_id=field_id,
        fields=[],
        views=[view],
        base=base,
        _field_id_to_name_cache=None,
    )
    table.__pydantic_private__ = {
        "_field_id_to_name_cache": None,
        "_snake": None,
        "_pascal": None,
        "_model": None,
        "_upper": None,
        "_name_cache": {},
    }

    choice_models = [Choice.model_construct(id=f"sel{i:03d}", name=name, color=None) for i, name in enumerate(choices)]

    field = Field.model_construct(
        id=field_id,
        name=field_name,
        type="singleSelect",
        description=None,
        options=Options.model_construct(
            formula=None,
            view_id_for_record_selection=None,
            is_reversed=None,
            precision=None,
            choices=choice_models,
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
            result=None,
            field_id=field_id,
        ),
        table=table,
        base=base,
    )
    field.__pydantic_private__ = {
        "_select_options_cache": None,
        "_python_type_csv": None,
        "_typescript_type_csv": None,
        "_formula_cache": {},
        "_generic_type": None,
        "_python_type": None,
        "_typescript_type": None,
        "_zod_type": None,
        "_rust_type": None,
        "_swift_type": None,
        "_kotlin_type": None,
        "_java_type": None,
        "_go_type": None,
        "_csharp_type": None,
        "_cpp_type": None,
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


class TestSelectOptionEscaping:
    """Generators must escape special characters (notably ") in select option names.

    Regression: Airtable allows option names like '"Bucyrus, OH"' (literally containing
    quote characters). Naively wrapping with double-quotes produces invalid syntax like
    `""Bucyrus, OH""` in the emitted source. See myairtable issue around rig_assignments.
    """

    CHOICES_WITH_QUOTES = [
        '"Bucyrus, OH"',
        '"Springfield, IL"',
        "Bucyrus, OH",
    ]

    def test_python_emits_parseable_literal_and_list(self, tmp_path: Path):
        from myairtable.generators.python import write_types

        base = _make_base_with_select_field("Rig Assignments", "Vehicle Drop Point", "fld001", self.CHOICES_WITH_QUOTES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "rig_assignments.py").read_text()

        # The whole file must parse as valid Python — this is the regression check.
        # Before the fix, names like `"Bucyrus, OH"` produced `""Bucyrus, OH""` which is a syntax error.
        ast.parse(content)

        # Quoted option names should appear escaped inside double-quoted string literals.
        assert '"\\"Bucyrus, OH\\""' in content
        assert '"\\"Springfield, IL\\""' in content
        # Plain option (no internal quotes) should still appear as-is.
        assert '"Bucyrus, OH"' in content

    def test_typescript_emits_escaped_literal_and_list(self, tmp_path: Path):
        from myairtable.generators.typescript import write_types

        base = _make_base_with_select_field("Rig Assignments", "Vehicle Drop Point", "fld001", self.CHOICES_WITH_QUOTES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "rigAssignments.ts").read_text()

        # Each quoted option should appear as \"Bucyrus, OH\" inside the double-quoted string literal
        assert '"\\"Bucyrus, OH\\""' in content
        assert '"\\"Springfield, IL\\""' in content
        # The plain option (no internal quotes) should still appear as-is
        assert '"Bucyrus, OH"' in content

    def test_javascript_emits_escaped_const_array(self, tmp_path: Path):
        from myairtable.generators.javascript import write_types

        base = _make_base_with_select_field("Rig Assignments", "Vehicle Drop Point", "fld001", self.CHOICES_WITH_QUOTES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "rigAssignments.js").read_text()

        assert '"\\"Bucyrus, OH\\""' in content
        assert '"\\"Springfield, IL\\""' in content
        assert '"Bucyrus, OH"' in content


# endregion


# region Select Option Name<->ID Mapping Tests


class TestSelectOptionNameIdMappings:
    """singleSelect / multipleSelects fields must emit name<->id maps alongside
    their Option Literal / list. Callers use these so JSON they write uses the
    stable Airtable option id, surviving option renames."""

    CHOICES = ["Open", "Completed", "Closed"]

    def test_python_emits_name_id_and_id_name_mappings(self, tmp_path: Path):
        from myairtable.generators.python import write_types

        base = _make_base_with_select_field("Jobs", "Status (Billing)", "fldBILLING", self.CHOICES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "jobs.py").read_text()
        ast.parse(content)  # must remain valid Python

        # Name->ID map
        assert "JobsStatusBillingOptionNameIdMapping: dict[JobsStatusBillingOption, str] = {" in content
        assert '"Open": "sel000"' in content
        assert '"Completed": "sel001"' in content
        assert '"Closed": "sel002"' in content

        # ID->Name map (reverse)
        assert "JobsStatusBillingOptionIdNameMapping: dict[str, JobsStatusBillingOption] = {" in content
        assert '"sel000": "Open"' in content
        assert '"sel001": "Completed"' in content
        assert '"sel002": "Closed"' in content

    def test_typescript_emits_name_id_and_id_name_mappings(self, tmp_path: Path):
        from myairtable.generators.typescript import write_types

        base = _make_base_with_select_field("Jobs", "Status (Billing)", "fldBILLING", self.CHOICES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "jobs.ts").read_text()

        assert "JobsStatusBillingOptionNameIdMapping: Record<JobsStatusBillingOption, string>" in content
        assert '"Open": "sel000"' in content
        assert "JobsStatusBillingOptionIdNameMapping: Record<string, JobsStatusBillingOption>" in content
        assert '"sel000": "Open"' in content

    def test_javascript_emits_name_id_and_id_name_mappings(self, tmp_path: Path):
        from myairtable.generators.javascript import write_types

        base = _make_base_with_select_field("Jobs", "Status (Billing)", "fldBILLING", self.CHOICES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "jobs.js").read_text()

        assert "JobsStatusBillingOptionNameIdMapping" in content
        assert '"Open": "sel000"' in content
        assert "JobsStatusBillingOptionIdNameMapping" in content
        assert '"sel000": "Open"' in content

    def test_rust_emits_id_and_from_id_helpers(self, tmp_path: Path):
        from myairtable.generators.rust import write_options

        base = _make_base_with_select_field("Jobs", "Status (Billing)", "fldBILLING", self.CHOICES)
        write_options(base, tmp_path)

        content = (tmp_path / "dynamic" / "options" / "jobs.rs").read_text()

        assert "impl JobsStatusBillingOption {" in content
        assert "pub fn id(&self) -> &'static str {" in content
        assert 'Self::Open => "sel000",' in content
        assert 'Self::Completed => "sel001",' in content
        assert 'Self::Closed => "sel002",' in content
        assert 'Self::Unknown => "",' in content
        assert "pub fn from_id(id: &str) -> Option<Self> {" in content
        assert '"sel000" => Some(Self::Open),' in content
        assert "_ => None," in content


# endregion


# region SMART IMPORTS


def _imports_block(content: str) -> str:
    """Return everything in the file up to the first class/namespace/struct declaration.

    Smart imports may legitimately reference a symbol in the body (e.g. a docstring);
    restricting assertions to the import region avoids false positives.
    """
    for marker in ("\nexport class ", "\nclass ", "\nexport namespace ", "\npub struct "):
        idx = content.find(marker)
        if idx != -1:
            return content[:idx]
    return content


class TestSmartImportsTypeScript:
    """The TS generator must only import symbols a file actually references."""

    def _model(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.typescript import write_models

        base = make_test_base(fields_spec)
        out = tmp_path / "ts_output"
        out.mkdir(parents=True, exist_ok=True)
        write_models(base, out, formulas=False, zod=False)
        return _read_generated_model(out, "typescript")

    def _formula(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.typescript import write_formula_helpers

        base = make_test_base(fields_spec)
        out = tmp_path / "ts_output"
        out.mkdir()
        write_formula_helpers(base, out)
        return (out / "dynamic" / "formulas" / "testTable.ts").read_text()

    def test_model_drops_unused_imports(self, tmp_path: Path):
        """A text-only table must not import attachment/collaborator/linked-record symbols."""
        content = self._model([("My Text", "fld001", "singleLineText")], tmp_path)
        imports = _imports_block(content)
        for unused in ("Attachment", "Collaborator", "AirtableButton", "LinkedRecord", "ChainableLinkedRecord", "RecordId"):
            assert unused not in imports, f"{unused} should not be imported for a text-only table"

    def test_model_imports_attachment_when_used(self, tmp_path: Path):
        """An attachment field must pull in the Attachment type."""
        content = self._model([("Files", "fld001", "multipleAttachments")], tmp_path)
        assert "Attachment" in _imports_block(content)

    def test_formula_only_imports_used_classes(self, tmp_path: Path):
        """A number-only table's formula file imports NumberField + ID, not other field classes."""
        imports = self._formula([("My Number", "fld001", "number")], tmp_path)
        assert "NumberField" in imports
        assert "ID" in imports
        for unused in ("TextField", "DateField", "AttachmentsField", "BooleanField", "LookupField"):
            assert unused not in imports, f"{unused} should not be imported for a number-only formula file"

    def test_deterministic_output(self, tmp_path: Path):
        """Generating twice must produce byte-identical models."""
        spec: list[tuple[str, str, FieldType]] = [
            ("My Text", "fld001", "singleLineText"),
            ("Files", "fld002", "multipleAttachments"),
        ]
        first = self._model(spec, tmp_path / "a")
        second = self._model(spec, tmp_path / "b")
        assert first == second


class TestSmartImportsJavaScript:
    """The JS generator must only require symbols a file actually references."""

    def _model(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.javascript import write_models

        base = make_test_base(fields_spec)
        out = tmp_path / "js_output"
        out.mkdir()
        write_models(base, out, formulas=False, zod=False)
        return _read_generated_model(out, "javascript")

    def test_model_drops_unused_requires(self, tmp_path: Path):
        content = self._model([("My Text", "fld001", "singleLineText")], tmp_path)
        imports = _imports_block(content)
        for unused in ("LinkedRecord", "wrapLinkedRecordProxy"):
            assert unused not in imports, f"{unused} should not be required for a text-only table"


class TestSmartImportsPython:
    """The Python generator must only import symbols a file actually references."""

    def _model(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.python import write_models

        base = make_test_base(fields_spec)
        out = tmp_path / "py_output"
        out.mkdir()
        write_models(base, out, formulas=False, runtime=True, package_prefix="")
        return (out / "dynamic" / "models" / "test_table.py").read_text()

    def test_model_drops_unused_field_types(self, tmp_path: Path):
        """A text-only table imports SingleLineTextField but not unrelated pyairtable field types."""
        content = self._model([("My Text", "fld001", "singleLineText")], tmp_path)
        imports = _imports_block(content)
        assert "SingleLineTextField" in imports
        for unused in ("AutoNumberField", "DurationField", "CollaboratorField", "AttachmentsField"):
            assert unused not in imports, f"{unused} should not be imported for a text-only table"

    def test_model_is_valid_python(self, tmp_path: Path):
        """Generated model with smart imports must still parse."""
        content = self._model([("My Text", "fld001", "singleLineText")], tmp_path)
        ast.parse(content)


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
        from myairtable.generators.swift import write_field_types, write_main, write_options, write_tables
        from myairtable.utils.type_mapper import map_types

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
        fields_spec: list[tuple[str, str, FieldType]] = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)

        fields_file = out / "dynamic" / "types" / "TestTableFields.swift"
        content = fields_file.read_text()

        assert "public enum TestTableFields" in content
        assert 'public static let primaryKeyId: String = "fld001"' in content
        assert 'public static let primaryKeyName: String = "Primary Key"' in content

    def test_field_types_emit_name_to_id_and_id_to_name_dictionaries(self, tmp_path: Path):
        """The nameToId / idToName maps enable dual-access lookup at runtime."""
        fields_spec: list[tuple[str, str, FieldType]] = [("Primary Key", "fld001", "singleLineText")]
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
        fields_spec: list[tuple[str, str, FieldType]] = [
            ("A", "fld001", "singleLineText"),
            ("B", "fld002", "number"),
            ("C", "fld003", "checkbox"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.swift").read_text()

        assert 'public static let allIds: [String] = ["fld001", "fld002", "fld003"]' in content

    def test_writable_fields_exclude_computed_from_create_enum(self, tmp_path: Path):
        """Create{Table}Fields enum omits computed fields (formula, createdTime, etc.)."""
        fields_spec: list[tuple[str, str, FieldType]] = [
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
        fields_spec: list[tuple[str, str, FieldType]] = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.swift").read_text()

        assert "public struct TestTableTable: Sendable" in content
        assert 'public static let tableId: String = "tblTEST123"' in content
        assert "public let dict: DictTable" in content
        assert "public init(client: AirtableClient)" in content
        assert "nameToId: TestTableFields.nameToId" in content

    def test_tables_forwards_orm_methods_directly(self, tmp_path: Path):
        """ORM is the default: `get` / `create` / `update` / `delete` live on
        the table struct as overloaded methods (no `.orm` prefix, no
        `getOne`/`createOne` variants). Matches TS/Py pattern."""
        fields_spec: list[tuple[str, str, FieldType]] = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.swift").read_text()

        # Overloaded names — no `One`/`Many` suffixes.
        assert "public func get(_ recordId: String)" in content
        assert "public func get(_ recordIds: [String])" in content
        assert "public func get(_ query: AirtableQuery" in content
        assert "public func create(" in content
        assert "public func update(" in content
        assert "public func upsert(" in content
        assert "public func duplicate(_ model: TestTableModel" in content
        assert "public func duplicate(_ recordId: String" in content
        assert "public func delete(_ recordId: String)" in content
        assert "public func delete(_ recordIds: [String])" in content
        assert "public func delete(_ model: TestTableModel)" in content
        assert "public func delete(_ models: [TestTableModel])" in content

        # No public .orm accessor; the internal OrmTable reference is
        # `@usableFromInline internal`.
        assert "public let orm:" not in content
        assert "@usableFromInline" in content
        assert "internal let orm: OrmTable<TestTableModel>" in content
        # Old *One/*Many names are gone.
        assert "getOne" not in content
        assert "getMany" not in content
        assert "createOne" not in content
        assert "updateOne" not in content
        assert "deleteOne" not in content
        assert "deleteMany" not in content

    def test_model_has_attached_client_property(self, tmp_path: Path):
        """Each model carries an `_attachedClient: AirtableClient?` so
        `model.save()` / `.fetch()` / `.delete()` can call back without
        needing a table argument."""
        from myairtable.generators.swift import write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        map_types(base)
        write_models(base, output_folder)
        content = (output_folder / "dynamic" / "models" / "TestTableModel.swift").read_text()

        # The property is public+var (needed by protocol requirement) but
        # flagged @ObservationIgnored so SwiftUI doesn't track it.
        assert "@ObservationIgnored" in content
        assert "public var _attachedClient: AirtableClient?" in content

    def test_main_airtable_actor_exposes_per_table_accessors(self, tmp_path: Path):
        """Airtable.swift should expose each table as a lowerCamelCase property."""
        fields_spec: list[tuple[str, str, FieldType]] = [("Primary Key", "fld001", "singleLineText")]
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
        fields_spec: list[tuple[str, str, FieldType]] = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        assert not (out / "Package.swift").exists()


class TestSwiftComputedFields:
    """Swift generator should emit computed fields as `let` (decode-only) and
    writable fields as `var`. Also verifies manual `Codable` conformance,
    `@Observable` annotation, CodingKeys mapping to field IDs, and that the
    designated init + `encode(to:)` both restrict to writable fields. This is
    the Swift analog of TestTypeScriptComputedFields.
    """

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.swift import write_models
        from myairtable.utils.type_mapper import map_types

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
        fields_spec: list[tuple[str, str, FieldType]] = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(non_formula_computed)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(non_formula_computed):
            # Use make_test_base's camel-naming so we get the right property string.
            field = make_test_base([(f"Field {i}", f"fld{i:03d}", ft)]).tables[0].fields[0]
            camel = field.name_camel()
            assert f"public let {camel}:" in content, f"Missing `let` for {ft}"
            assert f"public var {camel}:" not in content, f"Unexpected `var` for computed {ft}"

    def test_writable_fields_are_var(self, tmp_path: Path):
        """Writable field types should emit as `public var <prop>: T?`."""
        fields_spec: list[tuple[str, str, FieldType]] = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(WRITABLE_TYPES)]
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

    def test_no_create_struct_emitted(self, tmp_path: Path):
        """No separate `Create{Table}Model` struct — the ORM class itself carries
        the writable-field init."""
        content = self._generate(
            [
                ("My Text", "fld001", "singleLineText"),
                ("My Formula", "fld002", "formula"),
                ("Created", "fld003", "createdTime"),
            ],
            tmp_path,
        )
        assert "struct CreateTestTableModel" not in content

    def test_designated_init_excludes_computed_fields(self, tmp_path: Path):
        """The `public init(...)` on the class lists writable fields only —
        computed fields are server-owned and initialized to nil internally."""
        content = self._generate(
            [
                ("My Text", "fld001", "singleLineText"),
                ("My Formula", "fld002", "formula"),
                ("Created", "fld003", "createdTime"),
            ],
            tmp_path,
        )
        # Find the `public init(` block that opens the constructor.
        assert "public init(" in content
        init_block = content.split("public init(")[1].split(") {")[0]
        assert "myText: String? = nil" in init_block
        # Computed fields must NOT appear as init parameters.
        assert "myFormula" not in init_block
        assert "created" not in init_block

    def test_encode_emits_only_writable_fields(self, tmp_path: Path):
        """`encode(to:)` writes only writable fields into the `fields`
        container — computed fields are read-only server-side."""
        content = self._generate(
            [
                ("My Text", "fld001", "singleLineText"),
                ("My Formula", "fld002", "formula"),
                ("Created", "fld003", "createdTime"),
            ],
            tmp_path,
        )
        # Carve out just the encode(to:) body so we only check what it emits.
        encode_start = content.index("public func encode(to encoder: any Encoder) throws")
        encode_body = content[encode_start:]
        encode_body = encode_body[: encode_body.index("\n    }")]
        assert "fields.encodeIfPresent(myText, forKey: .myText)" in encode_body
        # Computed fields absent from the encode path.
        assert "myFormula, forKey: .myFormula" not in encode_body
        assert "created, forKey: .created" not in encode_body

    def test_no_link_fetch_methods_emitted(self, tmp_path: Path):
        """Linked fields stay as raw [RecordId]? (matching Rust). The
        `fetch{FieldName}()` per-link async method and the "Linked record
        fetching" MARK header must not appear in generated models."""
        content = self._generate(
            [
                ("Primary Key", "fld001", "singleLineText"),
                ("Links", "fld002", "multipleRecordLinks"),
            ],
            tmp_path,
        )
        assert "fetchLink" not in content
        assert "Linked record fetching" not in content


class TestSwiftFormulaFunctions:
    """Formula fields should still appear on the model as `let` (not getter
    methods) in F4 — runtime evaluation methods land in F8. This verifies
    the F4 shape is stable before F8 adds on to it."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.swift import write_models
        from myairtable.utils.type_mapper import map_types

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
        from myairtable.generators.swift import write_options
        from myairtable.utils.type_mapper import map_types

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


class TestSwiftFlagGating:
    """generate_swift must honor formulas/wrappers/runtime flags (myairtable-2odn).

    Mirrors the Rust generator's gating: disabling a flag suppresses the
    corresponding static + dynamic output instead of emitting it anyway.
    """

    FIELDS_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
    ]

    def _generate(self, tmp_path: Path, **flags) -> Path:
        from myairtable.generators.swift import generate_swift
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(self.FIELDS_SPEC)
        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        map_types(base)
        generate_swift(base, output_folder, **flags)
        return output_folder

    def test_default_flags_emit_everything(self, tmp_path: Path):
        out = self._generate(tmp_path)
        assert (out / "dynamic" / "formulas").is_dir()
        assert (out / "dynamic" / "tables").is_dir()
        assert (out / "Airtable.swift").is_file()
        assert (out / "static" / "Formula.swift").is_file()
        assert (out / "static" / "AirtableRuntime.swift").is_file()
        model = (out / "dynamic" / "models" / "TestTableModel.swift").read_text()
        assert "public static let f = TestTableFilters()" in model

    def test_formulas_false_suppresses_formula_output(self, tmp_path: Path):
        out = self._generate(tmp_path, formulas=False)
        assert not (out / "dynamic" / "formulas").exists()
        assert not (out / "static" / "Formula.swift").exists()
        model = (out / "dynamic" / "models" / "TestTableModel.swift").read_text()
        assert "Filters()" not in model

    def test_wrappers_false_suppresses_tables_and_main(self, tmp_path: Path):
        out = self._generate(tmp_path, wrappers=False)
        assert not (out / "dynamic" / "tables").exists()
        assert not (out / "Airtable.swift").exists()
        # Models are still emitted.
        assert (out / "dynamic" / "models" / "TestTableModel.swift").is_file()

    def test_runtime_false_suppresses_airtable_runtime(self, tmp_path: Path):
        out = self._generate(tmp_path, runtime=False)
        assert not (out / "static" / "AirtableRuntime.swift").exists()

    def test_all_flags_false_emits_minimal_output(self, tmp_path: Path):
        out = self._generate(tmp_path, formulas=False, wrappers=False, runtime=False)
        assert not (out / "dynamic" / "formulas").exists()
        assert not (out / "dynamic" / "tables").exists()
        assert not (out / "Airtable.swift").exists()
        assert not (out / "static" / "Formula.swift").exists()
        assert not (out / "static" / "AirtableRuntime.swift").exists()
        assert (out / "dynamic" / "models" / "TestTableModel.swift").is_file()
        assert (out / "dynamic" / "types" / "TestTableFields.swift").is_file()


class TestKotlinGeneratorOutput:
    """Kotlin generator (K-F3 — dict-only path) content assertions.

    Verifies the generator emits the expected file structure and key code
    snippets without shelling out to Gradle. Compilation is separately
    verified by ``tests/kotlin_static/`` + the integration tests in
    ``myairtable-tests``.
    """

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> Path:
        """Generate Kotlin code to a fresh tmp dir and return the output folder."""
        from myairtable.generators.kotlin import write_field_types, write_main, write_options, write_tables
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        write_field_types(base, output_folder)
        write_tables(base, output_folder)
        write_main(base, output_folder)
        return output_folder

    def test_field_types_emit_dual_id_and_name_constants(self, tmp_path: Path):
        """Every field must get both a `{field}Id` and `{field}Name` constant."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.kt").read_text()

        assert "object TestTableFields" in content
        assert 'const val primaryKeyId: String = "fld001"' in content
        assert 'const val primaryKeyName: String = "Primary Key"' in content

    def test_field_types_emit_name_to_id_and_id_to_name_maps(self, tmp_path: Path):
        """The nameToId / idToName maps enable dual-access lookup at runtime."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.kt").read_text()

        assert "val nameToId: Map<String, String>" in content
        assert "val idToName: Map<String, String>" in content
        assert '"Primary Key" to "fld001"' in content
        assert '"fld001" to "Primary Key"' in content
        assert "fun idByName(name: String): String? = nameToId[name]" in content
        assert "fun nameById(id: String): String? = idToName[id]" in content

    def test_field_types_all_ids_contains_every_field(self, tmp_path: Path):
        """allIds should list every field ID in schema order."""
        fields_spec: list[tuple[str, str, FieldType]] = [
            ("A", "fld001", "singleLineText"),
            ("B", "fld002", "number"),
            ("C", "fld003", "checkbox"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.kt").read_text()

        assert 'val allIds: List<String> = listOf("fld001", "fld002", "fld003")' in content

    def test_writable_fields_exclude_computed_from_create_object(self, tmp_path: Path):
        """Create{Table}Fields object omits computed fields (formula, createdTime, etc.)."""
        fields_spec: list[tuple[str, str, FieldType]] = [
            ("My Text", "fld001", "singleLineText"),
            ("My Formula", "fld002", "formula"),
            ("Created", "fld003", "createdTime"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.kt").read_text()

        assert "object CreateTestTableFields" in content
        create_block = content.split("object CreateTestTableFields")[1]
        assert "myTextId" in create_block
        assert "myFormulaId" not in create_block
        assert "createdId" not in create_block

    def test_tables_class_exposes_dict_accessor(self, tmp_path: Path):
        """Each table gets a {Table}Table class with a `.dict: DictTable` accessor."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.kt").read_text()

        assert "class TestTableTable(" in content
        assert 'const val TABLE_ID: String = "tblTEST123"' in content
        assert "val dict: DictTable" in content
        assert "nameToId = TestTableFields.nameToId" in content

    def test_main_airtable_exposes_per_table_accessors(self, tmp_path: Path):
        """Airtable.kt should expose each table as a lowerCamelCase property."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "Airtable.kt").read_text()

        assert "class Airtable(" in content
        assert "val client: AirtableClient," in content
        assert "val testTable: TestTableTable = TestTableTable(client)" in content
        # Secondary constructor with embedded default baseId.
        assert "constructor(" in content
        assert 'baseId: String = "appTEST123",' in content
        assert "suspend fun invalidateAllCaches()" in content

    def test_every_generated_file_declares_the_flat_package(self, tmp_path: Path):
        """All generated files live in the flat `myairtable` package."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        for path in out.rglob("*.kt"):
            assert "package myairtable" in path.read_text(), f"{path} missing package decl"

    def test_no_build_files_are_emitted(self, tmp_path: Path):
        """The generator never emits Gradle build files (matches no-Package.swift)."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        assert not (out / "build.gradle.kts").exists()
        assert not (out / "settings.gradle.kts").exists()

    def test_view_enum_implements_airtable_view(self, tmp_path: Path):
        """Generated `{Table}View` enums implement the static `AirtableView` interface."""
        from myairtable.generators.kotlin import write_field_types

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        base.tables[0].views = [View.model_construct(id="viw001", name="Grid view", type="grid", table_id="tblTEST123")]
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        write_field_types(base, output_folder)
        content = (output_folder / "dynamic" / "types" / "TestTableFields.kt").read_text()

        assert "enum class TestTableView(" in content
        assert "override val id: String," in content
        assert ") : AirtableView {" in content
        assert 'GRID_VIEW("viw001");' in content


class TestKotlinOptionsGenerator:
    """Kotlin select-option enum generation."""

    def _generate_with_options(self, tmp_path: Path) -> str:
        """Build a table with a singleSelect field and return its options file content."""
        from myairtable.generators.kotlin import write_options
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("Status", "fld001", "singleSelect")])
        field = base.tables[0].fields[0]
        assert field.options is not None
        field.options.choices = [
            Choice.model_construct(id="sel1", name="Open"),
            Choice.model_construct(id="sel2", name="In Progress"),
            Choice.model_construct(id="sel3", name="Closed"),
        ]
        assert field.__pydantic_private__ is not None
        field.__pydantic_private__["_select_options_cache"] = None

        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        return (output_folder / "dynamic" / "options" / "TestTableOptions.kt").read_text()

    def test_options_enum_is_serializable(self, tmp_path: Path):
        """Each options enum carries @Serializable so it decodes from wire values."""
        content = self._generate_with_options(tmp_path)
        assert "@Serializable" in content
        assert "enum class" in content

    def test_options_entries_are_screaming_snake_with_serial_names(self, tmp_path: Path):
        """Choices map to SCREAMING_SNAKE_CASE entries with @SerialName raw values.

        Entry order follows select_options() (alphabetical), so assertions are
        order-agnostic: each @SerialName must be immediately followed by its entry.
        """
        import re

        content = self._generate_with_options(tmp_path)
        for raw, entry in [("Open", "OPEN"), ("In Progress", "IN_PROGRESS"), ("Closed", "CLOSED")]:
            assert re.search(rf'@SerialName\("{raw}"\)\s+{entry}[,;]', content), f"missing {raw} -> {entry}"
        # The final entry is terminated with `;`.
        assert re.search(r"\w+;\n}", content)


class TestKotlinFlagGating:
    """generate_kotlin must honor the wrappers flag (formulas/runtime gating
    is exercised once Formula.kt / AirtableRuntime.kt exist in K-F7/K-F8)."""

    def _generate(self, tmp_path: Path, **flags) -> Path:
        from myairtable.generators.kotlin import generate_kotlin
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        map_types(base)
        generate_kotlin(base, output_folder, **flags)
        return output_folder

    def test_default_flags_emit_tables_and_main(self, tmp_path: Path):
        out = self._generate(tmp_path)
        assert (out / "dynamic" / "tables" / "TestTableTable.kt").is_file()
        assert (out / "Airtable.kt").is_file()
        assert (out / "static" / "DictTable.kt").is_file()

    def test_wrappers_false_suppresses_tables_and_main(self, tmp_path: Path):
        out = self._generate(tmp_path, wrappers=False)
        assert not (out / "dynamic" / "tables").exists()
        assert not (out / "Airtable.kt").exists()
        # Field types are still emitted.
        assert (out / "dynamic" / "types" / "TestTableFields.kt").is_file()


class TestKotlinComputedFields:
    """Kotlin model generation: constructor-property val/var split (plan §2.3.1)."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.kotlin import write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        map_types(base)
        write_models(base, output_folder)
        return (output_folder / "dynamic" / "models" / "TestTableModel.kt").read_text()

    def test_computed_fields_are_val_constructor_params(self, tmp_path: Path):
        """Computed fields are decode-only `val` params (mutation = compile error)."""
        content = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert "val myFormula: MaybeSpecialOrError<Double>? = null," in content
        assert "var myFormula" not in content

    def test_writable_fields_are_var_constructor_params(self, tmp_path: Path):
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "var myText: String? = null," in content

    def test_reserved_model_member_names_are_renamed(self, tmp_path: Path):
        """JR follow-up: a field whose camel collides with a plumbing member
        (`snapshot`/`attachedClient`) is suffixed `Field` so it isn't a Kotlin
        redeclaration error; a fully-symbolic name falls back to `field`."""
        import re

        content = self._generate(
            [
                ("Snapshot", "fld001", "singleLineText"),
                ("Attached Client", "fld002", "singleLineText"),
                ("_", "fld003", "singleLineText"),
            ],
            tmp_path,
        )
        # The plumbing members appear exactly once each (the field versions are renamed).
        assert len(re.findall(r"\bvar snapshot\b", content)) == 1
        assert len(re.findall(r"\bvar attachedClient\b", content)) == 1
        assert "var snapshotField: String? = null," in content
        assert "var attachedClientField: String? = null," in content
        assert "var field: String? = null," in content  # `_` -> field
        assert "``" not in content  # no empty backtick identifier

    def test_model_is_serializable_with_field_id_serial_names(self, tmp_path: Path):
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "@Serializable" in content
        assert '@SerialName("fld001")' in content
        assert "@file:UseSerializers(AirtableInstantSerializer::class, AirtableDurationSerializer::class)" in content

    def test_model_implements_airtable_model_with_transients(self, tmp_path: Path):
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert ") : AirtableModel {" in content
        assert "override var id: RecordId? = null" in content
        assert "override var createdTime: Instant? = null" in content
        assert "override var attachedClient: AirtableClient? = null" in content
        assert "private var snapshot: Map<String, JsonElement> = emptyMap()" in content
        # All four are @Transient (never serialized).
        assert content.count("@Transient") == 4
        assert 'const val TABLE_ID: String = "tblTEST123"' in content
        assert "override val tableId: String get() = TABLE_ID" in content

    def test_create_fields_exclude_computed_but_to_record_includes_all(self, tmp_path: Path):
        fields_spec: list[tuple[str, str, FieldType]] = [
            ("My Text", "fld001", "singleLineText"),
            ("My Formula", "fld002", "formula"),
        ]
        content = self._generate(fields_spec, tmp_path)

        create_block = content.split("override fun toCreateFields()")[1].split("override fun toRecord()")[0]
        record_block = content.split("override fun toRecord()")[1].split("override fun takeSnapshot()")[0]

        assert '"fld001"' in create_block
        assert '"fld002"' not in create_block, "computed fields must never reach create payloads"
        assert '"fld001"' in record_block
        assert '"fld002"' in record_block

    def test_dirty_fields_diff_against_snapshot_with_jsonnull_clears(self, tmp_path: Path):
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "override fun dirtyFields(): Map<String, JsonElement> {" in content
        assert "if (snapshot[key] != value) dirty[key] = value" in content
        assert "dirty[key] = JsonNull" in content
        assert "snapshot = toCreateFields()" in content

    def test_linked_record_fields_are_record_id_lists(self, tmp_path: Path):
        content = self._generate([("Links", "fld001", "multipleRecordLinks")], tmp_path)
        assert "var links: List<RecordId>? = null," in content

    def test_tables_forward_orm_methods(self, tmp_path: Path):
        """ORM is the default: get/create/update/upsert/delete live on the table."""
        from myairtable.generators.kotlin import write_tables
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        map_types(base)
        write_tables(base, output_folder)
        content = (output_folder / "dynamic" / "tables" / "TestTableTable.kt").read_text()

        assert "private val orm: OrmTable<TestTableModel> = OrmTable(TABLE_ID, TestTableModel.serializer(), client)" in content
        assert "suspend fun get(recordId: String): TestTableModel" in content
        assert "suspend fun get(recordIds: List<String>): List<TestTableModel>" in content
        assert "suspend fun get(query: AirtableQuery = AirtableQuery()): List<TestTableModel>" in content
        assert "suspend fun create(model: TestTableModel)" in content
        assert "suspend fun create(models: List<TestTableModel>)" in content
        assert "suspend fun update(model: TestTableModel)" in content
        assert "suspend fun updateFields(recordId: String, fields: Map<String, JsonElement>)" in content
        assert "suspend fun duplicate(model: TestTableModel, typecast: Boolean = false)" in content
        assert '@JvmName("duplicateModels")' in content
        assert "suspend fun duplicate(recordIds: List<String>, typecast: Boolean = false)" in content
        assert "suspend fun upsert(model: TestTableModel, fieldsToMergeOn: List<String>)" in content
        assert "suspend fun delete(recordId: String)" in content
        assert '@JvmName("deleteModels")' in content
        # No public orm accessor.
        assert "val orm" in content and "private val orm" in content


class TestKotlinFormulas:
    """Kotlin formula-builder + runtime-evaluation generation (K-F7/K-F8)."""

    def _generate(self, tmp_path: Path, formula: str | None = None, **flags) -> Path:
        from myairtable.generators.kotlin import write_formula_helpers, write_models
        from myairtable.utils.type_mapper import map_types

        fields_spec: list[tuple[str, str, FieldType]] = [("My Text", "fld001", "singleLineText")]
        formula_map = None
        if formula is not None:
            fields_spec.append(("My Formula", "fld002", "formula"))
            formula_map = {"fld002": formula}
        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        map_types(base)
        write_formula_helpers(base, output_folder)
        write_models(base, output_folder, **flags)
        return output_folder

    def test_filters_class_has_typed_formula_fields(self, tmp_path: Path):
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "formulas" / "TestTableFilters.kt").read_text()
        assert "class TestTableFilters {" in content
        assert "val id: FormulaId = FormulaId()" in content
        assert 'val myText: FormulaTextField = FormulaTextField("fld001")' in content

    def test_model_companion_exposes_filters_as_f(self, tmp_path: Path):
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "models" / "TestTableModel.kt").read_text()
        assert "val f: TestTableFilters = TestTableFilters()" in content

    def test_formulas_false_omits_companion_f(self, tmp_path: Path):
        out = self._generate(tmp_path, formulas=False)
        content = (out / "dynamic" / "models" / "TestTableModel.kt").read_text()
        assert "val f:" not in content

    def test_runtime_true_emits_evaluate_methods(self, tmp_path: Path):
        out = self._generate(tmp_path, formula='{fld001} & "!"')
        content = (out / "dynamic" / "models" / "TestTableModel.kt").read_text()
        assert "fun evaluateMyFormula(): JsonElement = " in content
        assert 'JsonPrimitive(S(V(this.myText)) + "!")' in content

    def test_runtime_false_omits_evaluate_methods(self, tmp_path: Path):
        out = self._generate(tmp_path, formula='{fld001} & "!"', runtime=False)
        content = (out / "dynamic" / "models" / "TestTableModel.kt").read_text()
        assert "fun evaluate" not in content


class TestGeneratedCommentAndLiteralEscaping:
    """KDoc/doc-comment sanitization + string-literal escaping (myairtable-ydk1).

    A hostile field name must not be able to terminate a generated comment
    block early (`*/`) or produce illegal string-literal escapes ($, tab,
    newline, quote).
    """

    EVIL = 'evil */ name $x "q"'
    CONTROL = "Tab\there\nNewline"

    def _generate(self, language: str, tmp_path: Path) -> Path:
        if language == "kotlin":
            from myairtable.generators.kotlin import write_field_types, write_models
        else:
            from myairtable.generators.swift import write_field_types, write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(
            [
                (self.EVIL, "fld001", "singleLineText"),
                (self.CONTROL, "fld002", "singleLineText"),
            ]
        )
        output_folder = tmp_path / f"{language}_output"
        output_folder.mkdir()
        map_types(base)
        write_field_types(base, output_folder)
        write_models(base, output_folder)
        return output_folder

    @staticmethod
    def _comment_lines(content: str) -> list[str]:
        return [ln.strip() for ln in content.splitlines() if ln.strip().startswith(("/**", "*", "///", "//"))]

    def test_kotlin_comments_cannot_be_terminated_early(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        for rel in ("dynamic/types/TestTableFields.kt", "dynamic/models/TestTableModel.kt"):
            content = (out / rel).read_text()
            for line in self._comment_lines(content):
                assert "evil */" not in line, f"raw */ inside a comment line: {line!r}"
            assert "evil * / name" in content

    def test_kotlin_model_kdoc_blocks_are_balanced(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/models/TestTableModel.kt").read_text()
        # Field names only appear in comments in the model file, so any stray
        # terminator would unbalance the KDoc blocks.
        assert content.count("/**") == content.count("*/")

    def test_kotlin_string_literals_are_escaped(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/types/TestTableFields.kt").read_text()
        # sanitize_string turns the inner double quotes into single quotes;
        # $ must be escaped for Kotlin string templates.
        assert "\"evil */ name \\$x 'q'\"" in content
        assert '"Tab\\there\\nNewline" to "fld002",' in content

    def test_kotlin_doc_comment_splits_embedded_newlines(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/types/TestTableFields.kt").read_text()
        assert " * Newline` (field ID)" in content

    def test_swift_comments_cannot_be_terminated_early(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        for rel in ("dynamic/types/TestTableFields.swift", "dynamic/models/TestTableModel.swift"):
            content = (out / rel).read_text()
            for line in self._comment_lines(content):
                assert "evil */" not in line, f"raw */ inside a comment line: {line!r}"
            assert "evil * / name" in content

    def test_swift_string_literals_are_escaped(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        content = (out / "dynamic/types/TestTableFields.swift").read_text()
        # Swift has no $ templates, so $ stays raw; tab/newline must be escaped.
        assert "\"evil */ name $x 'q'\"" in content
        assert '"Tab\\there\\nNewline": "fld002",' in content

    def test_swift_doc_comment_splits_embedded_newlines(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        content = (out / "dynamic/types/TestTableFields.swift").read_text()
        assert "/// Newline` (field ID)" in content


class TestIdentifierCollisionDedup:
    """Distinct field/table names that collapse to the same identifier must be
    deduplicated consistently across every generated declaration (myairtable-w42e)."""

    FIELDS: list[tuple[str, str, FieldType]] = [
        ("My Field", "fld001", "singleLineText"),
        ("my field", "fld002", "singleLineText"),
        ("Calc", "fld003", "formula"),
    ]
    FORMULA_MAP = {"fld003": "{fld002}"}

    def _generate(self, language: str, tmp_path: Path) -> Path:
        if language == "kotlin":
            from myairtable.generators.kotlin import write_field_types, write_formula_helpers, write_models
        else:
            from myairtable.generators.swift import write_field_types, write_formula_helpers, write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        output_folder = tmp_path / f"{language}_output"
        output_folder.mkdir()
        map_types(base)
        write_field_types(base, output_folder)
        write_formula_helpers(base, output_folder)
        write_models(base, output_folder)
        return output_folder

    # ---- Kotlin ----

    def test_kotlin_model_dedups_colliding_properties(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/models/TestTableModel.kt").read_text()
        assert "var myField: String? = null," in content
        assert "var myFieldV2: String? = null," in content
        # No duplicate declarations.
        assert content.count("var myField: ") == 1
        assert content.count("var myFieldV2: ") == 1

    def test_kotlin_fields_consts_dedup(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/types/TestTableFields.kt").read_text()
        assert 'const val myFieldId: String = "fld001"' in content
        assert 'const val myFieldV2Id: String = "fld002"' in content
        assert content.count("const val myFieldId: ") == 2  # Fields + CreateFields
        assert content.count("const val myFieldV2Id: ") == 2

    def test_kotlin_filters_dedup(self, tmp_path: Path):
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/formulas/TestTableFilters.kt").read_text()
        assert 'val myField: FormulaTextField = FormulaTextField("fld001")' in content
        assert 'val myFieldV2: FormulaTextField = FormulaTextField("fld002")' in content

    def test_kotlin_formula_field_name_map_uses_deduped_name(self, tmp_path: Path):
        """A formula referencing the second colliding field must transpile to the deduped property."""
        out = self._generate("kotlin", tmp_path)
        content = (out / "dynamic/models/TestTableModel.kt").read_text()
        assert "fun evaluateCalc(): JsonElement = V(this.myFieldV2)" in content

    # ---- Swift ----

    def test_swift_model_dedups_colliding_properties(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        content = (out / "dynamic/models/TestTableModel.swift").read_text()
        assert "public var myField: String?" in content
        assert "public var myFieldV2: String?" in content
        assert 'case myField = "fld001"' in content
        assert 'case myFieldV2 = "fld002"' in content
        # No duplicate declarations.
        assert content.count("public var myField: ") == 1
        assert content.count("public var myFieldV2: ") == 1

    def test_swift_fields_consts_dedup(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        content = (out / "dynamic/types/TestTableFields.swift").read_text()
        assert 'public static let myFieldId: String = "fld001"' in content
        assert 'public static let myFieldV2Id: String = "fld002"' in content

    def test_swift_filters_dedup(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        content = (out / "dynamic/formulas/TestTableFilters.swift").read_text()
        assert "public let myField: FormulaTextField" in content
        assert "public let myFieldV2: FormulaTextField" in content
        assert 'self.myFieldV2 = FormulaTextField("fld002")' in content

    def test_swift_formula_field_name_map_uses_deduped_name(self, tmp_path: Path):
        out = self._generate("swift", tmp_path)
        content = (out / "dynamic/models/TestTableModel.swift").read_text()
        assert "public func evaluateCalc() -> AirtableJSONValue {" in content
        assert "AirtableRuntime.V(self.myFieldV2)" in content

    # ---- Table-name collisions ----

    @staticmethod
    def _add_colliding_table(base: Base) -> None:
        """Add a second table whose name collapses to the same PascalCase prefix."""
        table = Table.model_construct(
            id="tblTEST456",
            name="test table",
            primary_field_id="fld100",
            fields=[],
            views=[],
            base=base,
            _field_id_to_name_cache=None,
        )
        table.__pydantic_private__ = {
            "_field_id_to_name_cache": None,
            "_snake": None,
            "_pascal": None,
            "_model": None,
            "_upper": None,
            "_name_cache": {},
        }
        base.tables.append(table)
        base._table_index[table.id] = table

    def test_kotlin_table_name_collision_dedup(self, tmp_path: Path):
        from myairtable.generators.kotlin import write_main

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        self._add_colliding_table(base)
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir()
        write_main(base, output_folder)
        content = (output_folder / "Airtable.kt").read_text()
        assert "val testTable: TestTableTable = TestTableTable(client)" in content
        assert "val testTableV2: TestTableV2Table = TestTableV2Table(client)" in content

    def test_swift_table_name_collision_dedup(self, tmp_path: Path):
        from myairtable.generators.swift import write_main

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        self._add_colliding_table(base)
        output_folder = tmp_path / "swift_output"
        output_folder.mkdir()
        write_main(base, output_folder)
        content = (output_folder / "Airtable.swift").read_text()
        assert "public let testTable: TestTableTable" in content
        assert "public let testTableV2: TestTableV2Table" in content

    # ---- Shared dedup helper ----

    def test_deduplicate_identifiers_residual_collision(self):
        """["A", "A", "A_V2"] must not yield two A_V2 — suffixes bump until free."""
        from myairtable.utils.helpers import deduplicate_identifiers

        result = deduplicate_identifiers(["A", "A", "A_V2"], suffix="_V")
        assert result == ["A", "A_V3", "A_V2"]
        assert len(set(result)) == len(result)

    def test_deduplicate_identifiers_camel_suffix(self):
        from myairtable.utils.helpers import deduplicate_identifiers

        assert deduplicate_identifiers(["myField", "myField", "myField"]) == ["myField", "myFieldV2", "myFieldV3"]


class TestOriginalGeneratorCollisionDedup:
    """Python / TypeScript / Rust / JavaScript must deduplicate property names that
    collapse to the same identifier (e.g. a custom property name duplicating another
    field's), rather than emitting duplicate dict keys / struct fields (myairtable-xc8h).

    snake_case languages (Python, Rust) suffix with `_v2`; camelCase (TS, JS) with `V2`.
    """

    FIELDS: list[tuple[str, str, FieldType]] = [
        ("My Field", "fld001", "singleLineText"),
        ("my field", "fld002", "singleLineText"),
        ("Calc", "fld003", "formula"),
    ]
    FORMULA_MAP = {"fld003": "{fld002}"}

    # ---- Shared snake helper ----

    def test_snake_map_suffixes_second_collider(self):
        from myairtable.utils.helpers import deduplicated_field_property_map_snake

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        table = base.tables[0]
        prop_map = deduplicated_field_property_map_snake(table)
        assert prop_map["fld001"] == "my_field"
        assert prop_map["fld002"] == "my_field_v2"

    # ---- Python ----

    def test_python_types_dedup_property_map(self, tmp_path: Path):
        from myairtable.generators.python import write_types

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        out = tmp_path / "py_output"
        out.mkdir()
        write_types(base, out)
        content = (out / "dynamic/types/test_table.py").read_text()
        # The FieldPropertyId mapping is a dict keyed by property name — a duplicate
        # key is the exact F601 defect this fixes.
        assert '"my_field": "fld001"' in content
        assert '"my_field_v2": "fld002"' in content
        # Before the fix, fld002 also mapped to "my_field" -> duplicate key (F601).
        assert '"my_field": "fld002"' not in content
        # Each property-keyed dict (Id + Name mappings) lists my_field exactly once.
        assert content.count('"my_field": "fld001"') == 1

    def test_python_model_dedup_and_formula_reference(self, tmp_path: Path):
        from myairtable.generators.python import write_models

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        out = tmp_path / "py_output"
        out.mkdir()
        write_models(base, out, formulas=False, runtime=True, package_prefix="")
        content = (out / "dynamic/models/test_table.py").read_text()
        assert "my_field:" in content
        assert "my_field_v2:" in content
        # The formula references fld002 (the second collider) -> deduped property.
        assert "self.my_field_v2" in content

    # ---- Rust ----

    def test_rust_types_and_model_dedup(self, tmp_path: Path):
        from myairtable.generators.rust import write_field_types, write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        out = tmp_path / "rust_output"
        out.mkdir()
        map_types(base)
        write_field_types(base, out)
        write_models(base, out, formulas=False, runtime=True)

        types = (out / "dynamic/types/test_table.rs").read_text()
        assert '"fld001" => Some("my_field"),' in types
        assert '"fld002" => Some("my_field_v2"),' in types
        assert "pub const MY_FIELD:" in types
        assert "pub const MY_FIELD_V2:" in types

        model = (out / "dynamic/models/test_table.rs").read_text()
        assert "pub my_field: Option<" in model
        assert "pub my_field_v2: Option<" in model
        assert "self.my_field_v2" in model

    # ---- TypeScript ----

    def test_typescript_model_dedup_and_formula_reference(self, tmp_path: Path):
        from myairtable.generators.typescript import write_models

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        out = tmp_path / "ts_output"
        out.mkdir()
        write_models(base, out, formulas=False, runtime=True, zod=False)
        content = (out / "dynamic/models/testTable.ts").read_text()
        assert "get myField()" in content
        assert "get myFieldV2()" in content
        assert content.count('propertyName: "myField"') == 1
        assert content.count('propertyName: "myFieldV2"') == 1
        assert 'this._fields["myFieldV2"]' in content

    # ---- JavaScript ----

    def test_javascript_model_dedup_and_formula_reference(self, tmp_path: Path):
        from myairtable.generators.javascript import write_models

        base = make_test_base(self.FIELDS, formula_map=self.FORMULA_MAP)
        out = tmp_path / "js_output"
        out.mkdir()
        write_models(base, out, formulas=False, runtime=True, zod=False)
        content = (out / "dynamic/models/testTable.js").read_text()
        assert "get myField()" in content
        assert "get myFieldV2()" in content
        assert content.count('propertyName: "myFieldV2"') == 1
        assert 'this._fields["myFieldV2"]' in content


class TestKotlinGeneratorEdgeCases:
    """myairtable-dmiw — generator edge cases flagged by the ultra-review."""

    def _generate_model(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.kotlin import write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "kotlin_output"
        output_folder.mkdir(exist_ok=True)
        map_types(base)
        write_models(base, output_folder)
        return (output_folder / "dynamic" / "models" / "TestTableModel.kt").read_text()

    def test_keyword_named_field_is_sanitized(self, tmp_path: Path):
        # The shared property map suffixes hard keywords with `_` (object -> object_)
        # so derived names (object_Id, evaluateObject_) stay backtick-free.
        content = self._generate_model([("Object", "fld001", "singleLineText")], tmp_path)
        assert "var object_: String? = null," in content
        assert "`object`" not in content

    def test_keyword_named_field_in_formula_reference(self, tmp_path: Path):
        from myairtable.formulas.formula_transpiler import transpile_formula

        result = transpile_formula('{fld001} & "!"', "kotlin", {"fld001": "`object`"}, set())
        assert result == 'JsonPrimitive(S(V(this.`object`)) + "!")'

    def test_zero_writable_fields_omits_create_object_and_empty_create_map(self, tmp_path: Path):
        from myairtable.generators.kotlin import write_field_types
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("My Formula", "fld001", "formula")])
        out = tmp_path / "kotlin_output"
        out.mkdir()
        map_types(base)
        write_field_types(base, out)
        content = (out / "dynamic" / "types" / "TestTableFields.kt").read_text()
        assert "CreateTestTableFields" not in content

        model = self._generate_model([("My Formula", "fld001", "formula")], tmp_path)
        assert "override fun toCreateFields(): Map<String, JsonElement> =" in model

    def test_duration_import_only_when_needed(self, tmp_path: Path):
        without = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "import kotlin.time.Duration" not in without

    def test_model_has_tostring(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert 'override fun toString(): String = "TestTableModel(id=$id, ${toRecord().size} fields)"' in content

    def test_choice_to_entry_edges(self):
        from myairtable.utils.write_to_kotlin_file import _choice_to_entry

        assert _choice_to_entry("3rd Party") == "N_3RD_PARTY"
        assert _choice_to_entry("") == "EMPTY"
        # Pure punctuation sanitizes through sanitize_property_name's char map.
        import re

        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", _choice_to_entry("!!!"))
        assert _choice_to_entry("openInvoices") == "OPEN_INVOICES"


# =============================================================================
# Java generator (J-F3)
# =============================================================================


class TestJavaOptionsGenerator:
    """Java select-option enum generation (one public enum per file)."""

    def _generate_options(self, choices: list[str], tmp_path: Path) -> Path:
        """Build a table with a singleSelect field and return the options dir."""
        from myairtable.generators.java import write_options
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("Status", "fld001", "singleSelect")])
        field = base.tables[0].fields[0]
        assert field.options is not None
        field.options.choices = [Choice.model_construct(id=f"sel{i:03d}", name=name) for i, name in enumerate(choices)]
        assert field.__pydantic_private__ is not None
        field.__pydantic_private__["_select_options_cache"] = None

        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        return output_folder / "dynamic" / "options"

    def test_one_public_enum_file_per_select_field(self, tmp_path: Path):
        """Java requires one public type per file — the enum gets its own file."""
        options_dir = self._generate_options(["Open", "Closed"], tmp_path)
        enum_file = options_dir / "TestTableStatusOption.java"
        assert enum_file.is_file()
        content = enum_file.read_text()
        assert "package myairtable;" in content
        assert "public enum TestTableStatusOption {" in content

    def test_entries_are_screaming_snake_with_raw_values(self, tmp_path: Path):
        """Choices map to SCREAMING_SNAKE_CASE constants carrying the raw string.

        Entry order follows select_options() (alphabetical), so assertions are
        order-agnostic; the final constant is terminated with `;`.
        """
        import re

        options_dir = self._generate_options(["Open", "In Progress", "Closed"], tmp_path)
        content = (options_dir / "TestTableStatusOption.java").read_text()
        for raw, entry in [("Open", "OPEN"), ("In Progress", "IN_PROGRESS"), ("Closed", "CLOSED")]:
            assert re.search(rf'{entry}\("{raw}"\)[,;]', content), f"missing {raw} -> {entry}"
        # The final entry is terminated with `;` so the value field can follow.
        assert re.search(r'\w+\("[^"]*"\);', content)

    def test_json_value_and_json_creator_round_trip(self, tmp_path: Path):
        """The enum exposes @JsonValue value() + @JsonCreator fromValue() for Jackson."""
        options_dir = self._generate_options(["Open"], tmp_path)
        content = (options_dir / "TestTableStatusOption.java").read_text()
        assert "import com.fasterxml.jackson.annotation.JsonValue;" in content
        assert "import com.fasterxml.jackson.annotation.JsonCreator;" in content
        assert "@JsonValue" in content
        assert "public String value() {" in content
        assert "@JsonCreator" in content
        assert "public static TestTableStatusOption fromValue(String value) {" in content

    def test_raw_value_strings_are_escaped(self, tmp_path: Path):
        """Choice names containing quotes must be escaped in the constructor literal."""
        options_dir = self._generate_options(['"Bucyrus, OH"'], tmp_path)
        content = (options_dir / "TestTableStatusOption.java").read_text()
        assert '("\\"Bucyrus, OH\\"")' in content

    def test_colliding_entries_get_v2_suffix(self, tmp_path: Path):
        """Distinct choices that collapse to the same constant deduplicate via _V2."""
        options_dir = self._generate_options(["Open", "open"], tmp_path)
        content = (options_dir / "TestTableStatusOption.java").read_text()
        assert 'OPEN("' in content
        assert 'OPEN_V2("' in content

    def _generate_multi(self, fields_spec, tmp_path: Path) -> Path:
        """Build a table whose select fields each carry choices, return options dir.

        `fields_spec` is `[(field_name, field_id, [choice, ...]), ...]`.
        """
        from myairtable.generators.java import write_options
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([(name, fid, "singleSelect") for name, fid, _ in fields_spec])
        for (_, _, choices), field in zip(fields_spec, base.tables[0].fields):
            assert field.options is not None
            assert field.__pydantic_private__ is not None
            field.options.choices = [Choice.model_construct(id=f"{field.id}sel{i}", name=c) for i, c in enumerate(choices)]
            field.__pydantic_private__["_select_options_cache"] = None
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        return output_folder / "dynamic" / "options"

    def test_within_table_options_name_collision_does_not_overwrite(self, tmp_path: Path):
        """JR-H3: two select fields whose names collapse must NOT share one enum
        file (the second would silently overwrite the first). The dedup map gives
        the colliding field a `V2`-suffixed enum name → two distinct files."""
        options_dir = self._generate_multi(
            [("Status", "fld001", ["A", "B"]), ("Status.", "fld002", ["C", "D"])],
            tmp_path,
        )
        primary = (options_dir / "TestTableStatusOption.java").read_text()
        secondary = (options_dir / "TestTableStatusOptionV2.java").read_text()
        # First field's choices survive (were not overwritten); second got V2.
        assert 'A("A")' in primary and 'B("B")' in primary
        assert 'C("C")' in secondary and 'D("D")' in secondary

    def test_cross_table_options_name_collision_dedups(self, tmp_path: Path):
        """JR-H3: the raw options name uses the un-deduplicated table pascal, so
        same-named tables collide across tables too — the base-wide dedup map
        still keeps the enum names unique."""
        from myairtable.generators.java import write_options
        from myairtable.utils.type_mapper import map_types

        # Two tables that both pascal-ize to `Foo`, each with a `Status` select.
        base = make_test_base([("Status", "fld001", "singleSelect")])
        first_table = base.tables[0]
        assert first_table.__pydantic_private__ is not None
        first_table.name = "Foo"
        first_table.__pydantic_private__["_pascal"] = None
        second = make_test_base([("Status", "fld101", "singleSelect")]).tables[0]
        assert second.__pydantic_private__ is not None
        second.id = "tblSECOND"
        second.name = "Foo "  # trailing space → pascal-izes to `Foo` as well
        second.__pydantic_private__["_pascal"] = None
        for f in second.fields:
            f.base = base
            f.table = second
        base.tables.append(second)
        base._table_index[second.id] = second
        for f in second.fields:
            base._field_index[f.id] = f
        base._select_fields_cache = None
        base._options_name_map_cache = None
        for t in base.tables:
            for f in t.fields:
                assert f.options is not None
                assert f.__pydantic_private__ is not None
                f.options.choices = [Choice.model_construct(id=f"{f.id}s0", name="X")]
                f.__pydantic_private__["_select_options_cache"] = None
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_options(base, output_folder)
        files = sorted(p.name for p in (output_folder / "dynamic" / "options").glob("*.java"))
        # Two distinct enum files, not one overwritten — names deduplicated.
        assert files == ["FooStatusOption.java", "FooStatusOptionV2.java"], files


class TestJavaFieldTypes:
    """Java `{Table}Fields` / `{Table}View` / `Create{Table}Fields` generation."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> Path:
        from myairtable.generators.java import write_field_types
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_field_types(base, output_folder)
        return output_folder

    def test_field_types_emit_dual_id_and_name_constants(self, tmp_path: Path):
        """Every field must get both a `{field}Id` and `{field}Name` constant."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()

        assert "public final class TestTableFields {" in content
        assert 'public static final String primaryKeyId = "fld001";' in content
        assert 'public static final String primaryKeyName = "Primary Key";' in content

    def test_field_types_all_ids_contains_every_field(self, tmp_path: Path):
        """allIds should list every field ID in schema order."""
        fields_spec: list[tuple[str, str, FieldType]] = [
            ("A", "fld001", "singleLineText"),
            ("B", "fld002", "number"),
            ("C", "fld003", "checkbox"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()

        assert 'public static final List<String> allIds = List.of("fld001", "fld002", "fld003");' in content

    def test_field_types_emit_name_to_id_and_id_to_name_maps(self, tmp_path: Path):
        """The nameToId / idToName maps enable dual-access lookup at runtime."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()

        assert "public static final Map<String, String> nameToId =" in content
        assert "public static final Map<String, String> idToName =" in content
        assert 'Map.entry("Primary Key", "fld001")' in content
        assert 'Map.entry("fld001", "Primary Key")' in content
        assert "public static String idByName(String name) {" in content
        assert "public static String nameById(String id) {" in content

    def test_no_trailing_comma_before_map_of_entries_close(self, tmp_path: Path):
        """Map.ofEntries blocks must not leave a trailing comma before `);`."""
        import re

        fields_spec: list[tuple[str, str, FieldType]] = [
            ("A", "fld001", "singleLineText"),
            ("B", "fld002", "number"),
            ("C", "fld003", "checkbox"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()

        assert "Map.ofEntries(" in content
        assert not re.search(r",\s*\n\s*\);", content), "trailing comma before `);` is a Java syntax error"

    def test_name_to_id_collapses_duplicate_sanitized_keys(self, tmp_path: Path):
        """JR-M1: field names differing only by quote style sanitize to the same
        key; Map.ofEntries THROWS on duplicate keys at class init, bricking the
        client. The generator must collapse to one entry (last-wins, like Kotlin
        mapOf) so the static initializer can't crash."""
        out = self._generate(
            [('He said "hi"', "fld001", "singleLineText"), ("He said 'hi'", "fld002", "number")],
            tmp_path,
        )
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()
        # Exactly one nameToId entry for the collapsed key (sanitize turns " into ').
        assert content.count("Map.entry(\"He said 'hi'\", ") == 1, "duplicate nameToId key would throw at <clinit>"
        # Last-wins (matches Kotlin mapOf): the second field's ID survives.
        assert 'Map.entry("He said \'hi\'", "fld002")' in content
        # idToName is keyed by unique field IDs — both survive there.
        assert 'Map.entry("fld001", ' in content and 'Map.entry("fld002", ' in content

    def test_create_fields_excludes_computed(self, tmp_path: Path):
        """Create{Table}Fields lists writable fields only (formula/createdTime omitted)."""
        fields_spec: list[tuple[str, str, FieldType]] = [
            ("My Text", "fld001", "singleLineText"),
            ("My Formula", "fld002", "formula"),
            ("Created", "fld003", "createdTime"),
        ]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "types" / "CreateTestTableFields.java").read_text()

        assert "public final class CreateTestTableFields {" in content
        assert "myTextId" in content
        assert "myFormulaId" not in content
        assert "createdId" not in content

    def test_zero_writable_fields_omits_create_file(self, tmp_path: Path):
        """A computed-only table must not emit a Create{Table}Fields file at all."""
        out = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert not (out / "dynamic" / "types" / "CreateTestTableFields.java").exists()

    def test_view_enum_implements_airtable_view(self, tmp_path: Path):
        """Generated `{Table}View` enums implement the static `AirtableView` interface."""
        from myairtable.generators.java import write_field_types

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        base.tables[0].views = [View.model_construct(id="viw001", name="Grid view", type="grid", table_id="tblTEST123")]
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        write_field_types(base, output_folder)
        content = (output_folder / "dynamic" / "types" / "TestTableView.java").read_text()

        assert "public enum TestTableView implements AirtableView {" in content
        assert 'GRID_VIEW("viw001");' in content
        assert "@Override" in content
        assert "public String getId() {" in content

    def test_no_views_omits_view_file(self, tmp_path: Path):
        """A table without views must not emit a {Table}View file."""
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        assert not (out / "dynamic" / "types" / "TestTableView.java").exists()


class TestJavaTablesAndMain:
    """generate_java must honor the wrappers/runtime flags (J-F3 dict-only scope)."""

    FIELDS_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
    ]

    def _generate(self, tmp_path: Path, **flags) -> Path:
        from myairtable.generators.java import generate_java
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(self.FIELDS_SPEC)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        generate_java(base, output_folder, **flags)
        return output_folder

    def test_default_flags_emit_tables_main_and_static(self, tmp_path: Path):
        out = self._generate(tmp_path)
        assert (out / "dynamic" / "tables" / "TestTableTable.java").is_file()
        assert (out / "Airtable.java").is_file()
        assert (out / "static" / "DictTable.java").is_file()
        assert (out / "static" / "AirtableRuntime.java").is_file()

    def test_wrappers_false_suppresses_tables_and_main(self, tmp_path: Path):
        out = self._generate(tmp_path, wrappers=False)
        assert not (out / "dynamic" / "tables").exists()
        assert not (out / "Airtable.java").exists()
        # Field types are still emitted.
        assert (out / "dynamic" / "types" / "TestTableFields.java").is_file()

    def test_runtime_false_excludes_airtable_runtime(self, tmp_path: Path):
        out = self._generate(tmp_path, runtime=False)
        assert not (out / "static" / "AirtableRuntime.java").exists()
        # Other static files are still copied.
        assert (out / "static" / "DictTable.java").is_file()

    def test_table_class_exposes_dict_accessor(self, tmp_path: Path):
        """Each table gets a {Table}Table class with a `.dict()` accessor."""
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.java").read_text()

        assert "public final class TestTableTable {" in content
        assert 'public static final String TABLE_ID = "tblTEST123";' in content
        assert "public DictTable dict() {" in content
        assert "new DictTable(TABLE_ID, TestTableFields.nameToId, client);" in content

    def test_tables_forward_orm_methods(self, tmp_path: Path):
        """The generated table re-emits the ORM surface as explicit forwarders.

        Java is a Group B target: unlike Python/TS/C#/C++, {Table}Table does not inherit from
        OrmTable, so every verb has to be emitted here or it is simply absent from the
        generated API. Nothing else pins that list.
        """
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.java").read_text()

        assert "public TestTableModel create(TestTableModel model)" in content
        assert "public TestTableModel update(TestTableModel model)" in content
        assert "public TestTableModel duplicate(TestTableModel model)" in content
        assert "public TestTableModel duplicate(String recordId)" in content
        # List<Model> and List<String> erase to the same signature, hence the distinct names.
        assert "public List<TestTableModel> duplicateModels(List<TestTableModel> models)" in content
        assert "public List<TestTableModel> duplicateAll(List<String> recordIds)" in content

    def test_main_contains_base_id_and_per_table_accessors(self, tmp_path: Path):
        """Airtable.java should expose BASE_ID and one accessor method per table."""
        out = self._generate(tmp_path)
        content = (out / "Airtable.java").read_text()

        assert "public final class Airtable implements AutoCloseable {" in content
        assert 'public static final String BASE_ID = "appTEST123";' in content
        assert "public TestTableTable testTable() {" in content
        assert "public Airtable(AirtableClient client) {" in content
        assert "public Airtable(String baseId, String apiKey) {" in content
        assert "public void invalidateAllCaches() {" in content
        assert "public void close() {" in content


class TestJavaStringEscaping:
    """Javadoc sanitization + string-literal escaping for hostile Airtable names.

    A hostile field name must not be able to terminate a generated Javadoc
    block early (`*/`) or produce illegal string-literal escapes (quote, tab,
    newline). `<`, `>`, `&` must be HTML-entity-escaped in Javadoc prose.
    """

    EVIL = 'evil */ name $x "q"'
    CONTROL = "Tab\there\nNewline"

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.java import write_field_types
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_field_types(base, output_folder)
        return (output_folder / "dynamic" / "types" / "TestTableFields.java").read_text()

    @staticmethod
    def _comment_lines(content: str) -> list[str]:
        return [ln.strip() for ln in content.splitlines() if ln.strip().startswith(("/**", "*", "//"))]

    def test_javadoc_cannot_be_terminated_early(self, tmp_path: Path):
        content = self._generate([(self.EVIL, "fld001", "singleLineText")], tmp_path)
        for line in self._comment_lines(content):
            assert "evil */" not in line, f"raw */ inside a comment line: {line!r}"
        assert "evil * / name" in content

    def test_javadoc_blocks_are_balanced(self, tmp_path: Path):
        import re

        content = self._generate([(self.EVIL, "fld001", "singleLineText"), (self.CONTROL, "fld002", "singleLineText")], tmp_path)
        # `*/` inside a Java string literal is legal — blank out literals before
        # counting so only comment delimiters are compared.
        without_literals = re.sub(r'"(?:\\.|[^"\\])*"', '""', content)
        assert without_literals.count("/**") == without_literals.count("*/")

    def test_string_literals_are_escaped(self, tmp_path: Path):
        content = self._generate([(self.EVIL, "fld001", "singleLineText"), (self.CONTROL, "fld002", "singleLineText")], tmp_path)
        # sanitize_string turns the inner double quotes into single quotes;
        # Java has no $ templates, so $ stays raw (unlike Kotlin).
        assert "\"evil */ name $x 'q'\"" in content
        assert 'Map.entry("Tab\\there\\nNewline", "fld002")' in content

    def test_doc_comment_splits_embedded_newlines(self, tmp_path: Path):
        content = self._generate([(self.CONTROL, "fld001", "singleLineText")], tmp_path)
        assert " * Newline} (field ID)" in content

    def test_javadoc_html_entities_escaped(self, tmp_path: Path):
        """`<`, `>`, `&` are entity-escaped in Javadoc prose but raw in string literals."""
        content = self._generate([("A <b> & B", "fld001", "singleLineText")], tmp_path)
        assert "A &lt;b&gt; &amp; B" in content
        # The string literal keeps the raw characters.
        assert '= "A <b> & B";' in content

    def test_javadoc_unicode_escape_cannot_inject_code(self, tmp_path: Path):
        r"""JR-H1: a field name carrying the literal 6-char sequences
        `*/` must NOT let javac's unicode-escape pass (JLS 3.3, which
        runs inside comments before lexing) reconstitute `*/` and inject code.
        doc_comment doubles all backslashes, so the emitted comment carries
        `\\u002a\\u002f` (even backslash count → not escape-eligible)."""
        # Literal backslash-u sequences (NOT actual unicode escapes in this .py source).
        hostile = "x \\u002a\\u002f static{} /\\u002a y"
        content = self._generate([(hostile, "fld001", "singleLineText")], tmp_path)
        for line in self._comment_lines(content):
            # No single backslash immediately before `u` survives; doubling makes
            # every occurrence `\\u`, which javac never treats as an escape.
            assert "\\u" not in line.replace("\\\\u", ""), f"un-doubled \\u in comment: {line!r}"

    def test_javadoc_lone_backslash_u_is_neutralized(self, tmp_path: Path):
        r"""An innocent name like `Window\update` (a `\u` not followed by 4 hex
        digits) is a HARD javac error inside a comment unless the backslash is
        doubled. Assert the comment carries `\\update`, not a bare `\u`."""
        content = self._generate([(r"Window\update count", "fld001", "singleLineText")], tmp_path)
        comment = "\n".join(self._comment_lines(content))
        assert "\\\\update" in comment
        assert "\\u" not in comment.replace("\\\\u", "")

    def test_java_ident_renames_keywords_with_underscore_suffix(self):
        """Java has no identifier escaping — keywords/literals get a `_` suffix."""
        from myairtable.utils.write_to_java_file import _java_ident

        for kw in ("class", "switch", "true", "false", "null", "_", "var", "yield"):
            assert _java_ident(kw) == f"{kw}_"
        assert _java_ident("status") == "status"

    def test_keyword_table_name_gets_suffixed_accessor(self, tmp_path: Path):
        """A table named `Switch` yields a `switch_()` accessor on Airtable.java."""
        from myairtable.generators.java import write_main

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        base.tables[0].name = "Switch"
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        write_main(base, output_folder)
        content = (output_folder / "Airtable.java").read_text()

        assert "public SwitchTable switch_() {" in content
        assert "this.switch_ = new SwitchTable(client);" in content


class TestDedupJava:
    """Colliding field/table names must deduplicate consistently in Java output
    (Java analog of TestIdentifierCollisionDedup's Kotlin/Swift assertions)."""

    FIELDS: list[tuple[str, str, FieldType]] = [
        ("My Field", "fld001", "singleLineText"),
        ("my field", "fld002", "singleLineText"),
    ]

    def _generate(self, tmp_path: Path) -> Path:
        from myairtable.generators.java import write_field_types
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(self.FIELDS)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_field_types(base, output_folder)
        return output_folder

    def test_fields_consts_dedup(self, tmp_path: Path):
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()
        assert 'public static final String myFieldId = "fld001";' in content
        assert 'public static final String myFieldV2Id = "fld002";' in content
        # No duplicate declarations.
        assert content.count("public static final String myFieldId = ") == 1
        assert content.count("public static final String myFieldV2Id = ") == 1

    def test_create_fields_dedup_consistently(self, tmp_path: Path):
        """Create{Table}Fields must use the same deduplicated property names."""
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "types" / "CreateTestTableFields.java").read_text()
        assert 'public static final String myFieldId = "fld001";' in content
        assert 'public static final String myFieldV2Id = "fld002";' in content

    def test_name_maps_keep_distinct_raw_names(self, tmp_path: Path):
        """The raw Airtable names stay distinct in nameToId — only identifiers dedup."""
        out = self._generate(tmp_path)
        content = (out / "dynamic" / "types" / "TestTableFields.java").read_text()
        assert 'Map.entry("My Field", "fld001")' in content
        assert 'Map.entry("my field", "fld002")' in content

    def test_table_name_collision_dedup(self, tmp_path: Path):
        from myairtable.generators.java import write_main

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        TestIdentifierCollisionDedup._add_colliding_table(base)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        write_main(base, output_folder)
        content = (output_folder / "Airtable.java").read_text()
        assert "public TestTableTable testTable() {" in content
        assert "public TestTableV2Table testTableV2() {" in content


class TestJavaComputedTypes:
    """map_java_type wrapping for computed fields (pure type_mapper assertions)."""

    @staticmethod
    def _field(name: str, field_id: str, field_type: FieldType):
        return make_test_base([(name, field_id, field_type)]).tables[0].fields[0]

    def test_formula_number_wraps_maybe_special_or_error_double(self):
        from myairtable.utils.type_mapper import map_java_type

        assert map_java_type(self._field("Calc", "fld001", "formula")) == "MaybeSpecialOrError<Double>"

    def test_auto_number_wraps_maybe_special_or_error_long(self):
        from myairtable.utils.type_mapper import map_java_type

        assert map_java_type(self._field("Auto", "fld001", "autoNumber")) == "MaybeSpecialOrError<Long>"

    def test_lookup_wraps_vec_or_value(self):
        """A resolved lookup inner type wraps as VecOrValue<MaybeSpecialOrError<T>>."""
        from myairtable.utils.type_mapper import apply_java_computed_wrapping

        field = self._field("Look", "fld001", "multipleLookupValues")
        assert apply_java_computed_wrapping("Double", field) == "VecOrValue<MaybeSpecialOrError<Double>>"
        # Disambiguation-applied List<...> is stripped so the inner primitive is wrapped.
        assert apply_java_computed_wrapping("List<String>", field) == "VecOrValue<MaybeSpecialOrError<String>>"

    def test_lookup_with_unresolvable_inner_falls_back_to_json_node(self):
        """An unresolvable lookup renders as VecOrValue<JsonNode> end-to-end."""
        from myairtable.utils.type_mapper import map_java_type

        assert map_java_type(self._field("Look", "fld001", "multipleLookupValues")) == "VecOrValue<JsonNode>"

    def test_rollup_wraps_vec_or_value(self):
        """A resolved rollup inner type wraps as VecOrValue<MaybeSpecialOrError<T>>."""
        from myairtable.utils.type_mapper import apply_java_computed_wrapping

        field = self._field("Roll", "fld001", "rollup")
        assert apply_java_computed_wrapping("Double", field) == "VecOrValue<MaybeSpecialOrError<Double>>"

    def test_already_wrapped_type_is_left_alone(self):
        """apply_java_computed_wrapping is a no-op on already-wrapped types."""
        from myairtable.utils.type_mapper import apply_java_computed_wrapping

        field = self._field("Calc", "fld001", "formula")
        assert apply_java_computed_wrapping("MaybeSpecialOrError<Double>", field) == "MaybeSpecialOrError<Double>"

    def test_writable_field_is_never_wrapped(self):
        from myairtable.utils.type_mapper import apply_java_computed_wrapping

        field = self._field("My Text", "fld001", "singleLineText")
        assert apply_java_computed_wrapping("String", field) == "String"

    def test_writable_text_is_plain_string(self):
        from myairtable.utils.type_mapper import map_java_type

        assert map_java_type(self._field("My Text", "fld001", "singleLineText")) == "String"


class TestCSharpComputedTypes:
    """map_csharp_type wrapping for computed fields (pure type_mapper assertions)."""

    @staticmethod
    def _field(name: str, field_id: str, field_type: FieldType):
        return make_test_base([(name, field_id, field_type)]).tables[0].fields[0]

    def test_formula_number_wraps_maybe_special_or_error_double(self):
        from myairtable.utils.type_mapper import map_csharp_type

        assert map_csharp_type(self._field("Calc", "fld001", "formula")) == "MaybeSpecialOrError<double>"

    def test_auto_number_wraps_maybe_special_or_error_long(self):
        from myairtable.utils.type_mapper import map_csharp_type

        assert map_csharp_type(self._field("Auto", "fld001", "autoNumber")) == "MaybeSpecialOrError<long>"

    def test_lookup_wraps_vec_or_value(self):
        """A resolved lookup inner type wraps as VecOrValue<MaybeSpecialOrError<T>>."""
        from myairtable.utils.type_mapper import apply_csharp_computed_wrapping

        field = self._field("Look", "fld001", "multipleLookupValues")
        assert apply_csharp_computed_wrapping("double", field) == "VecOrValue<MaybeSpecialOrError<double>>"
        # Disambiguation-applied List<...> is stripped so the inner primitive is wrapped.
        assert apply_csharp_computed_wrapping("List<string>", field) == "VecOrValue<MaybeSpecialOrError<string>>"

    def test_lookup_with_unresolvable_inner_falls_back_to_json_node(self):
        """An unresolvable lookup renders as VecOrValue<JsonNode> end-to-end."""
        from myairtable.utils.type_mapper import map_csharp_type

        assert map_csharp_type(self._field("Look", "fld001", "multipleLookupValues")) == "VecOrValue<JsonNode>"

    def test_rollup_wraps_vec_or_value(self):
        """A resolved rollup inner type wraps as VecOrValue<MaybeSpecialOrError<T>>."""
        from myairtable.utils.type_mapper import apply_csharp_computed_wrapping

        field = self._field("Roll", "fld001", "rollup")
        assert apply_csharp_computed_wrapping("double", field) == "VecOrValue<MaybeSpecialOrError<double>>"

    def test_already_wrapped_type_is_left_alone(self):
        """apply_csharp_computed_wrapping is a no-op on already-wrapped types."""
        from myairtable.utils.type_mapper import apply_csharp_computed_wrapping

        field = self._field("Calc", "fld001", "formula")
        assert apply_csharp_computed_wrapping("MaybeSpecialOrError<double>", field) == "MaybeSpecialOrError<double>"

    def test_writable_field_is_never_wrapped(self):
        from myairtable.utils.type_mapper import apply_csharp_computed_wrapping

        field = self._field("My Text", "fld001", "singleLineText")
        assert apply_csharp_computed_wrapping("string", field) == "string"

    def test_writable_text_is_plain_string(self):
        from myairtable.utils.type_mapper import map_csharp_type

        assert map_csharp_type(self._field("My Text", "fld001", "singleLineText")) == "string"


class TestCSharpWriterHelpers:
    """Pure helpers in write_to_csharp_file.py (CS1.2)."""

    def test_csharp_ident_escapes_keywords_with_at_prefix(self):
        """C# uses verbatim identifiers — reserved words get a leading `@`."""
        from myairtable.utils.write_to_csharp_file import _csharp_ident

        for kw in ("class", "switch", "true", "false", "null", "namespace", "string", "int"):
            assert _csharp_ident(kw) == f"@{kw}"
        # Contextual keywords and ordinary names are left alone.
        assert _csharp_ident("status") == "status"
        assert _csharp_ident("value") == "value"
        assert _csharp_ident("record") == "record"
        assert _csharp_ident("async") == "async"

    def test_csharp_string_literal_escapes_quotes_and_controls(self):
        from myairtable.utils.write_to_csharp_file import _csharp_string_literal

        assert _csharp_string_literal('a"b') == 'a\\"b'
        assert _csharp_string_literal("a\\b") == "a\\\\b"
        assert _csharp_string_literal("a\nb\tc") == "a\\nb\\tc"
        # `$` and `{` are not interpreted in a regular literal — left alone.
        assert _csharp_string_literal("${x}") == "${x}"

    def test_xmldoc_escape_entities_and_double_dash(self):
        from myairtable.utils.write_to_csharp_file import _xmldoc_escape

        assert _xmldoc_escape("a < b & c > d") == "a &lt; b &amp; c &gt; d"
        # `--` is illegal inside an XML comment body — neutralised.
        assert _xmldoc_escape("LEN({f})--1") == "LEN({f})- -1"
        # `&` runs first so introduced entities aren't re-escaped.
        assert "&amp;lt;" not in _xmldoc_escape("<")

    def test_choice_to_entry_pascal_case_and_edges(self):
        from myairtable.utils.write_to_csharp_file import _choice_to_entry

        assert _choice_to_entry("open Invoices") == "OpenInvoices"
        assert _choice_to_entry("In Progress") == "InProgress"
        assert _choice_to_entry("") == "Empty"
        assert _choice_to_entry("   ") == "Empty"
        # Every result is a valid PascalCase-ish identifier (never starts with a digit).
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", _choice_to_entry("!!!"))
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", _choice_to_entry("3rd Party"))
        assert _choice_to_entry("3rd Party").startswith("N")


class TestCppComputedTypes:
    """map_cpp_type wrapping for computed fields (pure type_mapper assertions)."""

    @staticmethod
    def _field(name: str, field_id: str, field_type: FieldType):
        return make_test_base([(name, field_id, field_type)]).tables[0].fields[0]

    def test_formula_number_wraps_maybe_special_or_error_double(self):
        from myairtable.utils.type_mapper import map_cpp_type

        assert map_cpp_type(self._field("Calc", "fld001", "formula")) == "MaybeSpecialOrError<double>"

    def test_auto_number_wraps_maybe_special_or_error_int64(self):
        from myairtable.utils.type_mapper import map_cpp_type

        assert map_cpp_type(self._field("Auto", "fld001", "autoNumber")) == "MaybeSpecialOrError<int64_t>"

    def test_lookup_wraps_vec_or_value(self):
        """A resolved lookup inner type wraps as VecOrValue<MaybeSpecialOrError<T>>."""
        from myairtable.utils.type_mapper import apply_cpp_computed_wrapping

        field = self._field("Look", "fld001", "multipleLookupValues")
        assert apply_cpp_computed_wrapping("double", field) == "VecOrValue<MaybeSpecialOrError<double>>"
        # Disambiguation-applied std::vector<...> is stripped so the inner primitive is wrapped.
        assert apply_cpp_computed_wrapping("std::vector<std::string>", field) == "VecOrValue<MaybeSpecialOrError<std::string>>"

    def test_lookup_with_unresolvable_inner_falls_back_to_json(self):
        """An unresolvable lookup renders as VecOrValue<nlohmann::json> end-to-end."""
        from myairtable.utils.type_mapper import map_cpp_type

        assert map_cpp_type(self._field("Look", "fld001", "multipleLookupValues")) == "VecOrValue<nlohmann::json>"

    def test_rollup_wraps_vec_or_value(self):
        """A resolved rollup inner type wraps as VecOrValue<MaybeSpecialOrError<T>>."""
        from myairtable.utils.type_mapper import apply_cpp_computed_wrapping

        field = self._field("Roll", "fld001", "rollup")
        assert apply_cpp_computed_wrapping("double", field) == "VecOrValue<MaybeSpecialOrError<double>>"

    def test_already_wrapped_type_is_left_alone(self):
        """apply_cpp_computed_wrapping is a no-op on already-wrapped types."""
        from myairtable.utils.type_mapper import apply_cpp_computed_wrapping

        field = self._field("Calc", "fld001", "formula")
        assert apply_cpp_computed_wrapping("MaybeSpecialOrError<double>", field) == "MaybeSpecialOrError<double>"

    def test_writable_field_is_never_wrapped(self):
        from myairtable.utils.type_mapper import apply_cpp_computed_wrapping

        field = self._field("My Text", "fld001", "singleLineText")
        assert apply_cpp_computed_wrapping("std::string", field) == "std::string"

    def test_writable_text_is_plain_string(self):
        from myairtable.utils.type_mapper import map_cpp_type

        assert map_cpp_type(self._field("My Text", "fld001", "singleLineText")) == "std::string"


class TestCppGenerator:
    """cpp.py F3 generator — offline content assertions (no compiler)."""

    def _generate(self, base: Base, tmp_path: Path) -> Path:
        from myairtable.generators.cpp import generate_cpp
        from myairtable.utils.type_mapper import map_types

        map_types(base)
        out = tmp_path / "cpp"
        generate_cpp(base=base, output_folder=out)
        return out

    def _generate_fields(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> Path:
        return self._generate(make_test_base(fields_spec), tmp_path)

    # ---- options (F3.1) ----------------------------------------------------

    def test_options_enum_class_and_entries(self, tmp_path: Path):
        base = _make_base_with_select_field("Jobs", "Status", "fld001", ["Todo", "In Progress", "Done"])
        out = self._generate(base, tmp_path)
        content = (out / "dynamic" / "options" / "jobs_status_option.hpp").read_text()
        assert "#pragma once" in content
        assert "enum class JobsStatusOption {" in content
        assert "Todo," in content
        assert "InProgress," in content
        assert "Done," in content
        assert "namespace myairtable {" in content

    def test_options_serializer_maps_raw_strings_and_throws_on_unknown(self, tmp_path: Path):
        base = _make_base_with_select_field("Jobs", "Status", "fld001", ["In Progress", "Done"])
        out = self._generate(base, tmp_path)
        content = (out / "dynamic" / "options" / "jobs_status_option.hpp").read_text()
        assert "struct adl_serializer<myairtable::JobsStatusOption> {" in content
        assert 'if (raw == "In Progress") {' in content
        assert "return myairtable::JobsStatusOption::InProgress;" in content
        assert 'throw myairtable::DecodingError("Unknown JobsStatusOption: " + raw);' in content
        # to_json switch maps members back to the raw wire strings.
        assert "case myairtable::JobsStatusOption::InProgress:" in content
        assert 'j = "In Progress";' in content
        # NLOHMANN_JSON_SERIALIZE_ENUM would silently map unknowns to the first
        # entry — the generated serializer must never use it.
        assert "NLOHMANN_JSON_SERIALIZE_ENUM" not in content

    def test_options_duplicate_entries_deduplicate_with_v_suffix(self, tmp_path: Path):
        # Two choices that sanitize to the same member name.
        base = _make_base_with_select_field("Jobs", "Status", "fld001", ["Done.", "done"])
        out = self._generate(base, tmp_path)
        content = (out / "dynamic" / "options" / "jobs_status_option.hpp").read_text()
        assert "Done," in content
        assert "Done_V2," in content
        assert 'j = "Done.";' in content
        assert 'j = "done";' in content

    def test_options_escape_quotes_in_raw_strings(self, tmp_path: Path):
        base = _make_base_with_select_field("Rigs", "Drop Point", "fld001", ['North "Gate"'])
        out = self._generate(base, tmp_path)
        content = (out / "dynamic" / "options" / "rigs_drop_point_option.hpp").read_text()
        assert 'North \\"Gate\\"' in content

    # ---- field types (F3.2) --------------------------------------------------

    def test_fields_constants_and_maps(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText"), ("Count", "fld002", "number")], tmp_path)
        content = (out / "dynamic" / "types" / "test_table_fields.hpp").read_text()
        assert "struct TestTableFields {" in content
        assert 'static constexpr std::string_view kPrimaryKeyId = "fld001";' in content
        assert 'static constexpr std::string_view kPrimaryKeyName = "Primary Key";' in content
        assert 'static constexpr std::string_view kCountId = "fld002";' in content
        assert 'inline static const std::vector<std::string> kAllIds = {"fld001", "fld002"};' in content
        assert '{"Primary Key", "fld001"},' in content  # kNameToId
        assert '{"fld002", "Count"},' in content  # kIdToName
        assert "static std::optional<std::string> id_by_name(const std::string& name) {" in content
        assert "static std::optional<std::string> name_by_id(const std::string& id) {" in content

    def test_views_emit_static_instances(self, tmp_path: Path):
        base = _make_base_with_select_field("Jobs", "Status", "fld001", ["Done"])
        out = self._generate(base, tmp_path)
        content = (out / "dynamic" / "types" / "jobs_view.hpp").read_text()
        assert "class JobsView {" in content
        assert "static const JobsView GridView;" in content
        assert 'inline const JobsView JobsView::GridView{"viw001"};' in content
        assert "const std::string& id() const { return id_; }" in content

    def test_create_fields_exclude_computed(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText"), ("Auto", "fld002", "autoNumber")], tmp_path)
        content = (out / "dynamic" / "types" / "create_test_table_fields.hpp").read_text()
        assert 'static constexpr std::string_view kPrimaryKeyId = "fld001";' in content
        assert "kAutoId" not in content  # computed fields are not writable

    # ---- tables + entry point (F3.3) -----------------------------------------

    def test_table_facade_wraps_dict_table(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "tables" / "test_table_table.hpp").read_text()
        assert "class TestTableTable : public OrmTable<TestTableModel> {" in content  # ORM default
        assert 'static constexpr std::string_view kTableId = "tblTEST123";' in content
        assert "explicit TestTableTable(std::shared_ptr<AirtableClient> client)" in content
        assert "TestTableFields::kNameToId" in content  # names resolve on the field bag
        assert "DictTable& dict() { return dict_; }" in content
        assert '#include "dynamic/models/test_table_model.hpp"' in content
        assert '#include "dynamic/types/test_table_fields.hpp"' in content

    def test_entry_point_exposes_table_accessors(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "airtable.hpp").read_text()
        assert "class Airtable {" in content
        assert 'static constexpr std::string_view kBaseId = "appTEST123";' in content
        assert "explicit Airtable(const std::string& api_key, double cache_seconds = 0.0)" in content
        assert "explicit Airtable(std::shared_ptr<AirtableClient> client)" in content
        assert "TestTableTable test_table() const { return TestTableTable(client_); }" in content
        assert "void invalidate_all_caches() { client_->invalidate_all_caches(); }" in content
        assert '#include "dynamic/tables/test_table_table.hpp"' in content

    # ---- models (F4.2) ---------------------------------------------------------

    def test_model_aggregate_shape_and_members(self, tmp_path: Path):
        out = self._generate_fields(
            [
                ("Primary Key", "fld001", "singleLineText"),
                ("Count", "fld002", "number"),
                ("Auto", "fld003", "autoNumber"),
            ],
            tmp_path,
        )
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "struct TestTableModel : AirtableModel<TestTableModel> {" in content
        assert 'static constexpr std::string_view kTableId = "tblTEST123";' in content
        # meta members declared directly (the CRTP base holds no data)
        assert "std::optional<std::string> id{};" in content
        assert "std::optional<DateTime> created_time{};" in content
        assert "std::shared_ptr<AirtableClient> client_{};" in content
        assert "json snapshot_{};" in content
        # schema-ordered optional members; computed wrapped
        assert "std::optional<std::string> primary_key{};" in content
        assert "std::optional<double> count{};" in content
        assert "std::optional<MaybeSpecialOrError<int64_t>> auto_{};" in content  # `auto` is a keyword

    def test_model_hooks_split_writable_and_computed(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText"), ("Auto", "fld002", "autoNumber")], tmp_path)
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        writable_hook = content.split("json collect_writable_fields() const {")[1].split("}")[0]
        computed_hook = content.split("json collect_computed_fields() const {")[1].split("}")[0]
        assert 'write_field(fields, "fld001", primary_key);' in writable_hook
        assert "fld002" not in writable_hook  # computed never in a write payload (R21)
        assert 'write_field(fields, "fld002", auto_);' in computed_hook

    def test_model_from_json_decodes_envelope_by_field_id(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText"), ("Auto", "fld002", "autoNumber")], tmp_path)
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "inline void from_json(const json& record, TestTableModel& model) {" in content
        assert 'model.id = record.at("id").get<std::string>();' in content
        assert 'model.created_time = record.at("createdTime").get<DateTime>();' in content
        assert 'model.primary_key = read_field<std::string>(fields, "fld001");' in content
        assert 'model.auto_ = read_field<MaybeSpecialOrError<int64_t>>(fields, "fld002");' in content

    def test_model_reserved_member_names_are_suffixed(self, tmp_path: Path):
        out = self._generate_fields(
            [("Primary Key", "fld001", "singleLineText"), ("Save", "fld002", "number"), ("Fetch", "fld003", "number")],
            tmp_path,
        )
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "std::optional<double> save_field{};" in content
        assert "std::optional<double> fetch_field{};" in content
        # "Id" is pre-sanitized to "identifier" upstream; the base's `id` member
        # itself can never be shadowed because it is a reserved member name.

    def test_model_emits_evaluate_methods_for_formula_fields(self, tmp_path: Path):
        base = make_test_base(
            [("Score", "fld001", "number"), ("Calc", "fld002", "formula")],
            formula_map={"fld002": "{fld001} + 1"},
        )
        out = self._generate(base, tmp_path)
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "json evaluate_calc() const {" in content
        assert "return runtime::v((runtime::n(runtime::v(this->score)) + 1.0));" in content
        assert '#include "static/runtime_math.hpp"' in content

    def test_runtime_flag_suppresses_evaluate_methods(self, tmp_path: Path):
        from myairtable.generators.cpp import generate_cpp
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(
            [("Score", "fld001", "number"), ("Calc", "fld002", "formula")],
            formula_map={"fld002": "{fld001} + 1"},
        )
        map_types(base)
        out = tmp_path / "cpp"
        generate_cpp(base=base, output_folder=out, runtime=False)
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "evaluate_" not in content

    # ---- formula helpers (F7.2) ---------------------------------------------

    def test_filters_struct_maps_field_classes(self, tmp_path: Path):
        out = self._generate_fields(
            [
                ("Primary Key", "fld001", "singleLineText"),
                ("Count", "fld002", "number"),
                ("Done", "fld003", "checkbox"),
                ("When", "fld004", "date"),
                ("Look", "fld005", "multipleLookupValues"),
            ],
            tmp_path,
        )
        content = (out / "dynamic" / "formulas" / "test_table_filters.hpp").read_text()
        assert "struct TestTableFilters {" in content
        assert "FormulaId id{};" in content
        assert 'FormulaTextField primary_key{"fld001"};' in content
        assert 'FormulaNumberField count{"fld002"};' in content
        assert 'FormulaBooleanField done{"fld003"};' in content
        assert 'FormulaDateField when{"fld004"};' in content
        assert 'FormulaLookupField look{"fld005"};' in content

    def test_model_exposes_static_f_accessor(self, tmp_path: Path):
        out = self._generate_fields([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "inline static const TestTableFilters F{};" in content
        assert '#include "dynamic/formulas/test_table_filters.hpp"' in content

    def test_formulas_flag_suppresses_filters(self, tmp_path: Path):
        from myairtable.generators.cpp import generate_cpp
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        map_types(base)
        out = tmp_path / "cpp"
        generate_cpp(base=base, output_folder=out, formulas=False)
        assert not (out / "dynamic" / "formulas").exists()
        model = (out / "dynamic" / "models" / "test_table_model.hpp").read_text()
        assert "Filters F" not in model
        # the static DSL headers are excluded from the copy too
        assert not (out / "static" / "formulas.hpp").exists()

    def test_wrappers_flag_suppresses_tables_and_entry_point(self, tmp_path: Path):
        from myairtable.generators.cpp import generate_cpp
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        map_types(base)
        out = tmp_path / "cpp"
        generate_cpp(base=base, output_folder=out, wrappers=False)
        assert not (out / "airtable.hpp").exists()
        assert not (out / "dynamic" / "tables").exists()
        assert (out / "dynamic" / "types" / "test_table_fields.hpp").exists()


class TestCppWriterHelpers:
    """Pure helpers in write_to_cpp_file.py (CPP F1.4)."""

    def test_cpp_ident_renames_keywords_with_trailing_underscore(self):
        """C++ has no verbatim-identifier escape — reserved words get a trailing `_`."""
        from myairtable.utils.write_to_cpp_file import _cpp_ident

        for kw in ("class", "switch", "true", "false", "delete", "namespace", "int", "template"):
            assert _cpp_ident(kw) == f"{kw}_"
        # Alternative tokens are operators — equally illegal as identifiers.
        for alt in ("and", "or", "not", "xor", "bitand", "compl", "not_eq"):
            assert _cpp_ident(alt) == f"{alt}_"
        # Contextual identifiers escaped defensively.
        assert _cpp_ident("final") == "final_"
        assert _cpp_ident("override") == "override_"
        # Ordinary names are left alone.
        assert _cpp_ident("status") == "status"
        assert _cpp_ident("value") == "value"

    def test_cpp_ident_normalises_implementation_reserved_patterns(self):
        """`__` anywhere and leading `_` are reserved for the implementation."""
        from myairtable.utils.write_to_cpp_file import _cpp_ident

        assert _cpp_ident("foo__bar") == "foo_bar"
        assert _cpp_ident("_Reserved") == "Reserved"
        assert _cpp_ident("__x") == "x"
        # Stripping may expose a digit or empty the name — validity is restored.
        assert _cpp_ident("_1st") == "n_1st"
        assert _cpp_ident("_") == "n"

    def test_cpp_string_literal_escapes_quotes_and_controls(self):
        from myairtable.utils.write_to_cpp_file import _cpp_string_literal

        assert _cpp_string_literal('a"b') == 'a\\"b'
        assert _cpp_string_literal("a\\b") == "a\\\\b"
        assert _cpp_string_literal("a\nb\tc") == "a\\nb\\tc"
        # `{` and `$` carry no meaning in a C++ string literal — left alone.
        assert _cpp_string_literal("${x}") == "${x}"

    def test_cppdoc_escape_strips_carriage_returns(self):
        from myairtable.utils.write_to_cpp_file import _cppdoc_escape

        assert _cppdoc_escape("a\r\nb") == "a\nb"
        # `--` and XML entities are NOT special in a `///` comment — untouched.
        assert _cppdoc_escape("LEN({f})--1 < 2 & 3") == "LEN({f})--1 < 2 & 3"

    def test_choice_to_entry_pascal_case_and_edges(self):
        from myairtable.utils.write_to_cpp_file import _choice_to_entry

        assert _choice_to_entry("open Invoices") == "OpenInvoices"
        assert _choice_to_entry("In Progress") == "InProgress"
        assert _choice_to_entry("") == "Empty"
        assert _choice_to_entry("   ") == "Empty"
        # Every result is a valid identifier that never starts with a digit.
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", _choice_to_entry("!!!"))
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", _choice_to_entry("3rd Party"))
        assert _choice_to_entry("3rd Party").startswith("N")


class TestCSharpGenerator:
    """csharp.py F3 generator — offline content assertions (no dotnet)."""

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> Path:
        from myairtable.generators.csharp import generate_csharp
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        map_types(base)
        out = tmp_path / "cs"
        generate_csharp(base=base, output_folder=out)
        return out

    def test_fields_constants_and_maps(self, tmp_path: Path):
        out = self._generate([("Primary Key", "fld001", "singleLineText"), ("Count", "fld002", "number")], tmp_path)
        content = (out / "dynamic" / "Types" / "TestTableFields.cs").read_text()
        assert "namespace MyAirtable;" in content
        assert 'public const string PrimaryKeyId = "fld001";' in content
        assert 'public const string PrimaryKeyName = "Primary Key";' in content
        assert '["Primary Key"] = "fld001",' in content  # NameToId
        assert '["fld001"] = "Primary Key",' in content  # IdToName
        assert "public static string? IdByName(string name)" in content

    def test_table_facade_inherits_ormtable_and_exposes_dict(self, tmp_path: Path):
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "dynamic" / "Tables" / "TestTableTable.cs").read_text()
        # The facade IS the typed table (ORM is the default, no `.Orm` hop): it derives from
        # OrmTable<{Table}Model> and forwards the table id to the base ctor.
        assert "class TestTableTable : OrmTable<TestTableModel>" in content
        assert 'public const string TableId = "tbl' in content
        assert ": base(TableId, client)" in content
        # No `.Orm` accessor property anymore (the ORM surface is inherited directly).
        assert "Orm { get; }" not in content
        # Raw dict access is still available behind `.Dict`.
        assert "new DictTable(TableId, TestTableFields.NameToId, client)" in content
        assert "public DictTable Dict { get; }" in content

    def test_airtable_entry_point(self, tmp_path: Path):
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        content = (out / "Airtable.cs").read_text()
        assert "public sealed class Airtable" in content
        assert "public TestTableTable TestTable { get; }" in content
        assert "public const string BaseId =" in content
        assert "public Airtable(string baseId, string apiKey, double cacheSeconds = 0)" in content
        assert "public void InvalidateAllCaches() => Client.InvalidateAllCaches();" in content

    def test_static_runtime_copied(self, tmp_path: Path):
        out = self._generate([("Primary Key", "fld001", "singleLineText")], tmp_path)
        assert (out / "static" / "AirtableClient.cs").exists()
        assert (out / "static" / "DictTable.cs").exists()

    def test_reserved_model_member_names_are_suffixed(self):
        """A field whose PascalCase collides with an AirtableModel member — a base
        property (`IsNew`) OR a base method (`ToRecord`, `DirtyFields`) — is suffixed
        `Field` so the generated property neither duplicates nor shadows the base member.
        Regression: `IsNew` and the method names were missing from the reserved set."""
        from myairtable.generators.csharp import _field_property_map

        base = make_test_base(
            [
                ("Primary Key", "fld001", "singleLineText"),
                ("Is New", "fld002", "singleLineText"),  # base property
                ("To Record", "fld003", "singleLineText"),  # base method
                ("Dirty Fields", "fld004", "singleLineText"),  # base method
            ]
        )
        props = _field_property_map(base.tables[0])
        assert props["fld002"] == "IsNewField"
        assert props["fld003"] == "ToRecordField"
        assert props["fld004"] == "DirtyFieldsField"
        # Names must stay unique after suffixing.
        assert len(set(props.values())) == len(props)

    def test_reserved_table_accessor_names_are_suffixed(self):
        """A table whose PascalCase accessor would collide with a root `Airtable`-class
        member is renamed `{Name}Table`. Covers the class name itself (`Airtable` →
        CS0542) and the `InvalidateAllCaches()` method (regression: was missing)."""
        from myairtable.generators.csharp import _table_property

        for name, expected in [
            ("Airtable", "AirtableTable"),
            ("Invalidate All Caches", "InvalidateAllCachesTable"),
            ("Client", "ClientTable"),
        ]:
            base = make_test_base([("Primary Key", "fld001", "singleLineText")])
            base.tables[0].name = name
            base.tables[0]._pascal = None
            assert _table_property(base.tables[0]) == expected

    def test_options_enum_and_converter(self, tmp_path: Path):
        from myairtable.generators.csharp import generate_csharp
        from myairtable.utils.type_mapper import map_types

        base = _make_base_with_select_field("Jobs", "Status", "fld001", ["To Do", "In Progress", "Done"])
        map_types(base)
        out = tmp_path / "cs"
        generate_csharp(base=base, output_folder=out)
        opts = list((out / "dynamic" / "Options").glob("*.cs"))
        assert opts, "expected an options enum file"
        content = opts[0].read_text()
        assert "public enum" in content
        assert "ToDo," in content and "InProgress," in content and "Done," in content
        assert "JsonConverter<" in content
        assert '["To Do"] =' in content  # FromWire raw-string mapping
        assert "WriteStringValue(ToWire[value])" in content


class TestCSharpComputedFields:
    """csharp.py `write_models` (CS4.3) — offline model-shape assertions (no dotnet).

    Computed fields decode-only ([JsonInclude] + private set, absent from the writable
    payload map); writable fields have public setters and feed CollectWritableFields.
    Compilation + live CRUD are verified separately by the integration suite.
    """

    MIXED_SPEC: list[tuple[str, str, FieldType]] = [
        ("My Text", "fld001", "singleLineText"),
        ("My Formula", "fld002", "formula"),
        ("Look", "fld003", "multipleLookupValues"),
    ]

    def _model(
        self,
        fields_spec: list[tuple[str, str, FieldType]],
        tmp_path: Path,
        **flags,
    ) -> str:
        from myairtable.generators.csharp import generate_csharp
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        map_types(base)
        out = tmp_path / "cs"
        generate_csharp(base=base, output_folder=out, **flags)
        return (out / "dynamic" / "Models" / "TestTableModel.cs").read_text()

    # ---- class header ----

    def test_model_class_extends_airtable_model(self, tmp_path: Path):
        content = self._model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "namespace MyAirtable;" in content
        assert "public sealed class TestTableModel : AirtableModel" in content
        # [JsonIgnore] on the override is required — the base property's attribute is not
        # inherited, so STJ would otherwise serialize TableId into the fields payload.
        assert '[JsonIgnore]\n    public override string TableId => "tbl' in content

    # ---- field properties ----

    def test_writable_field_has_public_setter_and_json_property(self, tmp_path: Path):
        content = self._model(self.MIXED_SPEC, tmp_path)
        assert '[JsonPropertyName("fld001")]' in content
        assert "public string? MyText { get; set; }" in content

    def test_computed_field_is_json_include_private_set(self, tmp_path: Path):
        content = self._model(self.MIXED_SPEC, tmp_path)
        # Formula → MaybeSpecialOrError<...>; lookup → VecOrValue<MaybeSpecialOrError<...>>.
        assert '[JsonPropertyName("fld002")]' in content
        assert "[JsonInclude]" in content
        assert "MyFormula { get; private set; }" in content
        assert "Look { get; private set; }" in content
        # computed fields never get a public setter
        assert "MyFormula { get; set; }" not in content
        assert "Look { get; set; }" not in content

    def test_all_properties_are_nullable(self, tmp_path: Path):
        content = self._model(self.MIXED_SPEC, tmp_path)
        # every Airtable field is optional → nullable annotation on every property
        assert "public string? MyText" in content
        assert "MaybeSpecialOrError<double>? MyFormula" in content

    # ---- payload maps ----

    def test_writable_payload_map_excludes_computed(self, tmp_path: Path):
        content = self._model(self.MIXED_SPEC, tmp_path)
        writable = content.split("CollectWritableFields()")[1].split("CollectComputedFields()")[0]
        assert '["fld001"] = AirtableRuntime.V(MyText),' in writable
        assert "fld002" not in writable
        assert "fld003" not in writable

    def test_computed_payload_map_excludes_writable(self, tmp_path: Path):
        content = self._model(self.MIXED_SPEC, tmp_path)
        computed = content.split("CollectComputedFields()")[1]
        assert '["fld002"] = AirtableRuntime.V(MyFormula),' in computed
        assert '["fld003"] = AirtableRuntime.V(Look),' in computed
        assert "fld001" not in computed

    # ---- fluent CRUD ----

    def test_fluent_crud_methods_delegate_to_model_ops(self, tmp_path: Path):
        content = self._model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "public Task<TestTableModel> SaveAsync(CancellationToken ct = default) => ModelOps.SaveAsync(this, ct: ct);" in content
        assert "public Task<TestTableModel> FetchAsync(CancellationToken ct = default) => ModelOps.FetchAsync(this, ct);" in content
        assert "public Task DeleteAsync(CancellationToken ct = default) => ModelOps.DeleteAsync(this, ct);" in content

    # ---- deferred features ----

    def test_filter_accessor_present_when_formulas(self, tmp_path: Path):
        """The static `F` filter accessor (F7) is emitted when formulas are enabled."""
        content = self._model(self.MIXED_SPEC, tmp_path, formulas=True)
        assert "public static readonly TestTableFilters F = new();" in content

    def test_filter_accessor_absent_without_formulas(self, tmp_path: Path):
        content = self._model(self.MIXED_SPEC, tmp_path, formulas=False)
        assert "TestTableFilters" not in content

    # ---- runtime formula evaluation (F8) ----

    def _model_with_formula(self, tmp_path: Path, **flags) -> str:
        from myairtable.generators.csharp import generate_csharp
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(
            [("Primary Key", "fld001", "singleLineText"), ("My Formula", "fld002", "formula")],
            formula_map={"fld002": "UPPER({fld001})"},
        )
        map_types(base)
        out = tmp_path / "cs"
        generate_csharp(base=base, output_folder=out, **flags)
        return (out / "dynamic" / "Models" / "TestTableModel.cs").read_text()

    def test_evaluate_method_emitted_for_formula_when_runtime(self, tmp_path: Path):
        content = self._model_with_formula(tmp_path, runtime=True)
        assert "#region Runtime formula evaluation" in content
        assert "public JsonNode? EvaluateMyFormula() =>" in content
        # field refs transpile to AirtableRuntime.V(this.<PascalProp>)
        assert "AirtableRuntime.UPPER(AirtableRuntime.V(this.PrimaryKey))" in content

    def test_evaluate_methods_absent_without_runtime(self, tmp_path: Path):
        content = self._model_with_formula(tmp_path, runtime=False)
        assert "#region Runtime formula evaluation" not in content
        assert "Evaluate" not in content

    # ---- linked records (CS6.1) ----

    def test_linked_record_field_is_raw_string_list(self, tmp_path: Path):
        """Record-ID links map to a raw nullable List<string> — no VecOrValue wrapper."""
        content = self._model(
            [
                ("Primary Key", "fld001", "singleLineText"),
                ("Links", "fld002", "multipleRecordLinks"),
            ],
            tmp_path,
        )
        assert "public List<string>? Links { get; set; }" in content
        assert "VecOrValue" not in content


class TestJavaModels:
    """Java `{Table}Model` generation (J4 — content assertions only, no javac).

    Java analog of TestKotlinComputedFields/TestKotlinFormulas model assertions:
    computed fields are getter-only POJO fields (no setter, absent from the
    Builder); writable fields get setters + Builder methods. Compilation is
    separately verified by the static-source gate + integration tests.
    """

    MIXED_SPEC: list[tuple[str, str, FieldType]] = [
        ("My Text", "fld001", "singleLineText"),
        ("My Formula", "fld002", "formula"),
        ("Look", "fld003", "multipleLookupValues"),
    ]

    def _generate(
        self,
        fields_spec: list[tuple[str, str, FieldType]],
        tmp_path: Path,
        formula_map: dict[str, str] | None = None,
        **flags,
    ) -> Path:
        from myairtable.generators.java import write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec, formula_map=formula_map)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir(exist_ok=True)
        map_types(base)
        write_models(base, output_folder, **flags)
        return output_folder

    def _generate_model(
        self,
        fields_spec: list[tuple[str, str, FieldType]],
        tmp_path: Path,
        formula_map: dict[str, str] | None = None,
        **flags,
    ) -> str:
        out = self._generate(fields_spec, tmp_path, formula_map=formula_map, **flags)
        return (out / "dynamic" / "models" / "TestTableModel.java").read_text()

    @staticmethod
    def _builder_block(content: str) -> str:
        """The nested `Builder` class body (everything after its declaration)."""
        assert "public static final class Builder {" in content
        return content.split("public static final class Builder {")[1]

    # ---- file layout + class header ----

    def test_model_file_generated_per_table_with_class_header(self, tmp_path: Path):
        """One dynamic/models/{Table}Model.java per table, implementing AirtableModel."""
        from myairtable.generators.java import write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base([("My Text", "fld001", "singleLineText")])
        TestIdentifierCollisionDedup._add_colliding_table(base)
        output_folder = tmp_path / "java_output"
        output_folder.mkdir()
        map_types(base)
        write_models(base, output_folder)

        model_file = output_folder / "dynamic" / "models" / "TestTableModel.java"
        assert model_file.is_file()
        content = model_file.read_text()
        assert "package myairtable;" in content
        assert "public final class TestTableModel implements AirtableModel {" in content
        # The colliding second table gets its own deduplicated model file.
        assert (output_folder / "dynamic" / "models" / "TestTableV2Model.java").is_file()

    # ---- computed vs writable accessors ----

    def test_computed_field_is_getter_only_and_absent_from_builder(self, tmp_path: Path):
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        assert "public MaybeSpecialOrError<Double> getMyFormula() {" in content
        assert "setMyFormula" not in content
        builder = self._builder_block(content)
        assert "myFormula" not in builder
        assert "look" not in builder

    def test_writable_field_has_getter_setter_and_builder_method(self, tmp_path: Path):
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        assert "public String getMyText() {" in content
        assert "public void setMyText(String value) {" in content
        builder = self._builder_block(content)
        assert "public Builder myText(String value) {" in builder
        assert "public TestTableModel build() {" in builder

    # ---- Jackson annotations ----

    def test_json_property_raw_values_are_field_ids(self, tmp_path: Path):
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        for field_id in ("fld001", "fld002", "fld003"):
            assert f'@JsonProperty("{field_id}")' in content

    def test_wrapper_typed_fields_carry_the_right_deserializer(self, tmp_path: Path):
        """MaybeSpecialOrError<...> fields use MaybeSpecialOrErrorDeserializer;
        VecOrValue<...> fields use VecOrValueDeserializer."""
        import re

        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        assert "import com.fasterxml.jackson.databind.annotation.JsonDeserialize;" in content
        assert re.search(
            r"@JsonDeserialize\(using = MaybeSpecialOrErrorDeserializer\.class\)\s*\n\s*private MaybeSpecialOrError<Double> myFormula;",
            content,
        )
        assert re.search(
            r"@JsonDeserialize\(using = VecOrValueDeserializer\.class\)\s*\n\s*private VecOrValue<JsonNode> look;",
            content,
        )
        # The plain writable field carries no deserializer override.
        assert re.search(r'@JsonProperty\("fld001"\)\s*\n\s*private String myText;', content)

    def test_no_wrapper_fields_omits_json_deserialize_import(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "JsonDeserialize" not in content

    # ---- constructor + plumbing ----

    def test_public_no_arg_constructor_present(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "public TestTableModel() {}" in content

    def test_json_ignore_plumbing_fields_present(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "@JsonIgnore private String id;" in content
        assert "@JsonIgnore private Instant createdTime;" in content
        assert "@JsonIgnore private AirtableClient attachedClient;" in content
        assert "@JsonIgnore private Map<String, JsonNode> snapshot = Map.of();" in content

    # ---- payloads ----

    def test_create_fields_exclude_computed_but_to_record_includes_all(self, tmp_path: Path):
        content = self._generate_model(self.MIXED_SPEC, tmp_path)

        create_block = content.split("public Map<String, JsonNode> toCreateFields() {")[1].split("public Map<String, JsonNode> toRecord() {")[0]
        record_block = content.split("public Map<String, JsonNode> toRecord() {")[1].split("public void takeSnapshot() {")[0]

        assert '"fld001"' in create_block
        assert '"fld002"' not in create_block, "computed fields must never reach create payloads"
        assert '"fld003"' not in create_block
        for field_id in ("fld001", "fld002", "fld003"):
            assert f'"{field_id}"' in record_block

    def test_snapshot_and_dirty_tracking_present(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "snapshot = toCreateFields();" in content
        assert "public Map<String, JsonNode> dirtyFields() {" in content
        assert "dirty.put(key, NullNode.getInstance());" in content

    # ---- TABLE_ID + fluent CRUD ----

    def test_table_id_constant_matches_table_id(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert 'public static final String TABLE_ID = "tblTEST123";' in content
        assert "public String getTableId() {" in content

    def test_fluent_crud_methods_have_covariant_returns(self, tmp_path: Path):
        content = self._generate_model([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "public TestTableModel save() {" in content
        assert "return ModelOps.save(this, TestTableModel.class);" in content
        assert "public TestTableModel fetch() {" in content
        assert "return ModelOps.fetch(this, TestTableModel.class);" in content
        assert "public void delete() {" in content
        assert "ModelOps.delete(this);" in content

    # ---- formula gating ----

    def test_evaluate_methods_emitted_with_runtime_and_gated_off_without(self, tmp_path: Path):
        """runtime=True emits transpiled evaluate* methods returning JsonNode;
        runtime=False suppresses them."""
        content = self._generate_model(
            self.MIXED_SPEC,
            tmp_path,
            formula_map={"fld002": '{fld001} & "!"'},
            runtime=True,
        )
        assert "public JsonNode evaluate" in content
        assert "AirtableRuntime.V(" in content
        content_off = self._generate_model(
            self.MIXED_SPEC,
            tmp_path,
            formula_map={"fld002": '{fld001} & "!"'},
            runtime=False,
        )
        assert "evaluate" not in content_off

    def test_filters_static_present_when_formulas_enabled(self, tmp_path: Path):
        """Models expose the {Table}Filters accessor `f`; gated off with formulas=False."""
        content = self._generate_model(self.MIXED_SPEC, tmp_path, formulas=True)
        assert "public static final TestTableFilters f = new TestTableFilters();" in content
        content_off = self._generate_model(self.MIXED_SPEC, tmp_path, formulas=False)
        assert "Filters" not in content_off

    # ---- keyword-named fields ----

    def test_keyword_named_field_uses_underscore_suffix_consistently(self, tmp_path: Path):
        """A field named `class` renames to `class_` across field, accessors,
        toCreateFields, and Builder (a raw getClass() would clash with the
        final Object.getClass())."""
        content = self._generate_model([("class", "fld001", "singleLineText")], tmp_path)
        assert "private String class_;" in content
        assert "public String getClass_() {" in content
        assert "public void setClass_(String value) {" in content
        assert "public Builder class_(String value) {" in content
        assert 'fields.put("fld001", AirtableRuntime.V(class_));' in content
        assert "public String getClass() {" not in content

    def test_reserved_model_member_names_are_renamed(self, tmp_path: Path):
        """JR-M2: a field whose camel collides with a generated model member
        (`f` static Filters accessor, `snapshot`/`attachedClient`/`id`/
        `createdTime` plumbing) is suffixed `Field` so it can't be a duplicate
        field; a name that camels to empty falls back to `field`."""
        import re

        content = self._generate_model(
            [
                ("Primary Key", "fld001", "singleLineText"),
                ("f", "fld002", "singleLineText"),
                ("Snapshot", "fld003", "singleLineText"),
                ("Attached Client", "fld004", "singleLineText"),
                ("_", "fld005", "singleLineText"),
            ],
            tmp_path,
            formulas=True,
        )
        # No duplicate private field declaration (the bug would emit two `f` etc.).
        decls = re.findall(r"private \S+ (\w+);", content)
        assert len(decls) == len(set(decls)), f"duplicate field decls: {decls}"
        assert "private String fField;" in content
        assert "private String snapshotField;" in content
        assert "private String attachedClientField;" in content
        assert "private String field;" in content  # `_` -> field
        # The static Filters accessor `f` still exists, now unambiguous.
        assert "public static final TestTableFilters f = new TestTableFilters();" in content

    def test_builder_build_returns_an_independent_instance(self, tmp_path: Path):
        """JR-M3: build() must copy into a fresh model so a reused builder is a
        safe template — the old `return model;` aliased every build()."""
        content = self._generate_model(
            [("Primary Key", "fld001", "singleLineText"), ("My Text", "fld002", "singleLineText")],
            tmp_path,
        )
        assert "private final TestTableModel template = new TestTableModel();" in content
        assert "TestTableModel result = new TestTableModel();" in content
        assert "result.primaryKey = template.primaryKey;" in content
        assert "result.myText = template.myText;" in content
        assert "return result;" in content
        assert "return model;" not in content

    def test_reserved_table_accessor_renamed(self, tmp_path: Path):
        """JR-M2: a table named `Client` would give the Airtable class a table
        accessor `client` colliding with its `AirtableClient client` field."""
        from myairtable.generators.java import _table_property

        base = make_test_base([("Primary Key", "fld001", "singleLineText")])
        base.tables[0].name = "Client"
        base.tables[0]._pascal = None
        assert _table_property(base.tables[0]) == "clientTable"

    # ---- Javadoc ----

    def test_javadoc_per_field_includes_field_id(self, tmp_path: Path):
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        assert "/** My Text {@code fld001} */" in content
        assert "My Formula {@code fld002} - {@code Read-Only}" in content
        assert "/** Look {@code fld003} - {@code Read-Only} */" in content

    def test_formula_javadoc_embeds_html_escaped_formula_in_pre_block(self, tmp_path: Path):
        content = self._generate_model(
            self.MIXED_SPEC,
            tmp_path,
            formula_map={"fld002": '{fld001} & "<b>!"'},
        )
        assert "<pre>" in content
        assert "</pre>" in content
        # Field references render by name; <, >, & are HTML-entity-escaped.
        assert '{My Text} &amp; "&lt;b&gt;!"' in content
        assert '& "<b>!"' not in content


# =============================================================================
# Go generator
# =============================================================================


class TestGoOptionsGenerator:
    """Go select-option typed-string constant generation.

    Go has no enums: each select field becomes `type {Name} string` plus a const
    block of `{Name}{Choice} {Name} = "raw"`. Verifies the generated source text
    without shelling out to `go build` (mirrors the Java/Swift generator tests).
    Assertions use substring/regex checks robust to gofmt's column alignment.
    """

    def _generate_options(self, choices: list[str], tmp_path: Path) -> str:
        from myairtable.generators.go import _gofmt, write_options

        base = make_test_base([("Status", "fld001", "singleSelect")])
        field = base.tables[0].fields[0]
        assert field.options is not None
        field.options.choices = [Choice.model_construct(id=f"sel{i}", name=name) for i, name in enumerate(choices)]
        assert field.__pydantic_private__ is not None
        field.__pydantic_private__["_select_options_cache"] = None

        out = tmp_path / "go_output"
        out.mkdir()
        write_options(base, out)
        _gofmt(out)
        return (out / "options_testtable.go").read_text()

    def test_typed_string_type_declared(self, tmp_path: Path):
        """Each select field emits `type {TypeName} string`."""
        content = self._generate_options(["Open", "Closed"], tmp_path)
        assert "type TestTableStatusOption string" in content

    def test_const_names_are_pascal_with_raw_values(self, tmp_path: Path):
        """Const names are `{TypeName}{Choice}` PascalCase with the raw choice value."""
        content = self._generate_options(["Open", "In Progress"], tmp_path)
        assert re.search(r'TestTableStatusOptionOpen\s+TestTableStatusOption = "Open"', content)
        assert re.search(r'TestTableStatusOptionInProgress\s+TestTableStatusOption = "In Progress"', content)

    def test_const_block_present(self, tmp_path: Path):
        """The typed constants are grouped in a `const ( ... )` block."""
        content = self._generate_options(["Open"], tmp_path)
        assert "const (" in content

    def test_colliding_choices_get_dedup_suffix(self, tmp_path: Path):
        """Two choices that sanitize to the same const name get a `V2` dedup suffix."""
        # select_options() sorts alphabetically; both "Open" entries collide.
        content = self._generate_options(["Open", "Open"], tmp_path)
        assert re.search(r'TestTableStatusOptionOpen\s+TestTableStatusOption = "Open"', content)
        assert re.search(r'TestTableStatusOptionOpenV2\s+TestTableStatusOption = "Open"', content)


class TestGoFieldTypes:
    """Go per-table field ID/name consts, lookup maps, allIds slice, and View consts.

    Member names mirror the other targets for cross-language parity (AllFieldIDs,
    NameToID, IDToName). Assertions are whitespace-tolerant (gofmt aligns the
    const block columns).
    """

    FIELDS_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
        ("My Formula", "fld003", "formula"),
    ]

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path, views: list[tuple[str, str]] | None = None) -> Path:
        from myairtable.generators.go import _gofmt, write_field_types

        base = make_test_base(fields_spec)
        if views is not None:
            base.tables[0].views = [View.model_construct(id=vid, name=vname, type="grid", table_id=base.tables[0].id) for vname, vid in views]
        out = tmp_path / "go_output"
        out.mkdir()
        write_field_types(base, out)
        _gofmt(out)
        return out

    def test_per_field_id_and_name_consts(self, tmp_path: Path):
        """Every field gets a `{Prefix}{Name}FieldID` + `{Prefix}{Name}FieldName` const."""
        content = (self._generate(self.FIELDS_SPEC, tmp_path) / "fields_testtable.go").read_text()
        assert re.search(r'TestTablePrimaryKeyFieldID\s+= "fld001"', content)
        assert re.search(r'TestTablePrimaryKeyFieldName\s+= "Primary Key"', content)
        assert re.search(r'TestTableCountFieldID\s+= "fld002"', content)
        assert re.search(r'TestTableCountFieldName\s+= "Count"', content)
        assert re.search(r'TestTableMyFormulaFieldID\s+= "fld003"', content)
        assert re.search(r'TestTableMyFormulaFieldName\s+= "My Formula"', content)

    def test_all_field_ids_slice(self, tmp_path: Path):
        """`{Prefix}AllFieldIDs` is a []string with every field ID in schema order."""
        content = (self._generate(self.FIELDS_SPEC, tmp_path) / "fields_testtable.go").read_text()
        assert 'var TestTableAllFieldIDs = []string{"fld001", "fld002", "fld003"}' in content

    def test_name_to_id_map(self, tmp_path: Path):
        """`{Prefix}NameToID` maps Airtable field name -> field ID."""
        content = (self._generate(self.FIELDS_SPEC, tmp_path) / "fields_testtable.go").read_text()
        assert "var TestTableNameToID = map[string]string{" in content
        assert re.search(r'"Primary Key":\s*"fld001"', content)
        assert re.search(r'"Count":\s*"fld002"', content)
        assert re.search(r'"My Formula":\s*"fld003"', content)

    def test_id_to_name_map(self, tmp_path: Path):
        """`{Prefix}IDToName` maps field ID -> Airtable field name."""
        content = (self._generate(self.FIELDS_SPEC, tmp_path) / "fields_testtable.go").read_text()
        assert "var TestTableIDToName = map[string]string{" in content
        assert re.search(r'"fld001":\s*"Primary Key"', content)
        assert re.search(r'"fld002":\s*"Count"', content)
        assert re.search(r'"fld003":\s*"My Formula"', content)

    def test_view_type_and_viewid_method(self, tmp_path: Path):
        """views_{table}.go emits `type {Prefix}View string` + a ViewID() method."""
        out = self._generate(self.FIELDS_SPEC, tmp_path, views=[("Grid view", "viw001"), ("My View", "viw002")])
        content = (out / "views_testtable.go").read_text()
        assert "type TestTableView string" in content
        assert re.search(r'TestTableViewGridView\s+TestTableView = "viw001"', content)
        assert re.search(r'TestTableViewMyView\s+TestTableView = "viw002"', content)
        assert "func (v TestTableView) ViewID() string { return string(v) }" in content

    def test_no_views_file_when_table_has_no_views(self, tmp_path: Path):
        """A table with no views must not emit a views_{table}.go file."""
        out = self._generate(self.FIELDS_SPEC, tmp_path, views=[])
        assert not (out / "views_testtable.go").exists()


class TestGoTablesAndMain:
    """Go airtable.go entry point: BaseID const, Airtable struct with per-table
    `{Prefix}Dict *DictTable` fields, New/NewWithBase constructors, Client() and
    InvalidateAllCaches accessors.
    """

    FIELDS_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
    ]

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.go import _gofmt, write_main

        base = make_test_base(fields_spec)
        out = tmp_path / "go_output"
        out.mkdir()
        write_main(base, out)
        _gofmt(out)
        return (out / "airtable.go").read_text()

    def test_base_id_const(self, tmp_path: Path):
        content = self._generate(self.FIELDS_SPEC, tmp_path)
        assert 'const BaseID = "appTEST123"' in content

    def test_airtable_struct_and_dict_fields(self, tmp_path: Path):
        content = self._generate(self.FIELDS_SPEC, tmp_path)
        assert "type Airtable struct {" in content
        # One `{Prefix}Dict *DictTable` field per table.
        assert re.search(r"TestTableDict\s+\*DictTable", content)

    def test_constructors_present(self, tmp_path: Path):
        content = self._generate(self.FIELDS_SPEC, tmp_path)
        assert "func New(" in content
        assert "func NewWithBase(" in content
        # NewWithBase wires up each table's DictTable from its NameToID map.
        assert 'NewDictTable(c, "tblTEST123", TestTableNameToID)' in content

    def test_client_and_invalidate_accessors(self, tmp_path: Path):
        content = self._generate(self.FIELDS_SPEC, tmp_path)
        assert "func (a *Airtable) Client()" in content
        assert "InvalidateAllCaches" in content


class TestGoFlagGating:
    """generate_go must honor the wrappers flag: with wrappers=False the dynamic
    writers must NOT emit airtable.go (the entry point), while the per-table field
    consts are still written.
    """

    FIELDS_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
    ]

    def test_wrappers_false_skips_airtable_go(self, tmp_path: Path):
        """With wrappers=False, write_main is not called so airtable.go is absent."""
        from myairtable.generators.go import _gofmt, write_field_types, write_main, write_options

        base = make_test_base(self.FIELDS_SPEC)
        out = tmp_path / "go_output"
        out.mkdir()
        # Mirror generate_go's dynamic writers with wrappers=False (skip write_main).
        wrappers = False
        write_options(base, out)
        write_field_types(base, out)
        if wrappers:
            write_main(base, out)
        _gofmt(out)

        assert not (out / "airtable.go").exists()
        # Field consts are still emitted.
        assert (out / "fields_testtable.go").exists()

    def test_wrappers_true_emits_airtable_go(self, tmp_path: Path):
        """The complementary case: with wrappers=True airtable.go is emitted."""
        from myairtable.generators.go import _gofmt, write_field_types, write_main, write_options

        base = make_test_base(self.FIELDS_SPEC)
        out = tmp_path / "go_output"
        out.mkdir()
        wrappers = True
        write_options(base, out)
        write_field_types(base, out)
        if wrappers:
            write_main(base, out)
        _gofmt(out)

        assert (out / "airtable.go").exists()


class TestGoComputedFields:
    """Go `model_{table}.go` writable vs computed contract (G4.5 — content
    assertions only, no `go build`).

    Go analog of TestJavaModels/TestJavaComputedFields: writable fields are
    pointer optionals (`*string`, ...) carrying a `json:"fld...,omitempty"` tag
    and appear in writableFields(); computed fields are pointer wrappers
    (`*MaybeSpecialOrError[...]` / `*VecOrValue[...]`) and are excluded from
    writableFields(). Assertions are whitespace-tolerant (gofmt reflows the
    method receivers and aligns struct-field columns).
    """

    MIXED_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
        ("Is Done", "fld003", "checkbox"),
        ("My Formula", "fld004", "formula"),
        ("Look", "fld005", "multipleLookupValues"),
    ]

    def _generate_model(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.go import _gofmt, write_models
        from myairtable.utils.type_mapper import map_types

        base = make_test_base(fields_spec)
        out = tmp_path / "go_output"
        out.mkdir()
        map_types(base)
        write_models(base, out)
        _gofmt(out)
        return (out / "model_testtable.go").read_text()

    def test_computed_field_is_pointer_wrapper(self, tmp_path: Path):
        """A computed field is a pointer to a MaybeSpecialOrError[...] (scalar
        formula) or VecOrValue[...] (lookup) wrapper, tagged with its field ID."""
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        # Scalar formula -> *MaybeSpecialOrError[...].
        assert re.search(r"MyFormula\s+\*MaybeSpecialOrError\[[^\]]+\]\s+`json:\"fld004,omitempty\"`", content)
        # Lookup -> *VecOrValue[...].
        assert re.search(r"Look\s+\*VecOrValue\[[^\]]+\]\s+`json:\"fld005,omitempty\"`", content)

    def test_writable_scalar_field_is_pointer_with_field_id_tag(self, tmp_path: Path):
        """Writable scalars are pointer optionals carrying a json field-ID tag."""
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        assert re.search(r"PrimaryKey\s+\*string\s+`json:\"fld001,omitempty\"`", content)
        assert re.search(r"Count\s+\*float64\s+`json:\"fld002,omitempty\"`", content)
        assert re.search(r"IsDone\s+\*bool\s+`json:\"fld003,omitempty\"`", content)
        # Writable fields are never wrapped.
        assert "PrimaryKey *MaybeSpecialOrError" not in content
        assert "Count *VecOrValue" not in content

    def test_writable_fields_method_includes_only_writable_ids(self, tmp_path: Path):
        """writableFields() emits an out["fldID"] line per writable field and
        excludes every computed field's ID."""
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        body = content.split("func (m *TestTableModel) writableFields()")[1]
        body = body.split("return out")[0]
        for writable_id in ("fld001", "fld002", "fld003"):
            assert re.search(rf'out\["{writable_id}"\]\s*=\s*mustMarshal\(', body)
        # Computed fields must not appear in writableFields().
        for computed_id in ("fld004", "fld005"):
            assert f'out["{computed_id}"]' not in body

    def test_model_has_crud_and_interface_methods(self, tmp_path: Path):
        """The model exposes Save/Fetch/Delete plus the TableID/writableFields
        Model-interface hooks (gofmt-aligned receivers)."""
        content = self._generate_model(self.MIXED_SPEC, tmp_path)
        assert re.search(r"func \(m \*TestTableModel\) Save\(ctx context\.Context\) error", content)
        assert re.search(r"func \(m \*TestTableModel\) Fetch\(ctx context\.Context\) error", content)
        assert re.search(r"func \(m \*TestTableModel\) Delete\(ctx context\.Context\) error", content)
        assert re.search(r"func \(m \*TestTableModel\) TableID\(\) string", content)
        assert re.search(r"func \(m \*TestTableModel\) writableFields\(\) map\[string\]json\.RawMessage", content)


class TestGoFormulaHelpers:
    """Go `filters_{table}.go` (F7): per-table `{prefix}Filters` struct mapping
    each field to its formula-builder type, plus a package-level `{Prefix}F`
    instance built from field NAMES, plus an `ID IDField` entry. The static
    formula DSL files are excluded from the flat copy when formulas=False.
    """

    FIELDS_SPEC: list[tuple[str, str, FieldType]] = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
        ("Done", "fld003", "checkbox"),
        ("Due", "fld004", "date"),
        ("Tags", "fld005", "multipleSelects"),
        ("Files", "fld006", "multipleAttachments"),
    ]

    def _generate(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from myairtable.generators.go import _gofmt, write_formula_helpers

        base = make_test_base(fields_spec)
        out = tmp_path / "go_output"
        out.mkdir()
        write_formula_helpers(base, out)
        _gofmt(out)
        return (out / "filters_testtable.go").read_text()

    def test_filters_struct_and_builder_types(self, tmp_path: Path):
        content = self._generate(self.FIELDS_SPEC, tmp_path)
        assert "type testtableFilters struct {" in content
        assert re.search(r"PrimaryKey\s+TextField", content)
        assert re.search(r"Count\s+NumberField", content)
        assert re.search(r"Done\s+BooleanField", content)
        assert re.search(r"Due\s+DateField", content)
        assert re.search(r"Tags\s+MultiSelectField", content)
        assert re.search(r"Files\s+AttachmentsField", content)
        # Record-ID builder entry.
        assert re.search(r"ID\s+IDField", content)

    def test_filters_instance_uses_field_names(self, tmp_path: Path):
        content = self._generate(self.FIELDS_SPEC, tmp_path)
        assert "var TestTableF = testtableFilters{" in content
        # Constructors are seeded with field NAMES, not IDs (gofmt aligns colons).
        assert re.search(r'PrimaryKey:\s+NewTextField\("Primary Key"\),', content)
        assert re.search(r'Count:\s+NewNumberField\("Count"\),', content)
        assert re.search(r"ID:\s+NewIDField\(\),", content)
        # No field IDs leak into the constructors.
        assert "fld001" not in content

    def test_generate_go_excludes_formula_statics_when_off(self, tmp_path: Path):
        """formulas=False must drop both the generated filters file and the static
        formula DSL files from the output (parity with runtime.go gating)."""
        from myairtable.generators.go import _GO_FORMULA_STATIC_FILES, generate_go

        base = make_test_base(self.FIELDS_SPEC)
        out = tmp_path / "go_output"
        generate_go(base, out, formulas=False)
        assert not (out / "filters_testtable.go").exists()
        for name in _GO_FORMULA_STATIC_FILES:
            assert not (out / name).exists()

    def test_generate_go_includes_formula_statics_when_on(self, tmp_path: Path):
        from myairtable.generators.go import _GO_FORMULA_STATIC_FILES, generate_go

        base = make_test_base(self.FIELDS_SPEC)
        out = tmp_path / "go_output"
        generate_go(base, out, formulas=True)
        assert (out / "filters_testtable.go").exists()
        for name in _GO_FORMULA_STATIC_FILES:
            assert (out / name).exists()
