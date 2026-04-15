from __future__ import annotations

import re

from core.models import ColumnProfile, QueryAnalysis, RetrievalHit, TableProfile


SUMMARY_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}")


class SchemaRetriever:
    def __init__(self, schema_catalog: tuple[TableProfile, ...], semantic_layer: dict | None = None):
        self.schema_catalog = schema_catalog
        self.semantic_layer = semantic_layer or {}
        self.metric_templates = tuple(self.semantic_layer.get("metric_templates", []))

    def retrieve(
        self,
        question: str,
        tokens: tuple[str, ...],
        analysis: QueryAnalysis | None = None,
        limit: int = 6,
    ) -> tuple[RetrievalHit, ...]:
        normalized_question = question.lower()
        hits: list[RetrievalHit] = []
        for table in self.schema_catalog:
            score = 0
            matched_terms: list[str] = []
            reasons: list[str] = []
            matched_columns: list[ColumnProfile] = []

            for alias in (table.name, *table.aliases):
                alias_lower = alias.lower()
                if alias_lower and alias_lower in normalized_question:
                    increment = 8 if alias == table.name else 6
                    score += increment
                    matched_terms.append(alias)
                    reasons.append(f"表命中: {alias}")

            for column in table.columns:
                column_hit = False
                for alias in (column.name, *column.aliases):
                    alias_lower = alias.lower()
                    if alias_lower and alias_lower in normalized_question:
                        increment = 4 if alias == column.name else 3
                        score += increment
                        matched_terms.append(alias)
                        reasons.append(f"字段命中: {alias}")
                        column_hit = True
                if column_hit:
                    matched_columns.append(column)

            token_overlap = self._token_overlap(table, tokens)
            if token_overlap:
                score += token_overlap
                reasons.append(f"关键词重合: +{token_overlap}")

            summary_boost, summary_reasons, summary_columns = self._summary_boost(table, tokens, normalized_question)
            if summary_boost:
                score += summary_boost
                reasons.extend(summary_reasons)
                matched_columns.extend(summary_columns)

            semantic_boost, semantic_reasons = self._semantic_boost(table, normalized_question, analysis)
            if semantic_boost:
                score += semantic_boost
                reasons.extend(semantic_reasons)

            if score <= 0:
                continue

            hits.append(
                RetrievalHit(
                    table_name=table.name,
                    score=score,
                    matched_terms=tuple(dict.fromkeys(matched_terms)),
                    reasons=tuple(dict.fromkeys(reasons)),
                    row_count=table.row_count,
                    columns=tuple(matched_columns[:5] or table.columns[:5]),
                )
            )

        hits.sort(key=lambda item: (-item.score, item.table_name))
        return tuple(hits[:limit])

    def _token_overlap(self, table: TableProfile, tokens: tuple[str, ...]) -> int:
        if not tokens:
            return 0

        candidate_terms = {table.name.lower(), *(alias.lower() for alias in table.aliases)}
        candidate_terms.update(self._extract_terms(table.description))
        for column in table.columns:
            candidate_terms.add(column.name.lower())
            candidate_terms.update(alias.lower() for alias in column.aliases)
            candidate_terms.update(self._extract_terms(column.description))

        overlap = sum(1 for token in tokens if token in candidate_terms)
        return overlap * 2

    def _summary_boost(
        self,
        table: TableProfile,
        tokens: tuple[str, ...],
        normalized_question: str,
    ) -> tuple[int, list[str], list[ColumnProfile]]:
        score = 0
        reasons: list[str] = []
        matched_columns: list[ColumnProfile] = []
        table_description = table.description.lower()

        matched_table_terms = [token for token in tokens if len(token) >= 2 and token in table_description]
        if matched_table_terms:
            score += min(6, len(matched_table_terms) * 2)
            reasons.append(f"表简介匹配: {matched_table_terms[0]}")

        for column in table.columns:
            column_description = column.description.lower()
            matched_column_terms = [token for token in tokens if len(token) >= 2 and token in column_description]
            if matched_column_terms:
                score += min(4, len(matched_column_terms) * 2)
                reasons.append(f"字段角色匹配: {column.name}")
                matched_columns.append(column)

        if table_description and table.name.lower() not in normalized_question and any(term in normalized_question for term in self._extract_terms(table.description)[:2]):
            score += 1
            reasons.append("表简介语义相关")

        return score, reasons, matched_columns

    def _extract_terms(self, text: str) -> tuple[str, ...]:
        if not text:
            return ()
        terms: list[str] = []
        for match in SUMMARY_TOKEN_PATTERN.finditer(text.lower()):
            token = match.group(0).strip()
            if not token or token in terms:
                continue
            terms.append(token)
        return tuple(terms)

    def _semantic_boost(
        self,
        table: TableProfile,
        normalized_question: str,
        analysis: QueryAnalysis | None,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        for metric in self.metric_templates:
            metric_name = str(metric.get("name", "")).lower()
            metric_table = metric.get("table")
            metric_column = metric.get("column")
            if not metric_name:
                continue
            if metric_name in normalized_question or (analysis is not None and metric_name in analysis.metric_hints):
                if metric_table == table.name:
                    score += 6
                    reasons.append(f"指标模板匹配: {metric_name}")
                if metric_column and any(column.name == metric_column for column in table.columns):
                    score += 2
                    reasons.append(f"指标字段匹配: {metric_column}")

        if analysis is None:
            return score, reasons

        for hint in analysis.entity_hints:
            hint_lower = hint.lower()
            if hint_lower == table.name.lower() or hint_lower in {alias.lower() for alias in table.aliases}:
                score += 4
                reasons.append(f"实体提示匹配: {hint}")

            matched_column_names = [column.name for column in table.columns if hint_lower == column.name.lower() or hint_lower in {alias.lower() for alias in column.aliases}]
            if matched_column_names:
                score += 2
                reasons.append(f"字段提示匹配: {matched_column_names[0]}")

        if analysis.time_grain is not None:
            date_columns = [column for column in table.columns if "date" in column.name.lower() or any("日期" in alias or "时间" in alias for alias in column.aliases)]
            if date_columns:
                score += 2
                reasons.append(f"时间粒度提示: {analysis.time_grain}")

        if analysis.top_k is not None and any(tag == "ranking" for tag in analysis.intent_tags):
            score += 1
            reasons.append(f"Top-K 提示: {analysis.top_k}")

        return score, reasons
