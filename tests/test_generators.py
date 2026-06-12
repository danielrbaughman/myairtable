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


# region Select Option Name<->ID Mapping Tests


class TestSelectOptionNameIdMappings:
    """singleSelect / multipleSelects fields must emit name<->id maps alongside
    their Option Literal / list. Callers use these so JSON they write uses the
    stable Airtable option id, surviving option renames."""

    CHOICES = ["Open", "Completed", "Closed"]

    def test_python_emits_name_id_and_id_name_mappings(self, tmp_path: Path):
        from src.generators.python import write_types

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
        from src.generators.typescript import write_types

        base = _make_base_with_select_field("Jobs", "Status (Billing)", "fldBILLING", self.CHOICES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "jobs.ts").read_text()

        assert "JobsStatusBillingOptionNameIdMapping: Record<JobsStatusBillingOption, string>" in content
        assert '"Open": "sel000"' in content
        assert "JobsStatusBillingOptionIdNameMapping: Record<string, JobsStatusBillingOption>" in content
        assert '"sel000": "Open"' in content

    def test_javascript_emits_name_id_and_id_name_mappings(self, tmp_path: Path):
        from src.generators.javascript import write_types

        base = _make_base_with_select_field("Jobs", "Status (Billing)", "fldBILLING", self.CHOICES)
        write_types(base, tmp_path)

        content = (tmp_path / "dynamic" / "types" / "jobs.js").read_text()

        assert "JobsStatusBillingOptionNameIdMapping" in content
        assert '"Open": "sel000"' in content
        assert "JobsStatusBillingOptionIdNameMapping" in content
        assert '"sel000": "Open"' in content

    def test_rust_emits_id_and_from_id_helpers(self, tmp_path: Path):
        from src.generators.rust import write_options

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
        from src.generators.typescript import write_models

        base = make_test_base(fields_spec)
        out = tmp_path / "ts_output"
        out.mkdir(parents=True, exist_ok=True)
        write_models(base, out, formulas=False, zod=False)
        return _read_generated_model(out, "typescript")

    def _formula(self, fields_spec: list[tuple[str, str, FieldType]], tmp_path: Path) -> str:
        from src.generators.typescript import write_formula_helpers

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
        from src.generators.javascript import write_models

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
        from src.generators.python import write_models

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

    def test_tables_forwards_orm_methods_directly(self, tmp_path: Path):
        """ORM is the default: `get` / `create` / `update` / `delete` live on
        the table struct as overloaded methods (no `.orm` prefix, no
        `getOne`/`createOne` variants). Matches TS/Py pattern."""
        fields_spec = [("Primary Key", "fld001", "singleLineText")]
        out = self._generate(fields_spec, tmp_path)
        content = (out / "dynamic" / "tables" / "TestTableTable.swift").read_text()

        # Overloaded names — no `One`/`Many` suffixes.
        assert "public func get(_ recordId: String)" in content
        assert "public func get(_ recordIds: [String])" in content
        assert "public func get(_ query: AirtableQuery" in content
        assert "public func create(" in content
        assert "public func update(" in content
        assert "public func upsert(" in content
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
        from src.generators.swift import write_models
        from src.utils.type_mapper import map_types

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
    `@Observable` annotation, CodingKeys mapping to field IDs, and that the
    designated init + `encode(to:)` both restrict to writable fields. This is
    the Swift analog of TestTypeScriptComputedFields.
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


class TestSwiftFlagGating:
    """generate_swift must honor formulas/wrappers/runtime flags (myairtable-2odn).

    Mirrors the Rust generator's gating: disabling a flag suppresses the
    corresponding static + dynamic output instead of emitting it anyway.
    """

    FIELDS_SPEC = [
        ("Primary Key", "fld001", "singleLineText"),
        ("Count", "fld002", "number"),
    ]

    def _generate(self, tmp_path: Path, **flags) -> Path:
        from src.generators.swift import generate_swift
        from src.utils.type_mapper import map_types

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
