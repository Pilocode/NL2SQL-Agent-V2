from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterator

from app.config import Settings
from core.database_registry import load_database_registry
from core.database_router import DatabaseRouter
from core.example_retriever import ExampleRetriever
from core.llm_client import LLMProfile, OpenAICompatibleLLM
from core.models import AgentTrace, ExampleCandidate, ExecutionConfirmation, NL2SQLResponse, OPERATION_MODE_DDL, OPERATION_MODE_DML, OPERATION_MODE_QUERY, PipelineResult, QueryExecution, SemanticInterpretation, StageUpdate, ValidationResult
from core.multi_agent import AnswerAgent, QueryAnalysisAgent, SQLGenerationAgent, SemanticThinkingAgent
from core.prompt_builder import PromptBuilder
from core.query_analyzer import QueryAnalyzer
from core.result_explainer import ResultExplainer
from core.schema_retriever import SchemaRetriever
from core.sql_executor import SQLiteExecutor
from core.sql_generator import SQLGenerator
from core.sql_validator import SQLValidator


@dataclass
class NL2SQLOrchestrator:
    settings: Settings

    def __post_init__(self) -> None:
        self.prompt_builder = PromptBuilder()
        self.database_registry = load_database_registry(self.settings)
        self.default_database_id = "chinook" if "chinook" in self.database_registry else next(iter(self.database_registry))
        self.database_router = DatabaseRouter(self.database_registry, self.default_database_id)
        self.router_seed_analyzer = QueryAnalyzer()
        self.example_retriever = ExampleRetriever(self.database_registry)
        self.sql_validator = SQLValidator()
        self.llm_client = OpenAICompatibleLLM(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=self.settings.llm_model,
            timeout_seconds=self.settings.llm_timeout_seconds,
            enable_thinking=self.settings.llm_enable_thinking,
        )
        self.thinking_agent = SemanticThinkingAgent(
            self.llm_client,
            self.prompt_builder,
            LLMProfile(
                model=self.settings.llm_thinking_model,
                temperature=0.2,
                max_tokens=320,
                enable_thinking=self.settings.llm_enable_thinking,
            ),
        )
        self.answer_agent = AnswerAgent(
            self.llm_client,
            self.prompt_builder,
            ResultExplainer(),
            LLMProfile(
                model=self.settings.llm_answer_model,
                temperature=0.2,
                max_tokens=220,
                enable_thinking=False,
            ),
        )
        self.query_analyzers: dict[str, QueryAnalyzer] = {}
        self.schema_retrievers: dict[str, SchemaRetriever] = {}
        self.rule_sql_generators: dict[str, SQLGenerator] = {}
        self.analysis_agents: dict[str, QueryAnalysisAgent] = {}
        self.generation_agents: dict[str, SQLGenerationAgent] = {}
        self.executors: dict[str, SQLiteExecutor] = {}

        for database_id, context in self.database_registry.items():
            analyzer = QueryAnalyzer(context.semantic_layer)
            retriever = SchemaRetriever(context.schema_catalog, context.semantic_layer)
            sql_generator = SQLGenerator(context.examples, database_id=database_id)

            self.query_analyzers[database_id] = analyzer
            self.schema_retrievers[database_id] = retriever
            self.rule_sql_generators[database_id] = sql_generator
            self.analysis_agents[database_id] = QueryAnalysisAgent(
                self.llm_client,
                self.prompt_builder,
                analyzer,
                context.semantic_layer,
                LLMProfile(
                    model=self.settings.llm_analysis_model,
                    temperature=0.1,
                    max_tokens=420,
                    enable_thinking=self.settings.llm_enable_thinking,
                ),
            )
            self.generation_agents[database_id] = SQLGenerationAgent(
                self.llm_client,
                self.prompt_builder,
                sql_generator,
                LLMProfile(
                    model=self.settings.llm_generation_model,
                    temperature=0.0,
                    max_tokens=520,
                    enable_thinking=False,
                ),
            )
            if context.profile.database_path is not None and context.profile.database_path.exists() and context.profile.dialect == "sqlite":
                self.executors[database_id] = SQLiteExecutor(context.profile.database_path)

    def inspect_question(self, question: str, operation_mode: str = OPERATION_MODE_QUERY) -> PipelineResult:
        pipeline, _ = self._prepare_pipeline(question, operation_mode)
        return pipeline

    def _prepare_pipeline(self, question: str, operation_mode: str = OPERATION_MODE_QUERY) -> tuple[PipelineResult, AgentTrace]:
        routed_database = self.database_router.route(question, self.router_seed_analyzer.analyze(question))
        analysis_agent = self.analysis_agents[routed_database.database_id]
        schema_retriever = self.schema_retrievers[routed_database.database_id]
        database_examples = self.database_registry[routed_database.database_id].examples

        analysis, analysis_trace = analysis_agent.analyze(question, operation_mode)
        if not question.strip():
            pipeline = PipelineResult(
                analysis=analysis,
                retrievals=(),
                example_candidates=tuple(database_examples[:3]),
                routed_database=routed_database,
                operation_mode=operation_mode,
            )
            return pipeline, analysis_trace

        retrievals = schema_retriever.retrieve(question, analysis.tokens, analysis=analysis)
        example_candidates = self.example_retriever.retrieve(question, analysis, routed_database.database_id, limit=8)
        if not example_candidates:
            example_candidates = tuple(database_examples[:5])
        pipeline = PipelineResult(
            analysis=analysis,
            retrievals=retrievals,
            example_candidates=example_candidates,
            routed_database=routed_database,
            operation_mode=operation_mode,
        )
        return pipeline, self._build_analysis_trace(analysis_trace, pipeline)

    def answer_question(self, question: str, max_repair_rounds: int = 2, operation_mode: str = OPERATION_MODE_QUERY) -> NL2SQLResponse:
        final_response: NL2SQLResponse | None = None
        for event_type, payload in self.answer_question_stream(question, max_repair_rounds=max_repair_rounds, operation_mode=operation_mode):
            if event_type == "final":
                final_response = payload

        if final_response is None:
            raise RuntimeError("NL2SQL pipeline ended without producing a final response")
        return final_response

    def confirm_ddl_response(self, response: NL2SQLResponse) -> NL2SQLResponse:
        confirmation = response.execution_confirmation
        if confirmation is None or not confirmation.required or confirmation.confirmed:
            return response
        if response.final_sql is None:
            raise ValueError("Cannot confirm DDL execution without validated SQL")

        traces = list(response.agent_traces)
        stage_updates = list(response.stage_updates)
        confirmed_message = self._build_stage_message("confirmation", "已收到二次确认，开始执行 DDL SQL。")
        stage_updates.append(confirmed_message)
        database = response.pipeline.routed_database
        database_id = database.database_id if database is not None else self.default_database_id
        execution = self._execute_sql(response.final_sql, traces, database_id, database)
        execution_message = self._build_execution_stage_message(execution)
        stage_updates.append(execution_message)
        answer_text = response.answer_text
        if execution is not None:
            answer_text, answer_trace = self.answer_agent.answer(
                response.pipeline.analysis.original_question,
                response.final_sql,
                execution,
                response.operation_mode,
            )
            traces.append(answer_trace)
            answer_message = self._build_stage_message("answer", "结果解释完成，正在整理最终回答。")
            stage_updates.append(answer_message)

        return replace(
            response,
            execution_confirmation=ExecutionConfirmation(
                required=True,
                confirmed=True,
                message="DDL 已经由用户确认并执行。",
                statement_type=confirmation.statement_type,
            ),
            execution=execution,
            answer_text=answer_text,
            agent_traces=tuple(traces),
            stage_updates=tuple(stage_updates),
        )

    def answer_question_stream(self, question: str, max_repair_rounds: int = 2, operation_mode: str = OPERATION_MODE_QUERY) -> Iterator[tuple[str, StageUpdate | NL2SQLResponse]]:
        pipeline, initial_analysis_trace = self._prepare_pipeline(question, operation_mode)
        traces = [initial_analysis_trace]
        stage_updates: list[StageUpdate] = []
        analysis_message = self._build_stage_message(
            "analysis",
            f"问题分析完成，当前模式为 {operation_mode.upper()}，识别到 {len(pipeline.analysis.tokens)} 个关键信号，召回 {len(pipeline.retrievals)} 张候选表。",
        )
        stage_updates.append(analysis_message)
        yield "stage", analysis_message
        if not question.strip():
            validation = ValidationResult(is_valid=False, message="问题为空，请先输入自然语言问题")
            response = NL2SQLResponse(
                pipeline=pipeline,
                prompt="",
                draft=None,
                validation=validation,
                semantic_interpretation=None,
                final_sql=None,
                execution=QueryExecution(
                    succeeded=False,
                    sql="",
                    error_message=validation.message,
                ),
                answer_text=validation.message,
                agent_traces=tuple(traces),
                stage_updates=tuple(stage_updates),
                operation_mode=operation_mode,
            )
            yield "final", response
            return

        if pipeline.analysis.generation_status != "generate":
            reason = pipeline.analysis.generation_reason or (
                "当前请求超出系统支持范围，未进入 SQL 生成。"
                if pipeline.analysis.generation_status == "unsupported"
                else "当前问题与数据库操作无关，未进入 SQL 生成。"
            )
            decision_message = self._build_stage_message(
                "analysis_decision",
                reason,
            )
            stage_updates.append(decision_message)
            yield "stage", decision_message
            validation = ValidationResult(is_valid=False, message=reason, operation_mode=operation_mode)
            response = NL2SQLResponse(
                pipeline=pipeline,
                prompt="",
                draft=None,
                validation=validation,
                semantic_interpretation=None,
                final_sql=None,
                execution=QueryExecution(
                    succeeded=False,
                    sql="",
                    error_message=reason,
                ),
                answer_text=reason,
                agent_traces=tuple(traces),
                stage_updates=tuple(stage_updates),
                operation_mode=operation_mode,
            )
            yield "final", response
            return

        write_intents = {"insert", "update", "delete", "create", "alter", "drop"}
        should_run_thinking = operation_mode != OPERATION_MODE_DDL and not any(tag in write_intents for tag in pipeline.analysis.intent_tags)
        if should_run_thinking:
            semantic_interpretation, thinking_trace = self.thinking_agent.interpret(
                question,
                pipeline.analysis,
                pipeline.retrievals,
            )
            traces.append(thinking_trace)
            if semantic_interpretation is None:
                thinking_message = self._build_stage_message("thinking", "语义解释阶段已完成，本次无需额外语义改写。")
            elif semantic_interpretation.rewritten_question.strip() != question.strip():
                thinking_message = self._build_stage_message(
                    "thinking",
                    f"语义解释完成，已将问题澄清为“{semantic_interpretation.rewritten_question}”。",
                )
            else:
                thinking_message = self._build_stage_message("thinking", "语义解释阶段已完成，保留原始问题语义继续执行。")
        else:
            semantic_interpretation = None
            traces.append(AgentTrace("thinking_agent", "skip", "当前模式或意图无需 thinking 语义改写。"))
            thinking_message = self._build_stage_message("thinking", "当前模式无需额外语义改写，直接进入 SQL 生成。")
        stage_updates.append(thinking_message)
        yield "stage", thinking_message

        generation_analysis = pipeline.analysis
        generation_retrievals = pipeline.retrievals
        generation_examples = pipeline.example_candidates
        generation_database = pipeline.routed_database
        if (
            semantic_interpretation is not None
            and semantic_interpretation.rewritten_question
            and semantic_interpretation.rewritten_question.strip() != question.strip()
        ):
            previous_database_id = generation_database.database_id if generation_database is not None else self.default_database_id
            rerouted_database = self.database_router.route(
                semantic_interpretation.rewritten_question,
                self.router_seed_analyzer.analyze(semantic_interpretation.rewritten_question),
            )
            generation_database = rerouted_database
            generation_analysis, refreshed_analysis_trace = self.analysis_agents[rerouted_database.database_id].analyze(semantic_interpretation.rewritten_question, operation_mode)
            generation_retrievals = self.schema_retrievers[rerouted_database.database_id].retrieve(
                semantic_interpretation.rewritten_question,
                generation_analysis.tokens,
                analysis=generation_analysis,
            )
            generation_examples = self.example_retriever.retrieve(
                semantic_interpretation.rewritten_question,
                generation_analysis,
                rerouted_database.database_id,
                limit=8,
            )
            if not generation_examples:
                generation_examples = tuple(self.database_registry[rerouted_database.database_id].examples[:5])
            pipeline = PipelineResult(
                analysis=generation_analysis,
                retrievals=generation_retrievals,
                example_candidates=generation_examples,
                routed_database=rerouted_database,
                operation_mode=operation_mode,
            )
            traces.append(
                self._build_analysis_trace(
                    refreshed_analysis_trace,
                    pipeline,
                    prefix="基于语义改写重新完成分析",
                )
            )
            if rerouted_database.database_id != previous_database_id:
                traces.append(
                    AgentTrace(
                        "routing_agent",
                        "database_switch",
                        f"语义改写后切换数据库到 {rerouted_database.display_name}: {rerouted_database.reason}",
                    )
                )
            traces.append(
                AgentTrace(
                    "thinking_agent",
                    "retrieval_refresh",
                    f"根据语义改写后的问题刷新召回：{[hit.table_name for hit in generation_retrievals[:5]]}",
                )
            )
            refresh_message = self._build_stage_message(
                "retrieval_refresh",
                f"已基于改写后的问题刷新分析与召回，当前重点表包括 {', '.join(hit.table_name for hit in generation_retrievals[:3]) or '无'}。",
            )
            stage_updates.append(refresh_message)
            yield "stage", refresh_message

        active_database_id = generation_database.database_id if generation_database is not None else self.default_database_id
        draft, generation_trace, prompt, generation_diagnostics = self.generation_agents[active_database_id].generate(
            question,
            generation_analysis,
            generation_retrievals,
            generation_examples,
            semantic_interpretation,
            generation_database,
            operation_mode,
            self.database_registry[active_database_id].schema_catalog,
        )
        traces.append(generation_trace)
        sql_preview = draft.sql if draft is not None else "未生成 SQL"
        generation_message = self._build_stage_message(
            "generation",
            f"SQL 生成完成，当前结果为：{sql_preview}",
        )
        stage_updates.append(generation_message)
        yield "stage", generation_message

        if draft is None:
            failure_message = generation_trace.detail or "SQL 生成失败，未返回可执行 SQL。"
            validation = ValidationResult(is_valid=False, message=failure_message, operation_mode=operation_mode)
            response = NL2SQLResponse(
                pipeline=pipeline,
                prompt=prompt,
                draft=None,
                validation=validation,
                semantic_interpretation=semantic_interpretation,
                generation_diagnostics=generation_diagnostics,
                final_sql=None,
                execution=QueryExecution(
                    succeeded=False,
                    sql="",
                    error_message=failure_message,
                ),
                answer_text=failure_message,
                agent_traces=tuple(traces),
                stage_updates=tuple(stage_updates),
                operation_mode=operation_mode,
            )
            yield "final", response
            return

        current_sql = draft.sql if draft is not None else ""
        validation = self.sql_validator.validate(current_sql, operation_mode=operation_mode)
        if validation.normalized_sql is not None:
            current_sql = validation.normalized_sql

        validation_message = self._build_stage_message(
            "validation",
            f"SQL 校验完成，结果：{validation.message}",
        )
        stage_updates.append(validation_message)
        yield "stage", validation_message

        if not validation.is_valid:
            response = NL2SQLResponse(
                pipeline=pipeline,
                prompt=prompt,
                draft=draft,
                validation=validation,
                semantic_interpretation=semantic_interpretation,
                generation_diagnostics=generation_diagnostics,
                final_sql=current_sql or None,
                execution=QueryExecution(
                    succeeded=False,
                    sql=current_sql,
                    statement_type=validation.statement_type,
                    error_message=validation.message,
                ),
                answer_text=validation.message,
                agent_traces=tuple(traces),
                stage_updates=tuple(stage_updates),
                operation_mode=operation_mode,
            )
            yield "final", response
            return

        if self._requires_ddl_confirmation(operation_mode, validation.statement_type):
            confirmation_message = "DDL 语句已生成并校验通过。该语句会修改表结构，请在执行前进行二次确认。"
            confirmation_stage = self._build_stage_message("confirmation", confirmation_message)
            stage_updates.append(confirmation_stage)
            yield "stage", confirmation_stage
            response = NL2SQLResponse(
                pipeline=pipeline,
                prompt=prompt,
                draft=draft,
                validation=validation,
                semantic_interpretation=semantic_interpretation,
                generation_diagnostics=generation_diagnostics,
                execution_confirmation=ExecutionConfirmation(
                    required=True,
                    confirmed=False,
                    message=confirmation_message,
                    statement_type=validation.statement_type,
                ),
                final_sql=current_sql or None,
                execution=QueryExecution(
                    succeeded=False,
                    sql=current_sql,
                    statement_type=validation.statement_type,
                    error_message=confirmation_message,
                ),
                answer_text=confirmation_message,
                agent_traces=tuple(traces),
                stage_updates=tuple(stage_updates),
                operation_mode=operation_mode,
            )
            yield "final", response
            return

        execution = self._execute_sql(
            current_sql,
            traces,
            active_database_id,
            generation_database,
        )
        execution_message = self._build_execution_stage_message(execution)
        stage_updates.append(execution_message)
        yield "stage", execution_message

        answer_text = "当前未返回结果。"
        if execution is not None:
            answer_text, answer_trace = self.answer_agent.answer(question, current_sql or "", execution, operation_mode)
            traces.append(answer_trace)
            answer_message = self._build_stage_message("answer", "结果解释完成，正在整理最终回答。")
            stage_updates.append(answer_message)
            yield "stage", answer_message

        response = NL2SQLResponse(
            pipeline=pipeline,
            prompt=prompt,
            draft=draft,
            validation=validation,
            semantic_interpretation=semantic_interpretation,
            generation_diagnostics=generation_diagnostics,
            execution_confirmation=ExecutionConfirmation(required=False, confirmed=True, message="当前请求无需额外执行确认。", statement_type=validation.statement_type),
            final_sql=current_sql or None,
            execution=execution,
            answer_text=answer_text,
            agent_traces=tuple(traces),
            stage_updates=tuple(stage_updates),
            operation_mode=operation_mode,
        )
        yield "final", response

    def _requires_ddl_confirmation(self, operation_mode: str, statement_type: str | None) -> bool:
        return operation_mode == OPERATION_MODE_DDL and statement_type in {"create", "alter", "drop"}

    def _execute_sql(
        self,
        sql: str,
        traces: list[AgentTrace],
        database_id: str,
        routed_database,
    ) -> QueryExecution:
        executor = self.executors.get(database_id)
        if executor is None:
            database_name = routed_database.display_name if routed_database is not None else database_id
            return QueryExecution(
                succeeded=False,
                sql=sql,
                error_message=f"当前数据库 {database_name} 尚未接入可执行 SQLite 文件，现阶段仅支持 schema 与 example RAG。",
            )

        try:
            execution = executor.execute(sql)
            traces.append(
                AgentTrace(
                    "execution_agent",
                    "sqlite",
                    f"SQL 执行成功，statement_type={execution.statement_type}, row_count={execution.row_count}, affected_rows={execution.affected_rows}",
                )
            )
            return execution
        except Exception as error:
            traces.append(AgentTrace("execution_agent", "sqlite", f"SQL 执行失败: {error}"))
            return QueryExecution(
                succeeded=False,
                sql=sql,
                error_message=str(error),
            )

    def _build_analysis_trace(self, analysis_trace: AgentTrace, pipeline: PipelineResult, prefix: str | None = None) -> AgentTrace:
        routed_database = pipeline.routed_database
        detail = (
            f"db={routed_database.database_id if routed_database is not None else self.default_database_id}; "
            f"route_reason={routed_database.reason if routed_database is not None else '默认库'}; "
            f"{analysis_trace.detail}; retrievals={[hit.table_name for hit in pipeline.retrievals[:4]]}"
        )
        if prefix:
            detail = f"{prefix}: {detail}"
        return AgentTrace("analysis_agent", analysis_trace.strategy, detail)

    def _build_stage_message(self, stage: str, message: str) -> StageUpdate:
        return StageUpdate(stage=stage, message=message)

    def _build_execution_stage_message(self, execution: QueryExecution) -> StageUpdate:
        if not execution.succeeded:
            return self._build_stage_message("execution", f"SQL 执行失败：{execution.error_message or '未知错误'}")

        if execution.statement_type == "select":
            return self._build_stage_message("execution", f"SQL 执行完成，返回 {execution.row_count} 行结果。")
        if execution.statement_type in {"insert", "update", "delete"}:
            return self._build_stage_message("execution", f"SQL 执行完成，影响 {execution.affected_rows} 行数据。")
        if execution.statement_type in {"create", "alter", "drop"}:
            return self._build_stage_message("execution", "SQL 执行完成，数据库结构已更新。")
        return self._build_stage_message("execution", "SQL 执行完成。")