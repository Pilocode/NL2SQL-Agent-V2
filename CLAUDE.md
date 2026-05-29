# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Run the Streamlit app
python -m streamlit run app/main.py

# Run all tests
python -m pytest

# Run core pipeline tests
python -m pytest tests/test_sql_pipeline.py tests/test_operation_modes.py

# Build Chinook schema metadata
python scripts/generate_metadata.py

# Create sample local SQLite databases
python scripts/create_sample_dbs.py
python scripts/create_library_demo_db.py
```

No linter or formatter is configured in this repo.

## Architecture

### Pipeline flow

The system runs an 8-stage streaming pipeline defined in `app/orchestrator.py`. Each stage produces `StageUpdate` events consumed by the Streamlit UI:

1. **Analysis** — classify intent (DML/DDL/unsupported/irrelevant), extract keywords
2. **Analysis gate** — short-circuit for unsupported (e.g. `DROP DATABASE`) or irrelevant (e.g. weather) queries
3. **Semantic thinking** — resolve fuzzy terms like "popular", "classic"
4. **SQL generation** — LLM-first, falls back to rule-based + few-shot examples
5. **Validation** — `sqlglot` parse check + operation mode boundary check (DML vs DDL)
6. **DDL confirmation** — only for DDL mode; pauses for user confirmation in the UI before execution
7. **Execution** — run SQL against the target SQLite database
8. **Answer** — convert results to natural language

### LLM fallback: every stage degrades gracefully

When no `NL2SQL_API_KEY` / `OPENAI_API_KEY` / `DASHSCOPE_API_KEY` is set, **every agent** (analysis, thinking, generation, answer) falls back to rule-based implementations. The app is fully functional without an LLM — it uses keyword matching, local rules, and example retrieval instead. This is a deliberate design choice for classroom demos where API keys may not be available.

### Multi-database support

`DatabaseRouter` (`core/database_router.py`) routes queries to the best-matching database based on keyword overlap. `DatabaseRegistry` loads Chinook (always) plus optional Spider databases. Users can upload SQLite files through the UI or place them in `data/local_dbs/`; the system auto-builds metadata, semantic layers, and examples for each.

### Data classes

All models in `core/models.py` use `@dataclass(frozen=True)`. State updates use `dataclasses.replace()` to create new instances. This keeps the pipeline stages decoupled — each stage receives an immutable snapshot and returns a new one.

### Schema context system

Three layers of context feed into SQL generation, not just raw schema:

- **Schema metadata** (`data/processed/schema_metadata.json`) — table/column names, types, descriptions
- **Semantic layer** (`data/processed/semantic_layer.json`) — business terms, synonyms, common aggregations
- **Few-shot examples** (`data/processed/demo_questions.json`) — question→SQL pairs used when LLM is unavailable

`SchemaRetriever` scores and ranks relevant tables/columns for each query. This trio is what makes the rule-based fallback produce reasonable SQL.

### SQL repair is disabled

The repair stage (`core/sql_repairer.py`) exists but is **commented out in the main pipeline**. When generation or validation fails, the pipeline terminates rather than attempting repair. This is noted in the README.

### Configuration

`app/config.py` defines a frozen `Settings` dataclass. All values come from env vars with a priority chain:

- API key: `NL2SQL_API_KEY` → `OPENAI_API_KEY` → `DASHSCOPE_API_KEY`
- Base URL: `NL2SQL_BASE_URL` → `OPENAI_BASE_URL` → auto-detected from DashScope presence
- Model: `NL2SQL_MODEL` → `OPENAI_MODEL` → `WRITINGTUTOR_VLM_MODEL` → DashScope default

When `DASHSCOPE_API_KEY` is present, the base URL auto-switches to `https://dashscope.aliyuncs.com/compatible-mode/v1` and thinking mode (`llm_enable_thinking`) defaults to enabled. Each pipeline stage can use a different model via `NL2SQL_ANALYSIS_MODEL`, `NL2SQL_THINKING_MODEL`, etc. — all fall back to the default model if unset.

### Image OCR

Image upload uses `pytesseract` (local OCR engine). Requires Tesseract OCR to be installed on the system:

- **Windows**: Download from https://github.com/UB-Mannheim/tesseract/wiki (install with Chinese Simplified language pack)
- Verify: `tesseract --version` should work in terminal

### Testing

Tests use `unittest.TestCase` (not pytest fixtures). There is no `pytest.ini` or `conftest.py`. Tests are designed to run without an LLM — they test rule-based paths and operation mode gating.
