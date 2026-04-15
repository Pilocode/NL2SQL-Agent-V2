from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.query_analyzer import QueryAnalyzer
from core.schema_loader import load_schema_catalog, load_semantic_layer
from core.schema_retriever import SchemaRetriever


BENCHMARK_PATH = ROOT_DIR / "data" / "evals" / "retrieval_summary_benchmark.json"
LOCAL_METADATA_DIR = ROOT_DIR / "data" / "processed" / "local_dbs" / "metadata"
LOCAL_SEMANTIC_DIR = ROOT_DIR / "data" / "processed" / "local_dbs" / "semantic_layers"
TOP_K_VALUES = (1, 3, 5)


def main() -> None:
    benchmark = _read_json(BENCHMARK_PATH)
    cases = benchmark.get("cases", [])
    if not cases:
        raise RuntimeError("benchmark cases are empty")

    baseline_hits = {k: 0 for k in TOP_K_VALUES}
    enhanced_hits = {k: 0 for k in TOP_K_VALUES}
    total = len(cases)
    case_rows: list[dict[str, object]] = []

    for case in cases:
        database = str(case["database"])
        question = str(case["question"])
        expected_tables = tuple(str(item) for item in case["expected_tables"])

        metadata_path = LOCAL_METADATA_DIR / f"{database}_sqlite.json"
        semantic_path = LOCAL_SEMANTIC_DIR / f"{database}_sqlite.json"
        schema_catalog = load_schema_catalog(metadata_path, semantic_path)
        semantic_layer = load_semantic_layer(semantic_path)

        baseline_schema = _strip_schema_summaries(schema_catalog)
        baseline_semantic = _strip_semantic_summaries(semantic_layer)

        baseline_analysis = QueryAnalyzer(baseline_semantic).analyze(question)
        enhanced_analysis = QueryAnalyzer(semantic_layer).analyze(question)

        baseline_hits_list = SchemaRetriever(baseline_schema, baseline_semantic).retrieve(question, baseline_analysis.tokens, analysis=baseline_analysis, limit=max(TOP_K_VALUES))
        enhanced_hits_list = SchemaRetriever(schema_catalog, semantic_layer).retrieve(question, enhanced_analysis.tokens, analysis=enhanced_analysis, limit=max(TOP_K_VALUES))

        baseline_rank = _best_rank(expected_tables, tuple(hit.table_name for hit in baseline_hits_list))
        enhanced_rank = _best_rank(expected_tables, tuple(hit.table_name for hit in enhanced_hits_list))

        for k in TOP_K_VALUES:
            if baseline_rank is not None and baseline_rank <= k:
                baseline_hits[k] += 1
            if enhanced_rank is not None and enhanced_rank <= k:
                enhanced_hits[k] += 1

        case_rows.append(
            {
                "database": database,
                "question": question,
                "expected": list(expected_tables),
                "baseline_top5": [hit.table_name for hit in baseline_hits_list[:5]],
                "enhanced_top5": [hit.table_name for hit in enhanced_hits_list[:5]],
                "baseline_rank": baseline_rank,
                "enhanced_rank": enhanced_rank,
            }
        )

    result = {
        "description": benchmark.get("description", ""),
        "total_cases": total,
        "metrics": {
            "baseline": _build_metric_block(baseline_hits, total),
            "enhanced": _build_metric_block(enhanced_hits, total),
        },
        "cases": case_rows,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _build_metric_block(hit_counts: dict[int, int], total: int) -> dict[str, dict[str, float | int]]:
    block: dict[str, dict[str, float | int]] = {}
    for k, count in hit_counts.items():
        block[f"top_{k}"] = {
            "hits": count,
            "total": total,
            "accuracy": round(count / total, 4),
        }
    return block


def _best_rank(expected_tables: tuple[str, ...], ranked_tables: tuple[str, ...]) -> int | None:
    expected_lookup = {name.lower() for name in expected_tables}
    for index, table_name in enumerate(ranked_tables, start=1):
        if table_name.lower() in expected_lookup:
            return index
    return None


def _strip_schema_summaries(schema_catalog):
    stripped_tables = []
    for table in schema_catalog:
        stripped_columns = [replace(column, description="") for column in table.columns]
        stripped_tables.append(replace(table, description="", columns=tuple(stripped_columns)))
    return tuple(stripped_tables)


def _strip_semantic_summaries(semantic_layer: dict) -> dict:
    stripped = dict(semantic_layer)
    stripped.pop("database_summary", None)
    stripped.pop("table_descriptions", None)
    stripped.pop("column_descriptions", None)
    stripped.pop("summary_terms", None)
    return stripped


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    main()