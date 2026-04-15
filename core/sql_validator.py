from __future__ import annotations

import sqlglot
from sqlglot import exp

from core.models import OPERATION_MODE_DDL, OPERATION_MODE_DML, OPERATION_MODE_QUERY, ValidationResult


class SQLValidator:
    def validate(self, sql: str, operation_mode: str = OPERATION_MODE_QUERY) -> ValidationResult:
        if not sql.strip():
            return ValidationResult(is_valid=False, message="SQL 为空", operation_mode=operation_mode)

        try:
            parsed_statements = sqlglot.parse(sql, read="sqlite")
        except sqlglot.errors.ParseError as error:
            return ValidationResult(is_valid=False, message=f"SQL 解析失败: {error}", operation_mode=operation_mode)

        if len(parsed_statements) != 1:
            return ValidationResult(
                is_valid=False,
                message="当前版本仅允许一次执行一条 SQL 语句",
                operation_mode=operation_mode,
            )

        parsed = parsed_statements[0]
        statement_type = self._classify_statement(parsed)
        if statement_type is None:
            return ValidationResult(
                is_valid=False,
                message="当前 SQL 类型暂不支持",
                operation_mode=operation_mode,
            )

        if operation_mode == OPERATION_MODE_QUERY:
            if statement_type != "select":
                return ValidationResult(
                    is_valid=False,
                    message="当前版本只允许只读 SELECT 查询",
                    statement_type=statement_type,
                    operation_mode=operation_mode,
                )
        elif operation_mode == OPERATION_MODE_DML:
            if statement_type not in {"select", "insert", "update", "delete"}:
                return ValidationResult(
                    is_valid=False,
                    message="DML 模式仅允许 SELECT、INSERT、UPDATE、DELETE",
                    statement_type=statement_type,
                    operation_mode=operation_mode,
                )
        elif operation_mode == OPERATION_MODE_DDL:
            if statement_type not in {"create", "alter", "drop"}:
                return ValidationResult(
                    is_valid=False,
                    message="DDL 模式仅允许 CREATE、ALTER、DROP",
                    statement_type=statement_type,
                    operation_mode=operation_mode,
                )
        else:
            return ValidationResult(
                is_valid=False,
                message=f"未知的操作模式: {operation_mode}",
                statement_type=statement_type,
                operation_mode=operation_mode,
            )

        normalized_sql = parsed.sql(dialect="sqlite")
        if statement_type == "select" and parsed.find(exp.Order) is not None and parsed.find(exp.Limit) is None:
            normalized_sql = f"{normalized_sql.rstrip(';')} LIMIT 100"
            return ValidationResult(
                is_valid=True,
                message="SQL 校验通过，检测到排序查询且未设置 LIMIT，已自动补充 LIMIT 100",
                normalized_sql=normalized_sql,
                statement_type=statement_type,
                operation_mode=operation_mode,
            )

        return ValidationResult(
            is_valid=True,
            message="SQL 校验通过",
            normalized_sql=normalized_sql,
            statement_type=statement_type,
            operation_mode=operation_mode,
        )

    def _classify_statement(self, parsed: exp.Expression) -> str | None:
        if isinstance(parsed, exp.Select) or parsed.find(exp.Select) is not None:
            return "select"
        if isinstance(parsed, exp.Insert):
            return "insert"
        if isinstance(parsed, exp.Update):
            return "update"
        if isinstance(parsed, exp.Delete):
            return "delete"
        if isinstance(parsed, exp.Create):
            return "create"
        if isinstance(parsed, exp.Alter):
            return "alter"
        if isinstance(parsed, exp.Drop):
            return "drop"
        return None
