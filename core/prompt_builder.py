from __future__ import annotations

from core.models import ExampleCandidate, OPERATION_MODE_DDL, OPERATION_MODE_DML, OPERATION_MODE_QUERY, QueryAnalysis, QueryExecution, RetrievalHit, RoutedDatabase, SemanticInterpretation, TableProfile


class PromptBuilder:
    def build_analysis_prompt(
        self,
        question: str,
        semantic_layer: dict | None = None,
        fallback_analysis: QueryAnalysis | None = None,
        operation_mode: str = OPERATION_MODE_QUERY,
    ) -> str:
        semantic_context = self._build_semantic_overview(semantic_layer or {})
        fallback_context = self._build_analysis_context(fallback_analysis)
        mode_hint = self._build_operation_mode_hint(operation_mode)
        return (
            "你是 Analysis Agent，负责把自然语言分析问题转成结构化语义槽位。\n"
            "你的任务不是机械抽关键词，而是基于业务语义主动理解用户真正想查什么。\n"
            "要求：\n"
            "- 只输出 JSON\n"
            "- JSON 字段固定为 normalized_question, tokens, intent_tags, metric_hints, entity_hints, ambiguous_terms, time_grain, top_k, is_follow_up\n"
            "- intent_tags 可使用 count, ranking, average, sum, filter, comparison, insert, update, delete, create, alter, drop\n"
            "- time_grain 仅可使用 year, month, day 或 null\n"
            "- tokens 应是后续 schema 检索有价值的业务词，不要机械拆所有词\n"
            "- metric_hints 和 entity_hints 可以基于语义推断，不要求必须原词出现在问题里\n"
            "- 如果这是追问，请把 is_follow_up 设为 true\n"
            "- 无法确定的字段请返回空数组、null 或 false，不要编造\n"
            f"当前操作模式: {mode_hint}\n"
            f"用户问题: {question}\n"
            f"本地兜底分析: {fallback_context}\n"
            "领域语义参考:\n"
            f"{semantic_context}"
        )

    def build(
        self,
        question: str,
        retrievals: tuple[RetrievalHit, ...],
        example_candidates: tuple[ExampleCandidate, ...] = (),
        analysis: QueryAnalysis | None = None,
    ) -> str:
        return self.build_generation_prompt(question, retrievals, example_candidates, analysis)

    def build_generation_prompt(
        self,
        question: str,
        retrievals: tuple[RetrievalHit, ...],
        example_candidates: tuple[ExampleCandidate, ...] = (),
        analysis: QueryAnalysis | None = None,
        semantic_interpretation: SemanticInterpretation | None = None,
        routed_database: RoutedDatabase | None = None,
        operation_mode: str = OPERATION_MODE_QUERY,
        schema_catalog: tuple[TableProfile, ...] = (),
    ) -> str:
        schema_context = self._build_schema_context(retrievals, schema_catalog, operation_mode)
        example_context = self._build_example_context(example_candidates)
        analysis_context = self._build_analysis_context(analysis)
        semantic_context = self._build_semantic_context(semantic_interpretation)
        database_context = self._build_database_context(routed_database)
        mode_rules = self._build_generation_rules(operation_mode)

        return (
            "你是 SQL Generation Agent，负责把自然语言问题转成 SQLite SQL。\n"
            f"目标：在当前模式下生成安全、可执行且最贴合问题的 SQL。\n"
            "规则：\n"
            f"{mode_rules}\n"
            "- 必须优先使用给定 schema，不要杜撰字段\n"
            f"目标数据库: {database_context}\n"
            f"用户问题: {question}\n"
            f"问题分析: {analysis_context}\n"
            f"语义解释: {semantic_context}\n"
            "可用 schema:\n"
            f"{schema_context}\n"
            "可参考示例:\n"
            f"{example_context}"
        )

    def build_thinking_prompt(
        self,
        question: str,
        retrievals: tuple[RetrievalHit, ...],
        analysis: QueryAnalysis | None = None,
    ) -> str:
        schema_context = self._build_schema_context(retrievals)
        analysis_context = self._build_analysis_context(analysis)
        return (
            "你是 Thinking Agent，负责把模糊的自然语言查询解释成可执行的业务语义。\n"
            "请根据问题、schema 和已知指标，判断像‘火’‘热门’‘经典’这类词最合理对应什么业务定义。\n"
            "要求：\n"
            "- 只输出 JSON\n"
            "- JSON 字段固定为 rewritten_question, resolved_metric, resolved_entity, assumptions, confidence\n"
            "- rewritten_question 必须是更明确、可以直接交给 SQL 生成器的问题\n"
            "- assumptions 是字符串数组，写出你采用该定义的理由\n"
            f"原始问题: {question}\n"
            f"问题分析: {analysis_context}\n"
            "可用 schema:\n"
            f"{schema_context}"
        )

    def build_repair_prompt(
        self,
        question: str,
        failed_sql: str,
        error_message: str,
        retrievals: tuple[RetrievalHit, ...],
        example_candidates: tuple[ExampleCandidate, ...] = (),
        analysis: QueryAnalysis | None = None,
        semantic_interpretation: SemanticInterpretation | None = None,
        routed_database: RoutedDatabase | None = None,
        operation_mode: str = OPERATION_MODE_QUERY,
        schema_catalog: tuple[TableProfile, ...] = (),
    ) -> str:
        schema_context = self._build_schema_context(retrievals, schema_catalog, operation_mode)
        example_context = self._build_example_context(example_candidates)
        analysis_context = self._build_analysis_context(analysis)
        semantic_context = self._build_semantic_context(semantic_interpretation)
        database_context = self._build_database_context(routed_database)
        mode_rules = self._build_generation_rules(operation_mode)

        return (
            "你是 SQL Repair Agent，负责根据报错修复一条 SQLite 查询。\n"
            "规则：\n"
            "- 只输出修复后的最终 SQL，不要解释，不要 Markdown 代码块\n"
            f"{mode_rules}\n"
            "- 必须参考给定 schema 和错误信息，不要发明不存在的字段\n"
            f"目标数据库: {database_context}\n"
            f"原始问题: {question}\n"
            f"问题分析: {analysis_context}\n"
            f"语义解释: {semantic_context}\n"
            f"失败 SQL: {failed_sql}\n"
            f"错误信息: {error_message}\n"
            "可用 schema:\n"
            f"{schema_context}\n"
            "可参考示例:\n"
            f"{example_context}"
        )

    def build_answer_prompt(
        self,
        question: str,
        sql: str,
        execution: QueryExecution,
        operation_mode: str = OPERATION_MODE_QUERY,
    ) -> str:
        preview_rows = [", ".join(str(value) for value in row) for row in execution.rows[:5]]
        preview_text = "\n".join(f"- {row}" for row in preview_rows) or "- 无结果"
        return (
            "你是 Answer Agent，负责把 SQL 查询结果解释成自然语言回答。\n"
            "要求：\n"
            "- 用中文回答\n"
            "- 直接回答用户问题\n"
            "- 简洁，不要暴露技术实现细节\n"
            f"操作模式: {self._build_operation_mode_hint(operation_mode)}\n"
            f"SQL 类型: {execution.statement_type or 'unknown'}\n"
            f"用户问题: {question}\n"
            f"执行 SQL: {sql}\n"
            f"返回行数: {execution.row_count}\n"
            "结果预览:\n"
            f"{preview_text}"
        )

    def _build_schema_context(
        self,
        retrievals: tuple[RetrievalHit, ...],
        schema_catalog: tuple[TableProfile, ...] = (),
        operation_mode: str = OPERATION_MODE_QUERY,
    ) -> str:
        if operation_mode in {OPERATION_MODE_DML, OPERATION_MODE_DDL} and schema_catalog:
            schema_lines = []
            for table in schema_catalog[:16]:
                column_lines = []
                for column in table.columns[:12]:
                    description = f" ({column.description})" if column.description else ""
                    column_lines.append(f"{column.name}{description}")
                table_description = f" | 表说明: {table.description}" if table.description else ""
                schema_lines.append(f"- {table.name}: {', '.join(column_lines)}{table_description}")
            return "\n".join(schema_lines) or "- 暂无 schema"

        schema_lines = []
        for hit in retrievals:
            columns = ", ".join(f"{column.name}{f' ({column.description})' if column.description else ''}" for column in hit.columns)
            schema_lines.append(f"- {hit.table_name}: {columns}")
        return "\n".join(schema_lines) or "- 暂无召回结果"

    def _build_example_context(self, example_candidates: tuple[ExampleCandidate, ...]) -> str:
        example_lines = []
        for example in example_candidates:
            example_lines.append(f"- 问题: {example.question}\n  SQL: {example.sql}")
        return "\n".join(example_lines) or "- 暂无相近示例"

    def _build_semantic_overview(self, semantic_layer: dict) -> str:
        table_lines = []
        for table_name, aliases in semantic_layer.get("table_aliases", {}).items():
            alias_values = [str(alias) for alias in aliases[:4] if str(alias).strip()]
            alias_text = ", ".join(alias_values) if alias_values else "无"
            table_lines.append(f"- 表 {table_name}: 别名 {alias_text}")

        metric_lines = []
        for metric in semantic_layer.get("metric_templates", []):
            metric_name = str(metric.get("name", "")).strip()
            if not metric_name:
                continue
            metric_lines.append(
                f"- 指标 {metric_name}: table={metric.get('table', '')}, column={metric.get('column', '')}"
            )

        column_lines = []
        for column_key, aliases in list(semantic_layer.get("column_aliases", {}).items())[:12]:
            alias_values = [str(alias) for alias in aliases[:3] if str(alias).strip()]
            alias_text = ", ".join(alias_values) if alias_values else "无"
            column_lines.append(f"- 字段 {column_key}: 别名 {alias_text}")

        blocks = [
            "表语义:\n" + ("\n".join(table_lines[:12]) or "- 无"),
            "指标模板:\n" + ("\n".join(metric_lines[:12]) or "- 无"),
            "字段语义:\n" + ("\n".join(column_lines) or "- 无"),
        ]
        return "\n".join(blocks)

    def _build_analysis_context(self, analysis: QueryAnalysis | None) -> str:
        if analysis is None:
            return "无"

        fields = [
            f"tokens={list(analysis.tokens)}",
            f"intent_tags={list(analysis.intent_tags)}",
            f"metric_hints={list(analysis.metric_hints)}",
            f"entity_hints={list(analysis.entity_hints)}",
            f"ambiguous_terms={list(analysis.ambiguous_terms)}",
            f"time_grain={analysis.time_grain}",
            f"top_k={analysis.top_k}",
        ]
        return "; ".join(fields)

    def _build_semantic_context(self, semantic_interpretation: SemanticInterpretation | None) -> str:
        if semantic_interpretation is None:
            return "无"
        return (
            f"rewritten_question={semantic_interpretation.rewritten_question}; "
            f"resolved_metric={semantic_interpretation.resolved_metric}; "
            f"resolved_entity={semantic_interpretation.resolved_entity}; "
            f"assumptions={list(semantic_interpretation.assumptions)}; "
            f"confidence={semantic_interpretation.confidence}"
        )

    def _build_database_context(self, routed_database: RoutedDatabase | None) -> str:
        if routed_database is None:
            return "未指定"
        return f"{routed_database.display_name} ({routed_database.database_id})"

    def _build_generation_rules(self, operation_mode: str) -> str:
        if operation_mode == OPERATION_MODE_DML:
            return (
                "- 只输出一条最终 SQL，不要解释，不要 Markdown 代码块\n"
                "- 仅允许 SELECT、INSERT、UPDATE、DELETE\n"
                "- 如果用户描述要新增数据，请优先生成 INSERT INTO ... VALUES ...\n"
                "- 如需排序的 SELECT，尽量补上 LIMIT"
            )
        if operation_mode == OPERATION_MODE_DDL:
            return (
                "- 只输出一条最终 SQL，不要解释，不要 Markdown 代码块\n"
                "- 仅允许 CREATE、ALTER、DROP\n"
                "- 优先使用 CREATE 或 ALTER；只有用户明确要求删除时才允许 DROP\n"
                "- 修改已有表结构时不要破坏现有主键和外键"
            )
        return (
            "- 只输出一条最终 SQL，不要解释，不要 Markdown 代码块\n"
            "- 只允许 SELECT 查询\n"
            "- 如需排序，尽量补上 LIMIT"
        )

    def _build_operation_mode_hint(self, operation_mode: str) -> str:
        if operation_mode == OPERATION_MODE_DML:
            return "DML 数据操作模式（SELECT / INSERT / UPDATE / DELETE）"
        if operation_mode == OPERATION_MODE_DDL:
            return "DDL 结构管理模式（CREATE / ALTER / DROP）"
        return "只读查询模式（SELECT）"