from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


OPERATION_MODE_QUERY = "query"
OPERATION_MODE_DML = "dml"
OPERATION_MODE_DDL = "ddl"
OPERATION_MODES = (OPERATION_MODE_QUERY, OPERATION_MODE_DML, OPERATION_MODE_DDL)


@dataclass(frozen=True)
class ForeignKey:
    column: str
    references_table: str
    references_column: str


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool = False
    aliases: tuple[str, ...] = ()
    description: str = ""
    foreign_key: ForeignKey | None = None


@dataclass(frozen=True)
class TableProfile:
    name: str
    row_count: int
    columns: tuple[ColumnProfile, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class QueryAnalysis:
    original_question: str
    normalized_question: str
    tokens: tuple[str, ...]
    intent_tags: tuple[str, ...] = ()
    metric_hints: tuple[str, ...] = ()
    entity_hints: tuple[str, ...] = ()
    ambiguous_terms: tuple[str, ...] = ()
    time_grain: str | None = None
    top_k: int | None = None
    is_follow_up: bool = False


@dataclass(frozen=True)
class RetrievalHit:
    table_name: str
    score: int
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]
    row_count: int
    columns: tuple[ColumnProfile, ...] = ()


@dataclass(frozen=True)
class ExampleCandidate:
    question: str
    sql: str
    explanation: str
    tags: tuple[str, ...] = ()
    database_id: str = "chinook"
    source: str = "local_demo"


@dataclass(frozen=True)
class RoutedDatabase:
    database_id: str
    display_name: str
    reason: str
    score: int = 0


@dataclass(frozen=True)
class DatabaseProfile:
    database_id: str
    display_name: str
    description: str
    dialect: str
    database_path: Path | None = None
    route_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineResult:
    analysis: QueryAnalysis
    retrievals: tuple[RetrievalHit, ...]
    example_candidates: tuple[ExampleCandidate, ...]
    routed_database: RoutedDatabase | None = None
    operation_mode: str = OPERATION_MODE_QUERY


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    message: str
    normalized_sql: str | None = None
    statement_type: str | None = None
    operation_mode: str = OPERATION_MODE_QUERY


@dataclass(frozen=True)
class SQLDraft:
    sql: str
    source: str
    rationale: str
    prompt: str


@dataclass(frozen=True)
class RepairResult:
    sql: str
    strategy: str
    message: str


@dataclass(frozen=True)
class RepairStep:
    reason: str
    sql_before: str
    sql_after: str


@dataclass(frozen=True)
class QueryExecution:
    succeeded: bool
    sql: str
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[object, ...], ...] = ()
    row_count: int = 0
    affected_rows: int = 0
    statement_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class AgentTrace:
    agent_name: str
    strategy: str
    detail: str


@dataclass(frozen=True)
class StageUpdate:
    stage: str
    message: str


@dataclass(frozen=True)
class SemanticInterpretation:
    rewritten_question: str
    resolved_metric: str
    resolved_entity: str
    assumptions: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class NL2SQLResponse:
    pipeline: PipelineResult
    prompt: str
    draft: SQLDraft | None
    validation: ValidationResult
    semantic_interpretation: SemanticInterpretation | None = None
    repairs: tuple[RepairStep, ...] = ()
    final_sql: str | None = None
    execution: QueryExecution | None = None
    answer_text: str = ""
    agent_traces: tuple[AgentTrace, ...] = ()
    stage_updates: tuple[StageUpdate, ...] = ()
    operation_mode: str = OPERATION_MODE_QUERY
