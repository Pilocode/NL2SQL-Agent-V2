from __future__ import annotations

import json
import re

import sqlglot
from sqlglot import exp

from core.llm_client import LLMProfile, OpenAICompatibleLLM
from core.models import AgentTrace, ExampleCandidate, GenerationDiagnostics, OPERATION_MODE_AUTO, OPERATION_MODE_DDL, OPERATION_MODE_DML, OPERATION_MODE_QUERY, QueryAnalysis, QueryExecution, RetrievalHit, RoutedDatabase, SQLDraft, SemanticInterpretation, TableProfile
from core.prompt_builder import PromptBuilder
from core.result_explainer import ResultExplainer
from core.sql_generator import SQLGenerator


CODE_BLOCK_PATTERN = re.compile(r"^```(?:json|sql)?\s*|\s*```$", re.IGNORECASE)
FENCED_BLOCK_PATTERN = re.compile(r"```(?:[A-Za-z0-9_+-]+)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


class SemanticThinkingAgent:
    def __init__(self, llm: OpenAICompatibleLLM, prompt_builder: PromptBuilder, profile: LLMProfile):
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.profile = profile

    def interpret(
        self,
        question: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
    ) -> tuple[SemanticInterpretation | None, AgentTrace]:
        if not self._needs_reasoning(question, analysis):
            interpretation = SemanticInterpretation(
                rewritten_question=question,
                resolved_metric=(analysis.metric_hints[0] if analysis.metric_hints else ""),
                resolved_entity=(analysis.entity_hints[0] if analysis.entity_hints else ""),
                assumptions=(),
                confidence=0.95,
            )
            return interpretation, AgentTrace("thinking_agent", "skip", "问题语义足够明确，跳过 thinking 层")

        if self.llm.is_available():
            prompt = self.prompt_builder.build_thinking_prompt(question, retrievals, analysis)
            response = self.llm.chat(
                system_prompt="You are a semantic interpretation agent for ambiguous analytics questions.",
                user_prompt=prompt,
                model=self.profile.model,
                temperature=self.profile.temperature,
                max_tokens=self.profile.max_tokens,
                enable_thinking=self.profile.enable_thinking,
            )
            interpretation = self._parse_interpretation(response.content if response is not None else "", question, analysis)
            if interpretation is not None:
                return interpretation, AgentTrace(
                    "thinking_agent",
                    "llm",
                    f"已使用 thinking LLM 将模糊问题解释为：{interpretation.rewritten_question}",
                )

        interpretation = self._fallback_interpretation(question, analysis)
        return interpretation, AgentTrace(
            "thinking_agent",
            "fallback_rule" if self.llm.is_available() else "rule_only",
            f"thinking LLM 不可用或解析失败，回退到本地语义解释：{interpretation.rewritten_question}",
        )

    def _needs_reasoning(self, question: str, analysis: QueryAnalysis) -> bool:
        return bool(analysis.ambiguous_terms or any(term in question for term in ("火", "热门", "经典", "受欢迎", "最好", "最差")))

    def _parse_interpretation(
        self,
        content: str,
        original_question: str,
        analysis: QueryAnalysis,
    ) -> SemanticInterpretation | None:
        cleaned = CODE_BLOCK_PATTERN.sub("", content.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        rewritten_question = str(payload.get("rewritten_question") or "").strip()
        if not rewritten_question:
            return None

        assumptions = payload.get("assumptions") or []
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return SemanticInterpretation(
            rewritten_question=rewritten_question,
            resolved_metric=str(payload.get("resolved_metric") or (analysis.metric_hints[0] if analysis.metric_hints else "")).strip(),
            resolved_entity=str(payload.get("resolved_entity") or (analysis.entity_hints[0] if analysis.entity_hints else "")).strip(),
            assumptions=tuple(str(item) for item in assumptions if str(item).strip()),
            confidence=confidence,
        )

    def _fallback_interpretation(self, question: str, analysis: QueryAnalysis) -> SemanticInterpretation:
        rewritten_question = question
        resolved_metric = analysis.metric_hints[0] if analysis.metric_hints else ""
        resolved_entity = analysis.entity_hints[0] if analysis.entity_hints else ""
        assumptions: list[str] = []

        if any(term in question for term in ("火", "热门", "受欢迎")) and any(term in question for term in ("专辑",)):
            rewritten_question = question.replace("最火", "销量最高").replace("热门", "销量最高").replace("火", "销量高")
            resolved_metric = "购买量"
            resolved_entity = "专辑"
            assumptions.append("当前数据库没有播放量，专辑热度默认按购买次数衡量，并以销售额作为次级排序。")
        elif any(term in question for term in ("经典",)) and any(term in question for term in ("歌曲", "曲目")):
            rewritten_question = question.replace("经典", "购买量最高")
            resolved_metric = "购买量"
            resolved_entity = "歌曲"
            assumptions.append("数据库缺少主观评分字段，经典歌曲默认按购买量近似。")

        if rewritten_question == question:
            assumptions.append("未识别到更强的模糊定义信号，沿用原始问题语义。")

        return SemanticInterpretation(
            rewritten_question=rewritten_question,
            resolved_metric=resolved_metric,
            resolved_entity=resolved_entity,
            assumptions=tuple(assumptions),
            confidence=0.62 if assumptions else 0.9,
        )


class QueryAnalysisAgent:
    def __init__(
        self,
        llm: OpenAICompatibleLLM,
        prompt_builder: PromptBuilder,
        fallback_analyzer,
        semantic_layer: dict,
        profile: LLMProfile,
    ):
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.fallback_analyzer = fallback_analyzer
        self.semantic_layer = semantic_layer
        self.profile = profile

    def analyze(self, question: str, operation_mode: str = OPERATION_MODE_QUERY) -> tuple[QueryAnalysis, AgentTrace]:
        fallback_analysis = self.fallback_analyzer.analyze(question)
        if not question.strip():
            return fallback_analysis, AgentTrace("analysis_agent", "skip", "问题为空，跳过 agent 分析")

        if self.llm.is_available():
            prompt = self.prompt_builder.build_analysis_prompt(question, self.semantic_layer, fallback_analysis, operation_mode)
            response = self.llm.chat(
                system_prompt="You are a semantic analysis agent for analytics questions.",
                user_prompt=prompt,
                model=self.profile.model,
                temperature=self.profile.temperature,
                max_tokens=self.profile.max_tokens,
                enable_thinking=self.profile.enable_thinking,
            )
            analysis = self._parse_analysis(response.content if response is not None else "", question, fallback_analysis)
            if analysis is not None:
                detail = (
                    f"已使用 analysis LLM 完成结构化分析: tokens={list(analysis.tokens)}, "
                    f"intents={list(analysis.intent_tags)}, metrics={list(analysis.metric_hints)}, "
                    f"entities={list(analysis.entity_hints)}, ambiguous={list(analysis.ambiguous_terms)}, "
                    f"generation_status={analysis.generation_status}"
                )
                return analysis, AgentTrace("analysis_agent", "llm", detail)

        strategy = "fallback_rule" if self.llm.is_available() else "rule_only"
        detail = (
            f"analysis LLM 不可用或未返回有效 JSON，回退到本地分析: tokens={list(fallback_analysis.tokens)}, "
            f"intents={list(fallback_analysis.intent_tags)}, metrics={list(fallback_analysis.metric_hints)}, "
            f"entities={list(fallback_analysis.entity_hints)}, ambiguous={list(fallback_analysis.ambiguous_terms)}, "
            f"generation_status={fallback_analysis.generation_status}"
        )
        return fallback_analysis, AgentTrace("analysis_agent", strategy, detail)

    def _parse_analysis(
        self,
        content: str,
        original_question: str,
        fallback_analysis: QueryAnalysis,
    ) -> QueryAnalysis | None:
        cleaned = CODE_BLOCK_PATTERN.sub("", content.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        normalized_question = str(payload.get("normalized_question") or fallback_analysis.normalized_question).strip().lower()
        if not normalized_question:
            normalized_question = fallback_analysis.normalized_question

        return QueryAnalysis(
            original_question=original_question,
            normalized_question=normalized_question,
            tokens=self._coerce_string_tuple(payload.get("tokens"), fallback_analysis.tokens),
            intent_tags=self._coerce_string_tuple(payload.get("intent_tags"), fallback_analysis.intent_tags),
            metric_hints=self._coerce_string_tuple(payload.get("metric_hints"), fallback_analysis.metric_hints),
            entity_hints=self._coerce_string_tuple(payload.get("entity_hints"), fallback_analysis.entity_hints),
            ambiguous_terms=self._coerce_string_tuple(payload.get("ambiguous_terms"), fallback_analysis.ambiguous_terms),
            time_grain=self._coerce_time_grain(payload.get("time_grain"), fallback_analysis.time_grain),
            top_k=self._coerce_top_k(payload.get("top_k"), fallback_analysis.top_k),
            is_follow_up=self._coerce_bool(payload.get("is_follow_up"), fallback_analysis.is_follow_up),
            generation_status=self._coerce_generation_status(payload.get("generation_status"), fallback_analysis.generation_status),
            generation_reason=str(payload.get("generation_reason") or fallback_analysis.generation_reason).strip(),
        )

    def _coerce_string_tuple(self, value: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            items = [item.strip().lower() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip().lower() for item in value if str(item).strip()]
        else:
            items = []

        if not items:
            return fallback
        return tuple(dict.fromkeys(items))

    def _coerce_time_grain(self, value: object, fallback: str | None) -> str | None:
        candidate = str(value or "").strip().lower()
        if candidate in {"year", "month", "day"}:
            return candidate
        return fallback

    def _coerce_top_k(self, value: object, fallback: int | None) -> int | None:
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            return fallback
        return candidate if candidate > 0 else fallback

    def _coerce_bool(self, value: object, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False
        return fallback

    def _coerce_generation_status(self, value: object, fallback: str) -> str:
        candidate = str(value or "").strip().lower()
        if candidate in {"generate", "unsupported", "irrelevant"}:
            return candidate
        return fallback


class SQLGenerationAgent:
    def __init__(self, llm: OpenAICompatibleLLM, prompt_builder: PromptBuilder, fallback_generator: SQLGenerator, profile: LLMProfile):
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.fallback_generator = fallback_generator
        self.profile = profile

    def generate(
        self,
        question: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
        example_candidates: tuple[ExampleCandidate, ...],
        semantic_interpretation: SemanticInterpretation | None,
        routed_database: RoutedDatabase | None,
        operation_mode: str = OPERATION_MODE_QUERY,
        schema_catalog: tuple[TableProfile, ...] = (),
    ) -> tuple[SQLDraft | None, AgentTrace, str, GenerationDiagnostics | None]:
        prompt = self.prompt_builder.build_generation_prompt(
            question,
            retrievals,
            example_candidates,
            analysis,
            semantic_interpretation,
            routed_database,
            operation_mode,
            schema_catalog,
        )
        if self.llm.is_available():
            llm_result = self.llm.chat_with_diagnostics(
                system_prompt="You are a careful SQLite SQL generation agent.",
                user_prompt=prompt,
                model=self.profile.model,
                temperature=self.profile.temperature,
                max_tokens=self.profile.max_tokens,
                enable_thinking=self.profile.enable_thinking,
            )
            response = llm_result.response
            sanitized_sql = self._sanitize_sql(response.content if response is not None else "", operation_mode)
            if sanitized_sql:
                return (
                    SQLDraft(
                        sql=sanitized_sql,
                        source="llm_generation_agent",
                        rationale="由 LLM SQL Generation Agent 根据 schema、示例和语义解释生成。",
                        prompt=prompt,
                    ),
                    AgentTrace("generation_agent", "llm", "已使用快速生成 LLM 生成 SQL"),
                    prompt,
                    None,
                )
            if response is not None:
                diagnostics = GenerationDiagnostics(
                    strategy="llm_invalid_output",
                    message="LLM 已返回内容，但清洗后未提取到有效 SQL。",
                    raw_response_preview=self._build_preview(response.content),
                )
                return None, AgentTrace(
                    "generation_agent",
                    "llm_invalid_output",
                    self._build_invalid_output_message(response.content, operation_mode),
                ), prompt, diagnostics
            diagnostics = GenerationDiagnostics(
                strategy=llm_result.failure_type or "llm_call_failed",
                message=llm_result.failure_message or "LLM 调用失败，未返回可用内容。",
            )
            return None, AgentTrace(
                "generation_agent",
                llm_result.failure_type or "llm_call_failed",
                llm_result.failure_message or "LLM 调用失败，未返回可用内容。",
            ), prompt, diagnostics

        fallback = self.fallback_generator.generate(
            question,
            analysis,
            retrievals,
            example_candidates,
            prompt,
            semantic_interpretation,
        )
        if fallback is not None:
            return fallback, AgentTrace("generation_agent", "rule_only", "LLM 未启用，已使用本地规则与样例生成 SQL。"), prompt, None

        detail = "SQL 生成失败：LLM 未启用，且当前数据库的本地规则与样例未能生成有效 SQL。"
        diagnostics = GenerationDiagnostics(
            strategy="failed",
            message=detail,
        )
        return None, AgentTrace("generation_agent", "failed", detail), prompt, diagnostics

    def _build_invalid_output_message(self, content: str, operation_mode: str) -> str:
        if operation_mode == OPERATION_MODE_DML:
            mode_hint = "SELECT / INSERT / UPDATE / DELETE"
        elif operation_mode == OPERATION_MODE_DDL:
            mode_hint = "CREATE / ALTER / DROP"
        else:
            mode_hint = "SELECT / INSERT / UPDATE / DELETE / CREATE / ALTER / DROP"
        preview = " ".join(content.strip().split())[:180] or "<empty>"
        return f"LLM 已返回内容，但清洗后未提取到有效 SQL。当前模式要求输出以 {mode_hint} 开头的单条 SQL。原始返回预览: {preview}"

    def _build_preview(self, content: str) -> str:
        return " ".join(content.strip().split())[:500] or "<empty>"

    def _sanitize_sql(self, content: str, operation_mode: str) -> str:
        candidate_segments = self._extract_candidate_segments(content)
        for segment in candidate_segments:
            extracted_sql = self._extract_first_valid_sql(segment, operation_mode)
            if extracted_sql:
                return extracted_sql
        return ""

    def _extract_candidate_segments(self, content: str) -> list[str]:
        stripped = content.strip()
        if not stripped:
            return []

        segments = [match.strip() for match in FENCED_BLOCK_PATTERN.findall(stripped) if match.strip()]
        segments.append(stripped)
        return segments

    def _extract_first_valid_sql(self, segment: str, operation_mode: str) -> str:
        cleaned = segment.replace("```", " ").strip()
        if operation_mode == OPERATION_MODE_DML:
            keyword_pattern = r"(?:select|insert|update|delete)\b"
        elif operation_mode == OPERATION_MODE_DDL:
            keyword_pattern = r"(?:create|alter|drop)\b"
        else:
            keyword_pattern = r"(?:select|insert|update|delete|create|alter|drop)\b"

        match = re.search(keyword_pattern, cleaned, flags=re.IGNORECASE)
        if match is None:
            return ""

        candidate = cleaned[match.start():].strip()
        normalized_sql = self._normalize_if_valid(candidate, operation_mode)
        if normalized_sql:
            return normalized_sql

        semicolon_positions = [index for index, char in enumerate(candidate) if char == ";"]
        for position in semicolon_positions:
            normalized_sql = self._normalize_if_valid(candidate[: position + 1].strip(), operation_mode)
            if normalized_sql:
                return normalized_sql

        accumulated_lines: list[str] = []
        last_valid = ""
        for line in candidate.splitlines():
            stripped_line = line.strip()
            if not stripped_line:
                continue
            accumulated_lines.append(stripped_line)
            combined = "\n".join(accumulated_lines)
            normalized_sql = self._normalize_if_valid(combined, operation_mode)
            if normalized_sql:
                last_valid = normalized_sql
        return last_valid

    def _normalize_if_valid(self, candidate: str, operation_mode: str) -> str:
        cleaned = candidate.strip()
        if not cleaned:
            return ""
        try:
            statements = sqlglot.parse(cleaned, read="sqlite")
        except sqlglot.errors.ParseError:
            return ""

        if len(statements) != 1:
            return ""
        statement = statements[0]
        if not self._statement_allowed(statement, operation_mode):
            return ""

        normalized_sql = statement.sql(dialect="sqlite")
        if normalized_sql and not normalized_sql.endswith(";"):
            normalized_sql = f"{normalized_sql};"
        return normalized_sql

    def _statement_allowed(self, statement: exp.Expression, operation_mode: str) -> bool:
        if operation_mode == OPERATION_MODE_QUERY:
            return isinstance(statement, exp.Select) or statement.find(exp.Select) is not None
        if operation_mode == OPERATION_MODE_DML:
            return isinstance(statement, (exp.Select, exp.Insert, exp.Update, exp.Delete)) or statement.find(exp.Select) is not None
        if operation_mode == OPERATION_MODE_DDL:
            return isinstance(statement, (exp.Create, exp.Alter, exp.Drop))
        # AUTO and anything else: allow all
        return True

class AnswerAgent:
    def __init__(self, llm: OpenAICompatibleLLM, prompt_builder: PromptBuilder, fallback_explainer: ResultExplainer, profile: LLMProfile):
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.fallback_explainer = fallback_explainer
        self.profile = profile

    def answer(self, question: str, sql: str, execution: QueryExecution, operation_mode: str = OPERATION_MODE_QUERY) -> tuple[str, AgentTrace]:
        if self.llm.is_available():
            if execution.succeeded:
                prompt = self.prompt_builder.build_answer_prompt(question, sql, execution, operation_mode)
                response = self.llm.chat(
                    system_prompt="You are a concise Chinese answer agent for analytics results.",
                    user_prompt=prompt,
                    model=self.profile.model,
                    temperature=self.profile.temperature,
                    max_tokens=self.profile.max_tokens,
                    enable_thinking=self.profile.enable_thinking,
                )
                if response is not None and response.content.strip():
                    return response.content.strip(), AgentTrace("answer_agent", "llm", "已使用快速回答 LLM 解释查询结果")
            else:
                error_msg = execution.error_message or "未知错误"
                error_prompt = (
                    f"用户想执行以下操作：{question}\n"
                    f"生成的 SQL：{sql}\n"
                    f"执行失败，原始错误信息：{error_msg}\n\n"
                    "请用一句通俗易懂的中文解释执行失败的原因，并给出修正建议。控制在 60 字以内。"
                )
                response = self.llm.chat(
                    system_prompt="你是数据库助教，用简洁中文解释 SQL 执行失败原因并给出修正建议。",
                    user_prompt=error_prompt,
                    model=self.profile.model,
                    temperature=0.2,
                    max_tokens=200,
                    enable_thinking=False,
                )
                if response is not None and response.content.strip():
                    return response.content.strip(), AgentTrace("answer_agent", "llm_error", "LLM 已解释错误原因")

        return self.fallback_explainer.explain(question, execution, operation_mode), AgentTrace(
            "answer_agent",
            "fallback_rule" if self.llm.is_available() else "rule_only",
            "使用本地解释器生成自然语言回答",
        )