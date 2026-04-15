from __future__ import annotations

import re

from core.models import ExampleCandidate, QueryAnalysis, RepairResult, RetrievalHit
from core.sql_generator import SQLGenerator


CODE_BLOCK_PATTERN = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE)


class SQLRepairer:
    def __init__(self, generator: SQLGenerator):
        self.generator = generator

    def repair(
        self,
        question: str,
        failed_sql: str,
        error_message: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
        example_candidates: tuple[ExampleCandidate, ...],
        prompt: str,
    ) -> RepairResult | None:
        cleaned_sql = self._sanitize_sql(failed_sql)
        if cleaned_sql and cleaned_sql != failed_sql.strip():
            return RepairResult(
                sql=cleaned_sql,
                strategy="sanitize_sql",
                message="移除了 SQL 代码块标记，并补齐了结尾分号。",
            )

        if not cleaned_sql:
            regenerated = self.generator.generate(question, analysis, retrievals, example_candidates, prompt)
            if regenerated is None:
                return None
            return RepairResult(
                sql=regenerated.sql,
                strategy="regenerate_empty_sql",
                message="原始 SQL 为空，已根据问题重新生成。",
            )

        if any(keyword in error_message.lower() for keyword in ("no such column", "no such table", "ambiguous column")):
            regenerated = self.generator.generate(question, analysis, retrievals, example_candidates, prompt)
            if regenerated is not None and regenerated.sql != cleaned_sql:
                return RepairResult(
                    sql=regenerated.sql,
                    strategy="regenerate_from_schema",
                    message=f"执行错误指向 schema 不匹配，已重新生成 SQL: {error_message}",
                )

        if "SQL 解析失败" in error_message and not cleaned_sql.endswith(";"):
            return RepairResult(
                sql=f"{cleaned_sql};",
                strategy="append_semicolon",
                message="检测到 SQL 解析失败，已尝试补齐结尾分号。",
            )

        regenerated = self.generator.generate(question, analysis, retrievals, example_candidates, prompt)
        if regenerated is not None and regenerated.sql != cleaned_sql:
            return RepairResult(
                sql=regenerated.sql,
                strategy="fallback_regenerate",
                message=f"根据失败信息回退到安全模板重生成 SQL: {error_message}",
            )

        return None

    def _sanitize_sql(self, sql: str) -> str:
        cleaned = CODE_BLOCK_PATTERN.sub("", sql.strip())
        select_match = re.search(r"(select\b.*)", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if select_match is not None:
            cleaned = select_match.group(1).strip()

        if cleaned and not cleaned.endswith(";"):
            cleaned = f"{cleaned};"
        return cleaned