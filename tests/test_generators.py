"""Tests for computed field read-only property generation in TS, JS, and Python generators."""

from pathlib import Path

from src.meta import Base, Field, Options, Table
from src.meta_types import FieldType


def make_test_base(fields_spec: list[tuple[str, str, FieldType]]) -> Base:
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

    for field_name, field_id, field_type in fields_spec:
        field = Field.model_construct(
            id=field_id,
            name=field_name,
            type=field_type,
            description=None,
            options=Options.model_construct(
                formula=None,
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
                result=None,
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

    def test_computed_field_has_getter_only(self, tmp_path: Path):
        """A formula field should have a getter but NO setter."""
        content = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert "get myFormula()" in content
        assert "set myFormula(" not in content

    def test_writable_field_has_getter_and_setter(self, tmp_path: Path):
        """A singleLineText field should have both getter and setter."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "get myText()" in content
        assert "set myText(" in content

    def test_all_computed_types_getter_only(self, tmp_path: Path):
        """Every computed field type should generate getter-only."""
        fields_spec = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(COMPUTED_TYPES)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(COMPUTED_TYPES):
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

        # Computed: getter only
        assert "get myFormula()" in content
        assert "set myFormula(" not in content
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

    def test_computed_field_has_getter_only(self, tmp_path: Path):
        """A formula field should have a getter but NO setter."""
        content = self._generate([("My Formula", "fld001", "formula")], tmp_path)
        assert "get myFormula()" in content
        assert "set myFormula(" not in content

    def test_writable_field_has_getter_and_setter(self, tmp_path: Path):
        """A singleLineText field should have both getter and setter."""
        content = self._generate([("My Text", "fld001", "singleLineText")], tmp_path)
        assert "get myText()" in content
        assert "set myText(" in content

    def test_all_computed_types_getter_only(self, tmp_path: Path):
        """Every computed field type should generate getter-only."""
        fields_spec = [(f"Field {i}", f"fld{i:03d}", ft) for i, ft in enumerate(COMPUTED_TYPES)]
        content = self._generate(fields_spec, tmp_path)

        for i, ft in enumerate(COMPUTED_TYPES):
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
