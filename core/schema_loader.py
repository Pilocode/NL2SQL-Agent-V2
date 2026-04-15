from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.models import ColumnProfile, ExampleCandidate, ForeignKey, TableProfile


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=8)
def load_schema_document(metadata_path: Path) -> dict:
    if not metadata_path.exists():
        return {}
    return _read_json(metadata_path)


@lru_cache(maxsize=1)
def load_semantic_layer(semantic_layer_path: Path) -> dict:
    if not semantic_layer_path.exists():
        return {}
    return _read_json(semantic_layer_path)


@lru_cache(maxsize=1)
def load_schema_catalog(metadata_path: Path, semantic_layer_path: Path) -> tuple[TableProfile, ...]:
    metadata = load_schema_document(metadata_path)
    semantic_layer = load_semantic_layer(semantic_layer_path)
    table_aliases = semantic_layer.get("table_aliases", {})
    column_aliases = semantic_layer.get("column_aliases", {})

    tables: list[TableProfile] = []
    for table in metadata.get("tables", []):
        foreign_key_lookup = {
            item["column"]: ForeignKey(
                column=item["column"],
                references_table=item["references"]["table"],
                references_column=item["references"]["column"],
            )
            for item in table.get("foreign_keys", [])
        }

        columns: list[ColumnProfile] = []
        for column in table.get("columns", []):
            alias_key = f"{table['name']}.{column['name']}"
            columns.append(
                ColumnProfile(
                    name=column["name"],
                    data_type=column["type"],
                    nullable=column["nullable"],
                    is_primary_key=column["name"] in table.get("primary_keys", []),
                    aliases=tuple(column_aliases.get(alias_key, [])),
                    description=str(column.get("description") or ""),
                    foreign_key=foreign_key_lookup.get(column["name"]),
                )
            )

        tables.append(
            TableProfile(
                name=table["name"],
                row_count=table["row_count"],
                columns=tuple(columns),
                aliases=tuple(table_aliases.get(table["name"], [])),
                description=str(table.get("description") or ""),
            )
        )

    return tuple(tables)


@lru_cache(maxsize=1)
def load_demo_questions(demo_questions_path: Path) -> tuple[ExampleCandidate, ...]:
    if not demo_questions_path.exists():
        return ()
    payload = _read_json(demo_questions_path)
    return tuple(
        ExampleCandidate(
            question=item["question"],
            sql=item["sql"],
            explanation=item["explanation"],
            tags=tuple(item.get("tags", [])),
            database_id=item.get("database_id", "chinook"),
            source=item.get("source", "local_demo"),
        )
        for item in payload.get("questions", [])
    )


def clear_schema_loader_caches() -> None:
    load_schema_document.cache_clear()
    load_semantic_layer.cache_clear()
    load_schema_catalog.cache_clear()
    load_demo_questions.cache_clear()
