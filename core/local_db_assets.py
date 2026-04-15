from __future__ import annotations

import json
import sqlite3
from json import JSONDecodeError
from pathlib import Path
import re

from app.config import Settings
from core.llm_client import OpenAICompatibleLLM


ROOT_DIR = Path(__file__).resolve().parent.parent
LOCAL_DATABASE_DIR = ROOT_DIR / "data" / "local_dbs"
LOCAL_METADATA_DIR = ROOT_DIR / "data" / "processed" / "local_dbs" / "metadata"
LOCAL_SEMANTIC_DIR = ROOT_DIR / "data" / "processed" / "local_dbs" / "semantic_layers"
LOCAL_EXAMPLES_DIR = ROOT_DIR / "data" / "processed" / "local_dbs" / "examples"
SUMMARY_TERM_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}")
SUMMARY_STOPWORDS = {"记录", "相关", "数据", "信息", "字段", "主要", "核心", "用于", "包括", "保存", "描述", "内容", "表", "数据库"}


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def list_local_database_files() -> tuple[Path, ...]:
    _ensure_dirs()
    paths = list(LOCAL_DATABASE_DIR.glob("*.sqlite")) + list(LOCAL_DATABASE_DIR.glob("*.db"))
    return tuple(sorted(paths, key=lambda item: item.name.lower()))


def get_local_asset_paths(database_path: Path) -> dict[str, Path]:
    asset_key = database_path.name.replace(".", "_")
    return {
        "metadata": LOCAL_METADATA_DIR / f"{asset_key}.json",
        "semantic": LOCAL_SEMANTIC_DIR / f"{asset_key}.json",
        "examples": LOCAL_EXAMPLES_DIR / f"{asset_key}.json",
    }


def ensure_local_database_assets(database_path: Path, settings: Settings | None = None) -> dict[str, Path]:
    asset_paths = get_local_asset_paths(database_path)
    if all(path.exists() for path in asset_paths.values()):
        return asset_paths
    return build_local_database_assets(database_path, settings=settings)


def refresh_database_assets(
    database_path: Path,
    metadata_path: Path,
    semantic_layer_path: Path,
    examples_path: Path | None = None,
) -> dict[str, Path]:
    database_path = database_path.resolve()
    metadata_path = metadata_path.resolve()
    semantic_layer_path = semantic_layer_path.resolve()
    resolved_examples_path = examples_path.resolve() if examples_path is not None else None
    _ensure_asset_parent_dirs(metadata_path, semantic_layer_path, resolved_examples_path)

    existing_metadata = _read_json_if_exists(metadata_path)
    existing_semantic = _read_json_if_exists(semantic_layer_path)
    existing_examples = _read_json_if_exists(resolved_examples_path) if resolved_examples_path is not None else {}

    connection = sqlite3.connect(database_path)
    try:
        cursor = connection.cursor()
        tables = [_fetch_table_profile(cursor, table_name) for table_name in _fetch_tables(cursor)]
    finally:
        connection.close()

    existing_table_descriptions, existing_column_descriptions = _collect_existing_descriptions(
        existing_metadata,
        existing_semantic,
    )
    database_description = str(
        existing_metadata.get("description")
        or existing_semantic.get("database_summary")
        or _fallback_database_description(database_path.stem, tables)
    )
    source_payload = existing_metadata.get("source")
    if not isinstance(source_payload, dict) or not source_payload:
        source_payload = {
            "name": "local-upload" if _is_local_database(database_path) else "sqlite-runtime",
            "database_file": _to_relative_path(database_path),
        }

    table_descriptions: dict[str, str] = {}
    column_descriptions: dict[str, str] = {}
    for table in tables:
        table_descriptions[table["name"]] = existing_table_descriptions.get(
            table["name"],
            _fallback_table_description(table),
        )
        table["description"] = table_descriptions[table["name"]]

        for column in table.get("columns", []):
            column_key = f"{table['name']}.{column['name']}"
            column_descriptions[column_key] = existing_column_descriptions.get(
                column_key,
                _fallback_column_description(table["name"], column),
            )
            column["description"] = column_descriptions[column_key]

    metadata_payload = dict(existing_metadata)
    metadata_payload.update(
        {
            "database_name": str(existing_metadata.get("database_name") or database_path.stem),
            "dialect": str(existing_metadata.get("dialect") or "sqlite"),
            "description": database_description,
            "source": source_payload,
            "tables": tables,
        }
    )
    if "domain_tags" not in metadata_payload and _is_local_database(database_path):
        metadata_payload["domain_tags"] = [database_path.stem.lower()]

    semantic_payload = dict(existing_semantic)
    semantic_payload.update(
        {
            "database_summary": database_description,
            "table_descriptions": table_descriptions,
            "column_descriptions": column_descriptions,
            "summary_terms": {
                "database": _extract_summary_terms(database_description),
                "tables": {name: _extract_summary_terms(description) for name, description in table_descriptions.items()},
                "columns": {name: _extract_summary_terms(description) for name, description in column_descriptions.items()},
            },
        }
    )
    semantic_payload.setdefault("table_aliases", {})
    semantic_payload.setdefault("column_aliases", {})
    examples_payload = existing_examples if isinstance(existing_examples, dict) else {"questions": []}

    metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    semantic_layer_path.write_text(json.dumps(semantic_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if resolved_examples_path is not None:
        resolved_examples_path.write_text(json.dumps(examples_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "metadata": metadata_path,
        "semantic": semantic_layer_path,
        "examples": resolved_examples_path,
    }


def refresh_local_database_assets(database_path: Path) -> dict[str, Path]:
    _ensure_dirs()
    database_path = database_path.resolve()
    asset_paths = get_local_asset_paths(database_path)
    if not all(path.exists() for path in asset_paths.values()):
        return build_local_database_assets(database_path)

    return refresh_database_assets(
        database_path,
        asset_paths["metadata"],
        asset_paths["semantic"],
        asset_paths["examples"],
    )


def build_local_database_assets(database_path: Path, settings: Settings | None = None) -> dict[str, Path]:
    _ensure_dirs()
    database_path = database_path.resolve()
    asset_paths = get_local_asset_paths(database_path)

    connection = sqlite3.connect(database_path)
    try:
        cursor = connection.cursor()
        tables = [_fetch_table_profile(cursor, table_name) for table_name in _fetch_tables(cursor)]
    finally:
        connection.close()

    summary_bundle = _generate_schema_summaries(database_path.stem, tables, settings)
    database_description = summary_bundle["database_description"]
    table_descriptions = summary_bundle["table_descriptions"]
    column_descriptions = summary_bundle["column_descriptions"]
    for table in tables:
        table["description"] = table_descriptions.get(table["name"], _fallback_table_description(table))
        for column in table.get("columns", []):
            column_key = f"{table['name']}.{column['name']}"
            column["description"] = column_descriptions.get(column_key, _fallback_column_description(table["name"], column))

    metadata_payload = {
        "database_name": database_path.stem,
        "dialect": "sqlite",
        "description": database_description,
        "source": {
            "name": "local-upload",
            "database_file": _to_relative_path(database_path),
        },
        "domain_tags": [database_path.stem.lower()],
        "tables": tables,
    }
    semantic_payload = {
        "table_aliases": {},
        "column_aliases": {},
        "database_summary": database_description,
        "table_descriptions": table_descriptions,
        "column_descriptions": column_descriptions,
        "summary_terms": {
            "database": _extract_summary_terms(database_description),
            "tables": {name: _extract_summary_terms(description) for name, description in table_descriptions.items()},
            "columns": {name: _extract_summary_terms(description) for name, description in column_descriptions.items()},
        },
    }
    examples_payload = {
        "questions": [],
    }

    asset_paths["metadata"].write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    asset_paths["semantic"].write_text(json.dumps(semantic_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    asset_paths["examples"].write_text(json.dumps(examples_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return asset_paths


def rebuild_all_local_database_assets(settings: Settings | None = None) -> tuple[Path, ...]:
    databases = list_local_database_files()
    for database_path in databases:
        build_local_database_assets(database_path, settings=settings)
    return databases


def delete_local_database_assets(database_path: Path) -> None:
    for path in get_local_asset_paths(database_path).values():
        if path.exists():
            path.unlink()


def _fetch_tables(cursor: sqlite3.Cursor) -> list[str]:
    rows = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _fetch_table_profile(cursor: sqlite3.Cursor, table_name: str) -> dict:
    row_count = cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
    columns = cursor.execute(f"PRAGMA table_info([{table_name}])").fetchall()
    foreign_keys = cursor.execute(f"PRAGMA foreign_key_list([{table_name}])").fetchall()

    primary_keys = [column[1] for column in columns if column[5] > 0]
    foreign_key_map = {
        item[3]: {"table": item[2], "column": item[4]}
        for item in foreign_keys
    }

    return {
        "name": table_name,
        "row_count": row_count,
        "primary_keys": primary_keys,
        "foreign_keys": [
            {
                "column": column_name,
                "references": reference,
            }
            for column_name, reference in foreign_key_map.items()
        ],
        "columns": [
            {
                "name": column[1],
                "type": column[2] or "TEXT",
                "nullable": column[3] == 0,
            }
            for column in columns
        ],
    }


def _generate_schema_summaries(database_name: str, tables: list[dict], settings: Settings | None) -> dict[str, object]:
    fallback_database_description = _fallback_database_description(database_name, tables)
    fallback_table_descriptions = {
        table["name"]: _fallback_table_description(table)
        for table in tables
    }
    fallback_column_descriptions = {
        f"{table['name']}.{column['name']}": _fallback_column_description(table["name"], column)
        for table in tables
        for column in table.get("columns", [])
    }
    if settings is None:
        return {
            "database_description": fallback_database_description,
            "table_descriptions": fallback_table_descriptions,
            "column_descriptions": fallback_column_descriptions,
        }

    llm = OpenAICompatibleLLM(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_generation_model or settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        enable_thinking=False,
    )
    if not llm.is_available():
        return {
            "database_description": fallback_database_description,
            "table_descriptions": fallback_table_descriptions,
            "column_descriptions": fallback_column_descriptions,
        }

    table_payload = [
        {
            "name": table["name"],
            "row_count": table["row_count"],
            "primary_keys": table.get("primary_keys", []),
            "columns": [
                {
                    "name": column["name"],
                    "type": column["type"],
                    "sample_role": _fallback_column_description(table["name"], column),
                }
                for column in table.get("columns", [])[:12]
            ],
            "sample_role": _fallback_table_description(table),
        }
        for table in tables
    ]
    response = llm.chat(
        system_prompt=(
            "你是数据库文档助手。"
            "请基于数据库名、表名、主键、字段名和行数，生成三级中文摘要：数据库简介、表简介、字段角色简介。"
            "只输出 JSON，不要添加 Markdown。"
        ),
        user_prompt=(
            f"数据库名：{database_name}\n"
            "请返回如下 JSON 结构："
            '{"database_description":"数据库简介","tables":[{"name":"表名","description":"一句话表简介","columns":[{"name":"字段名","description":"一句话字段角色简介"}]}]}'
            "。数据库简介控制在 18 到 40 个中文字符；表简介控制在 16 到 36 个中文字符；字段角色简介控制在 8 到 24 个中文字符。"
            "优先描述业务对象、主用途和字段角色，不要输出与结构无关的话。\n"
            f"表结构摘要：{json.dumps(table_payload, ensure_ascii=False)}"
        ),
        temperature=0.1,
        max_tokens=2200,
        model=settings.llm_generation_model or settings.llm_model,
        enable_thinking=False,
    )
    if response is None:
        return {
            "database_description": fallback_database_description,
            "table_descriptions": fallback_table_descriptions,
            "column_descriptions": fallback_column_descriptions,
        }

    parsed = _parse_json_object(response.content)
    items = parsed.get("tables", []) if isinstance(parsed, dict) else []
    ai_descriptions: dict[str, str] = {}
    ai_column_descriptions: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        if name and description:
            ai_descriptions[name] = description
        for column in item.get("columns", []):
            if not isinstance(column, dict):
                continue
            column_name = str(column.get("name") or "").strip()
            column_description = str(column.get("description") or "").strip()
            if name and column_name and column_description:
                ai_column_descriptions[f"{name}.{column_name}"] = column_description

    database_description = str(parsed.get("database_description") or "").strip() if isinstance(parsed, dict) else ""
    return {
        "database_description": database_description or fallback_database_description,
        "table_descriptions": {
            table["name"]: ai_descriptions.get(table["name"], fallback_table_descriptions[table["name"]])
            for table in tables
        },
        "column_descriptions": {
            f"{table['name']}.{column['name']}": ai_column_descriptions.get(
                f"{table['name']}.{column['name']}",
                fallback_column_descriptions[f"{table['name']}.{column['name']}"]
            )
            for table in tables
            for column in table.get("columns", [])
        },
    }


def _parse_json_object(content: str) -> dict:
    payload = content.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        payload = "\n".join(line for line in lines if not line.strip().startswith("```"))
    try:
        result = json.loads(payload)
        return result if isinstance(result, dict) else {}
    except JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            result = json.loads(payload[start : end + 1])
            return result if isinstance(result, dict) else {}
        except JSONDecodeError:
            return {}


def _read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except JSONDecodeError:
        return {}


def _collect_existing_descriptions(metadata_payload: dict, semantic_payload: dict) -> tuple[dict[str, str], dict[str, str]]:
    table_descriptions = {
        str(name): str(description)
        for name, description in (semantic_payload.get("table_descriptions") or {}).items()
        if str(name).strip() and str(description).strip()
    }
    column_descriptions = {
        str(name): str(description)
        for name, description in (semantic_payload.get("column_descriptions") or {}).items()
        if str(name).strip() and str(description).strip()
    }

    for table in metadata_payload.get("tables", []):
        table_name = str(table.get("name") or "").strip()
        if table_name and str(table.get("description") or "").strip() and table_name not in table_descriptions:
            table_descriptions[table_name] = str(table.get("description") or "")
        for column in table.get("columns", []):
            column_name = str(column.get("name") or "").strip()
            column_key = f"{table_name}.{column_name}"
            if table_name and column_name and str(column.get("description") or "").strip() and column_key not in column_descriptions:
                column_descriptions[column_key] = str(column.get("description") or "")

    return table_descriptions, column_descriptions


def _fallback_table_description(table: dict) -> str:
    column_names = [str(column.get("name") or "") for column in table.get("columns", [])]
    preview = "、".join(name for name in column_names[:3] if name)
    if preview:
        return f"记录 {table['name']} 相关数据，核心字段包括 {preview}。"
    return f"记录 {table['name']} 相关数据。"


def _fallback_database_description(database_name: str, tables: list[dict]) -> str:
    top_tables = "、".join(table["name"] for table in tables[:3])
    if top_tables:
        return f"SQLite 数据库 {database_name}，主要包含 {top_tables} 等业务数据。"
    return f"SQLite 数据库 {database_name}。"


def _fallback_column_description(table_name: str, column: dict) -> str:
    column_name = str(column.get("name") or "")
    lowered = column_name.lower()
    if lowered == "id" or lowered.endswith("_id"):
        return f"用于标识或关联 {table_name} 记录。"
    if any(term in lowered for term in ("name", "title")):
        return f"表示 {table_name} 的名称或标题信息。"
    if any(term in lowered for term in ("date", "time", "year", "month")):
        return f"表示 {table_name} 的时间或周期信息。"
    if any(term in lowered for term in ("amount", "price", "total", "salary", "cost")):
        return f"表示 {table_name} 的金额或数值指标。"
    return f"记录 {table_name} 中 {column_name} 的业务属性。"


def _extract_summary_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in SUMMARY_TERM_PATTERN.finditer((text or "").lower()):
        token = match.group(0).strip()
        if not token or token in SUMMARY_STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def _ensure_dirs() -> None:
    LOCAL_DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_asset_parent_dirs(*paths: Path | None) -> None:
    for path in paths:
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)


def _is_local_database(path: Path) -> bool:
    return path.is_relative_to(LOCAL_DATABASE_DIR.resolve())


def _to_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)