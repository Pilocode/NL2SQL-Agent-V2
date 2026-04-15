from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from app.config import Settings
from core.database_registry import load_database_registry
from core.database_router import DatabaseRouter
from core.example_retriever import ExampleRetriever
from core.llm_client import LLMProfile, OpenAICompatibleLLM
from core.models import AgentTrace, ExampleCandidate, NL2SQLResponse, OPERATION_MODE_DDL, OPERATION_MODE_DML, OPERATION_MODE_QUERY, PipelineResult, QueryExecution, RepairStep, SemanticInterpretation, StageUpdate, ValidationResult
from core.multi_agent import AnswerAgent, QueryAnalysisAgent, SQLGenerationAgent, SQLRepairAgent, SemanticThinkingAgent
from core.prompt_builder import PromptBuilder
from core.query_analyzer import QueryAnalyzer
from core.result_explainer import ResultExplainer
from core.schema_retriever import SchemaRetriever
from core.sql_executor import SQLiteExecutor
from core.sql_generator import SQLGenerator
from core.sql_repairer import SQLRepairer
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
        self.rule_sql_repairers: dict[str, SQLRepairer] = {}
        self.analysis_agents: dict[str, QueryAnalysisAgent] = {}
        self.generation_agents: dict[str, SQLGenerationAgent] = {}
        self.repair_agents: dict[str, SQLRepairAgent] = {}
        self.executors: dict[str, SQLiteExecutor] = {}

        for database_id, context in self.database_registry.items():
            analyzer = QueryAnalyzer(context.semantic_layer)
            retriever = SchemaRetriever(context.schema_catalog, context.semantic_layer)
            sql_generator = SQLGenerator(context.examples, database_id=database_id)
            sql_repairer = SQLRepairer(sql_generator)

            self.query_analyzers[database_id] = analyzer
            self.schema_retrievers[database_id] = retriever
            self.rule_sql_generators[database_id] = sql_generator
            self.rule_sql_repairers[database_id] = sql_repairer
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
            self.repair_agents[database_id] = SQLRepairAgent(
                self.llm_client,
                self.prompt_builder,
                sql_repairer,
                LLMProfile(
                    model=self.settings.llm_repair_model,
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
        draft, generation_trace, prompt = self.generation_agents[active_database_id].generate(
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

        current_sql = draft.sql if draft is not None else ""
        repairs: list[RepairStep] = []
        validation = self.sql_validator.validate(current_sql, operation_mode=operation_mode)
        if validation.normalized_sql is not None:
            current_sql = validation.normalized_sql

        validation_message = self._build_stage_message(
            "validation",
            f"SQL 校验完成，结果：{validation.message}",
        )
        stage_updates.append(validation_message)
        yield "stage", validation_message

        for _ in range(max_repair_rounds):
            if validation.is_valid:
                break

            repaired, repair_trace = self.repair_agents[active_database_id].repair(
                question,
                current_sql,
                validation.message,
                generation_analysis,
                generation_retrievals,
                generation_examples,
                semantic_interpretation,
                generation_database,
                operation_mode,
                self.database_registry[active_database_id].schema_catalog,
            )
            traces.append(repair_trace)
            if repaired is None or repaired.sql == current_sql:
                break

            repairs.append(
                RepairStep(
                    reason=repaired.message,
                    sql_before=current_sql,
                    sql_after=repaired.sql,
                )
            )
            current_sql = repaired.sql
            validation = self.sql_validator.validate(current_sql, operation_mode=operation_mode)
            if validation.normalized_sql is not None:
                current_sql = validation.normalized_sql
            repair_message = self._build_stage_message(
                "repair",
                f"已完成一次 SQL 修复，当前校验结果：{validation.message}",
            )
            stage_updates.append(repair_message)
            yield "stage", repair_message

        execution: QueryExecution | None = None
        if validation.is_valid and current_sql:
            execution = self._execute_with_repair(
                question,
                pipeline,
                current_sql,
                repairs,
                traces,
                max_repair_rounds,
                semantic_interpretation,
                generation_analysis,
                generation_retrievals,
                generation_examples,
                active_database_id,
                generation_database,
                operation_mode,
            )
            execution_message = self._build_execution_stage_message(execution)
            stage_updates.append(execution_message)
            yield "stage", execution_message

        if execution is None and not validation.is_valid:
            execution = QueryExecution(
                succeeded=False,
                sql=current_sql,
                statement_type=validation.statement_type,
                error_message=validation.message,
            )
            execution_message = self._build_stage_message(
                "execution",
                f"由于 SQL 未通过校验，未执行查询：{validation.message}",
            )
            stage_updates.append(execution_message)
            yield "stage", execution_message

        answer_text = validation.message if not validation.is_valid else "当前未返回结果。"
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
            repairs=tuple(repairs),
            final_sql=current_sql or None,
            execution=execution,
            answer_text=answer_text,
            agent_traces=tuple(traces),
            stage_updates=tuple(stage_updates),
            operation_mode=operation_mode,
        )
        yield "final", response

    def _execute_with_repair(
        self,
        question: str,
        pipeline: PipelineResult,
        sql: str,
        repairs: list[RepairStep],
        traces: list[AgentTrace],
        max_repair_rounds: int,
        semantic_interpretation: SemanticInterpretation | None,
        generation_analysis,
        generation_retrievals,
        generation_examples,
        database_id: str,
        routed_database,
        operation_mode: str,
    ) -> QueryExecution:
        executor = self.executors.get(database_id)
        if executor is None:
            database_name = routed_database.display_name if routed_database is not None else database_id
            return QueryExecution(
                succeeded=False,
                sql=sql,
                error_message=f"当前数据库 {database_name} 尚未接入可执行 SQLite 文件，现阶段仅支持 schema 与 example RAG。",
            )

        current_sql = sql
        current_validation: ValidationResult | None = None

        for _ in range(max_repair_rounds + 1):
            try:
                execution = executor.execute(current_sql)
                traces.append(
                    AgentTrace(
                        "execution_agent",
                        "sqlite",
                        f"SQL 执行成功，statement_type={execution.statement_type}, row_count={execution.row_count}, affected_rows={execution.affected_rows}",
                    )
                )
                return execution
            except Exception as error:
                repaired, repair_trace = self.repair_agents[database_id].repair(
                    question,
                    current_sql,
                    str(error),
                    generation_analysis,
                    generation_retrievals,
                    generation_examples,
                    semantic_interpretation,
                    routed_database,
                    operation_mode,
                    self.database_registry[database_id].schema_catalog,
                )
                traces.append(repair_trace)
                if repaired is None or repaired.sql == current_sql:
                    traces.append(AgentTrace("execution_agent", "sqlite", f"SQL 执行失败: {error}"))
                    return QueryExecution(
                        succeeded=False,
                        sql=current_sql,
                        error_message=str(error),
                    )

                repairs.append(
                    RepairStep(
                        reason=repaired.message,
                        sql_before=current_sql,
                        sql_after=repaired.sql,
                    )
                )
                current_sql = repaired.sql
                current_validation = self.sql_validator.validate(current_sql, operation_mode=operation_mode)
                if not current_validation.is_valid:
                    return QueryExecution(
                        succeeded=False,
                        sql=current_sql,
                        statement_type=current_validation.statement_type,
                        error_message=current_validation.message,
                    )
                if current_validation.normalized_sql is not None:
                    current_sql = current_validation.normalized_sql

        if current_validation is not None and not current_validation.is_valid:
            return QueryExecution(
                succeeded=False,
                sql=current_sql,
                statement_type=current_validation.statement_type,
                error_message=current_validation.message,
            )

        return QueryExecution(
            succeeded=False,
            sql=current_sql,
            error_message="SQL 执行失败，且自动修复已达到重试上限。",
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