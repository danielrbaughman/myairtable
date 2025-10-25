# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MyAirtable is a code generator that creates type-safe Python and TypeScript bindings for Airtable bases. It fetches metadata from the Airtable API and generates strongly-typed models, ORM classes, table abstractions, and formula helpers.

## Development Commands

### Python Development

- Generate metadata: `uv run python main.py meta output/`
- Export to CSV: `uv run python main.py csv output/`
- Generate Python types: `uv run python main.py py output/`
- Run playground: `uv run python playground.py`

### TypeScript Development

- Build: `yarn build` or `npx tsc`
- Build and run playground: `yarn playground`
- Lint: `yarn lint` or `eslint .`
- Format: `yarn format` or `prettier --write "**/*.{ts,js,md,yaml,yml,json}"`

### Environment Setup

Requires `.env` file with:

- `AIRTABLE_API_KEY`: Your Airtable API key
- `AIRTABLE_BASE_ID`: The base ID to generate code for

## Architecture

### Core Generator Modules (`src/`)

- **`meta.py`**: Fetches Airtable metadata via API, sorts tables and fields alphabetically
- **`python.py`**: Main Python code generation orchestrator
  - Generates types, dicts (TypedDict wrappers), ORM models (pyairtable), Pydantic models, tables, formula helpers
  - Creates multiple representations: field names, field IDs, property names, view names/IDs
  - Handles computed fields (formulas, rollups, lookups) with read-only flags
- **`typescript.py`**: TypeScript code generation (currently commented out in main.py CLI)
  - Similar structure to Python generator but outputs TypeScript interfaces and classes
- **`helpers.py`**: Shared utilities for both generators
  - Property name sanitization and transformation (snake_case, camelCase, CamelCase)
  - Custom property name resolution from CSV files
  - Type mapping helpers for complex Airtable field types
  - Duplicate property name detection
- **`csv.py`**: Exports metadata to CSV for customizing property names
- **`airtable_meta_types.py`**: Type definitions for Airtable metadata API responses

### Code Generation Flow

1. Fetch base metadata from Airtable API (tables, fields, views)
2. Build field registry and detect naming conflicts
3. Generate type definitions (Literals, TypedDicts, field/view mappings)
4. Generate ORM models (pyairtable) and Pydantic models with validation
5. Generate table abstractions (`.dict`, `.orm`, `.model` accessors)
6. Generate formula helpers (type-safe field references for formulas)
7. Generate main class (base-level accessor for all tables)
8. Copy static files (base classes, helpers) to output

### Output Structure (`output/`)

Generated code is split into:

- **`dynamic/`**: Auto-generated, table-specific code
  - `types.py`: Field options, field/view types, TypedDicts
  - `dicts.py`: RecordDict wrappers (Create, Update, Read)
  - `orm_models.py`: PyAirtable ORM models with validation
  - `models.py`: Pydantic models with type safety
  - `tables.py`: Table classes with `.dict`, `.orm`, `.model` interfaces
  - `formula.py`: Type-safe formula field helpers
  - `airtable_main.py`: Main `Airtable()` class
- **`static/`**: Copied from `static/python/` or `static/typescript/`
  - Base classes and helpers that don't change per base

### Static Files (`static/`)

Template files that are copied to `output/static/` during generation:

- **Python**: Base model classes, table abstractions, formula helpers, special types
- **TypeScript**: Similar structure with Airtable.js integration

### Property Name Customization

After running `csv` command, edit `output/fields.csv` or `output/tables.csv` to customize generated property names. The generator will use custom names on subsequent runs unless `--fresh` flag is used.

## Key Implementation Details

### Type Mapping

- Handles complex nested Airtable types (formulas referencing rollups, lookups of lookups)
- Computed fields (formulas, rollups, lookups, createdTime, etc.) are marked read-only
- Select options generate typed Literals for type safety
- Linked records map to other table's ORM models

### Field Validation

- Detects invalid fields using Airtable's `isValid` metadata flag
- Warns about unhandled field types that default to `Any`
- Detects duplicate property names across fields within a table

### Property Name Sanitization

- Converts special characters to words (e.g., `?` → `is_`, `&` → `and`, `$` → `dollar`)
- Handles leading numbers (e.g., `1st` → `first`, `123` → `n_123`)
- Avoids reserved names (`id` → `identifier`, `created_time` → `created_at_time`)

### Multiple Model Interfaces

Each table supports three access patterns:

- `.dict`: Works with TypedDict RecordDicts (pyairtable raw format)
- `.orm`: PyAirtable ORM models (active record pattern)
- `.model`: Pydantic models (validation + serialization)

## Linting and Formatting

- Python: Ruff configured in `pyproject.toml` (excludes `output/` directory)
- TypeScript: ESLint configured in `eslint.config.mts`
- Formatting: Prettier configured in `.prettierrc` (excludes generated code via `.prettierignore`)

## Notes

- TypeScript generation exists but is disabled in the main CLI (`main.py:60-67`)
- Recent commits show work on field naming improvements and duplicate detection
- The playground files (`playground.py`, `playground.ts`) demonstrate basic usage patterns
