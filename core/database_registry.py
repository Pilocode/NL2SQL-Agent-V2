from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from core.models import DatabaseProfile, ExampleCandidate, TableProfile
from core.schema_loader import load_demo_questions, load_schema_catalog, load_semantic_layer


@dataclass(frozen=True)
class DatabaseContext:
    profile: DatabaseProfile
    schema_catalog: tuple[TableProfile, ...]
    semantic_layer: dict
    examples: tuple[ExampleCandidate, ...]


def load_database_registry(settings: Settings) -> dict[str, DatabaseContext]:
    registry: dict[str, DatabaseContext] = {}

    chinook_examples = load_demo_questions(settings.demo_questions_path)
    chinook_semantic_layer = load_semantic_layer(settings.semantic_layer_path)
    chinook_metadata = _read_json(settings.schema_metadata_path) if settings.schema_metadata_path.exists() else {}
    chinook_display_name = str(chinook_metadata.get("database_name") or settings.database_path.stem)
    chinook_description = str(
        chinook_metadata.get("description")
        or (
            "数字音乐商店示例数据库，适合客户、订单、歌曲、专辑和艺人分析。"
            if settings.database_path.name.lower().startswith("chinook")
            else f"本地 SQLite 数据库 {chinook_display_name}。"
        )
    )
    chinook_route_hints = _build_route_hints(chinook_metadata, chinook_examples)
    if not chinook_route_hints:
        chinook_route_hints = ("音乐", "歌曲", "专辑", "艺人", "客户", "订单", "流派", "播放列表")
    chinook_profile = DatabaseProfile(
        database_id="chinook",
        display_name=chinook_display_name,
        description=chinook_description,
        dialect="sqlite",
        database_path=settings.database_path,
        route_hints=chinook_route_hints,
    )
    registry[chinook_profile.database_id] = DatabaseContext(
        profile=chinook_profile,
        schema_catalog=load_schema_catalog(settings.schema_metadata_path, settings.semantic_layer_path),
        semantic_layer=chinook_semantic_layer,
        examples=chinook_examples,
    )

    if not settings.enable_spider_rag:
        return registry

    spider_examples_by_db = _load_spider_examples(settings.spider_examples_path)
    if not settings.spider_metadata_dir.exists():
        return registry

    for metadata_path in sorted(settings.spider_metadata_dir.glob("*.json")):
        database_id = metadata_path.stem
        metadata = _read_json(metadata_path)
        semantic_layer_path = settings.spider_semantic_layer_dir / f"{database_id}.json"
        semantic_layer = load_semantic_layer(semantic_layer_path)
        database_path = settings.spider_database_root / "database" / database_id / f"{database_id}.sqlite"

        description = str(metadata.get("description") or f"Spider 数据库 {database_id} 的 schema 与训练样例骨架。")
        route_hints = _build_route_hints(metadata, spider_examples_by_db.get(database_id, ()))
        profile = DatabaseProfile(
            database_id=database_id,
            display_name=str(metadata.get("database_name") or database_id),
            description=description,
            dialect=str(metadata.get("dialect") or "sqlite"),
            database_path=database_path if database_path.exists() else None,
            route_hints=route_hints,
        )
        registry[database_id] = DatabaseContext(
            profile=profile,
            schema_catalog=load_schema_catalog(metadata_path, semantic_layer_path),
            semantic_layer=semantic_layer,
            examples=spider_examples_by_db.get(database_id, ()),
        )

    return registry


def _build_route_hints(metadata: dict, examples: tuple[ExampleCandidate, ...]) -> tuple[str, ...]:
    hints = set()
    hints.add(str(metadata.get("database_name") or "").lower())
    hints.update(_extract_description_terms(str(metadata.get("description") or "")))
    for tag in metadata.get("domain_tags", []):
        if str(tag).strip():
            hints.add(str(tag).strip().lower())

    for table in metadata.get("tables", [])[:8]:
        table_name = str(table.get("name") or "").strip().lower()
        if table_name:
            hints.add(table_name)
        hints.update(_extract_description_terms(str(table.get("description") or "")))
        for column in table.get("columns", [])[:12]:
            column_name = str(column.get("name") or "").strip().lower()
            if column_name:
                hints.add(column_name)
            hints.update(_extract_description_terms(str(column.get("description") or "")))

    for example in examples[:10]:
        for tag in example.tags:
            if tag.strip():
                hints.add(tag.strip().lower())

    return tuple(sorted(hints))


def _load_spider_examples(path: Path) -> dict[str, tuple[ExampleCandidate, ...]]:
    if not path.exists():
        return {}

    payload = _read_json(path)
    grouped: dict[str, list[ExampleCandidate]] = {}
    for item in payload.get("questions", []):
        database_id = str(item.get("database_id") or "").strip()
        if not database_id:
            continue
        grouped.setdefault(database_id, []).append(
            ExampleCandidate(
                question=item["question"],
                sql=item["sql"],
                explanation=item.get("explanation", "Spider 训练样例"),
                tags=tuple(item.get("tags", [])),
                database_id=database_id,
                source=item.get("source", "spider_train"),
            )
        )
    return {database_id: tuple(items) for database_id, items in grouped.items()}


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _extract_description_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in str(text or "").replace("，", " ").replace("。", " ").replace("、", " ").split():
        lowered = token.strip().lower()
        if lowered and len(lowered) >= 2:
            terms.add(lowered)
    return terms