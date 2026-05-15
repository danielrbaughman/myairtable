"""Tests for computed field read-only property generation in TS, JS, and Python generators."""

import ast
from pathlib import Path

from src.meta import Base, Choice, Field, Options, Result, Table, View
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
        from src.generators.python import write_types

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
        from src.generators.typescript import write_types

        base = _make_base_with_select_field("Rig Assignments", "Vehicle Drop Point", "fld001", self.CHOICES_WITH_QUOTES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "rigAssignments.ts").read_text()

        # Each quoted option should appear as \"Bucyrus, OH\" inside the double-quoted string literal
        assert '"\\"Bucyrus, OH\\""' in content
        assert '"\\"Springfield, IL\\""' in content
        # The plain option (no internal quotes) should still appear as-is
        assert '"Bucyrus, OH"' in content

    def test_javascript_emits_escaped_const_array(self, tmp_path: Path):
        from src.generators.javascript import write_types

        base = _make_base_with_select_field("Rig Assignments", "Vehicle Drop Point", "fld001", self.CHOICES_WITH_QUOTES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "rigAssignments.js").read_text()

        assert '"\\"Bucyrus, OH\\""' in content
        assert '"\\"Springfield, IL\\""' in content
        assert '"Bucyrus, OH"' in content


# endregion
