from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_SPIDER_DIR = ROOT_DIR / "data" / "raw" / "spider"
TABLES_PATH = RAW_SPIDER_DIR / "tables.json"
TRAIN_PATH = RAW_SPIDER_DIR / "train_spider.json"
DEV_PATH = RAW_SPIDER_DIR / "dev.json"
DATABASE_DIR = RAW_SPIDER_DIR / "database"
OUTPUT_METADATA_DIR = ROOT_DIR / "data" / "processed" / "spider" / "metadata"
OUTPUT_SEMANTIC_DIR = ROOT_DIR / "data" / "processed" / "spider" / "semantic_layers"
OUTPUT_EXAMPLES_PATH = ROOT_DIR / "data" / "processed" / "spider" / "examples.json"


def main() -> None:
    if not TABLES_PATH.exists():
        raise FileNotFoundError(f"Spider tables.json not found: {TABLES_PATH}")

    OUTPUT_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)

    tables_payload = _read_json(TABLES_PATH)
    for database in tables_payload:
        metadata = _build_metadata(database)
        semantic_layer = _build_semantic_layer(metadata)
        database_id = metadata["database_name"]

        (OUTPUT_METADATA_DIR / f"{database_id}.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (OUTPUT_SEMANTIC_DIR / f"{database_id}.json").write_text(
            json.dumps(semantic_layer, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    examples = _build_examples()
    OUTPUT_EXAMPLES_PATH.write_text(json.dumps({"questions": examples}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Spider metadata written to {OUTPUT_METADATA_DIR}")
    print(f"Spider examples written to {OUTPUT_EXAMPLES_PATH}")


def _build_metadata(database: dict) -> dict:
    database_id = database["db_id"]
    table_names = database["table_names_original"]
    column_names = database["column_names_original"]
    column_types = database["column_types"]
    primary_key_indexes = set(database.get("primary_keys", []))
    foreign_key_pairs = database.get("foreign_keys", [])
    row_counts = _read_row_counts(database_id, table_names)

    foreign_key_map: dict[int, list[dict[str, str]]] = defaultdict(list)
    for source_index, target_index in foreign_key_pairs:
        source_table_index, source_column_name = column_names[source_index]
        target_table_index, target_column_name = column_names[target_index]
        foreign_key_map[source_table_index].append(
            {
                "column": source_column_name,
                "references": {
                    "table": table_names[target_table_index],
                    "column": target_column_name,
                },
            }
        )

    table_columns: dict[int, list[dict[str, object]]] = defaultdict(list)
    for column_index, ((table_index, column_name), column_type) in enumerate(zip(column_names, column_types)):
        if table_index < 0:
            continue
        table_columns[table_index].append(
            {
                "name": column_name,
                "type": column_type.upper(),
                "nullable": True,
                "is_primary_key": column_index in primary_key_indexes,
            }
        )

    tables = []
    for table_index, table_name in enumerate(table_names):
        columns = table_columns.get(table_index, [])
        primary_keys = [column["name"] for column in columns if column["is_primary_key"]]
        tables.append(
            {
                "name": table_name,
                "row_count": row_counts.get(table_name, 0),
                "primary_keys": primary_keys,
                "foreign_keys": foreign_key_map.get(table_index, []),
                "columns": [
                    {
                        "name": column["name"],
                        "type": column["type"],
                        "nullable": column["nullable"],
                    }
                    for column in columns
                ],
            }
        )

    return {
        "database_name": database_id,
        "dialect": "sqlite",
        "description": f"Spider 数据库 {database_id} 的自动生成 metadata。",
        "domain_tags": [database_id.replace("_", " ")],
        "tables": tables,
    }


def _build_semantic_layer(metadata: dict) -> dict:
    table_aliases = {}
    column_aliases = {}
    for table in metadata["tables"]:
        table_name = table["name"]
        table_aliases[table_name] = [table_name.lower(), table_name.replace("_", " ").lower()]
        for column in table["columns"]:
            key = f"{table_name}.{column['name']}"
            column_aliases[key] = [column["name"].lower(), column["name"].replace("_", " ").lower()]

    return {
        "table_aliases": table_aliases,
        "column_aliases": column_aliases,
        "metric_templates": [],
    }


def _build_examples() -> list[dict]:
    examples: list[dict] = []
    for path, source in ((TRAIN_PATH, "spider_train"), (DEV_PATH, "spider_dev")):
        if not path.exists():
            continue
        for item in _read_json(path):
            examples.append(
                {
                    "database_id": item["db_id"],
                    "question": item["question"],
                    "sql": item["query"],
                    "explanation": "Spider 训练/验证样例",
                    "tags": [item["db_id"].lower()],
                    "source": source,
                }
            )
    return examples


def _read_row_counts(database_id: str, table_names: list[str]) -> dict[str, int]:
    database_path = DATABASE_DIR / database_id / f"{database_id}.sqlite"
    if not database_path.exists():
        return {table_name: 0 for table_name in table_names}

    counts = {table_name: 0 for table_name in table_names}
    with sqlite3.connect(database_path) as connection:
        cursor = connection.cursor()
        for table_name in table_names:
            try:
                counts[table_name] = cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            except sqlite3.DatabaseError:
                counts[table_name] = 0
    return counts


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    main()