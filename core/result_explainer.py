from __future__ import annotations

from core.models import OPERATION_MODE_QUERY, QueryExecution


WRITE_STATEMENT_LABELS = {
    "insert": "写入",
    "update": "更新",
    "delete": "删除",
}

DDL_STATEMENT_LABELS = {
    "create": "创建",
    "alter": "修改",
    "drop": "删除",
}


class ResultExplainer:
    def explain(self, question: str, execution: QueryExecution, operation_mode: str = OPERATION_MODE_QUERY) -> str:
        if not execution.succeeded:
            return execution.error_message or "查询失败，当前未能返回结果。"

        if execution.statement_type in WRITE_STATEMENT_LABELS:
            action = WRITE_STATEMENT_LABELS[execution.statement_type]
            if execution.affected_rows > 0:
                return f"已成功执行{action}操作，影响 {execution.affected_rows} 行数据。"
            return f"{action}操作已执行成功，但没有影响任何数据。"

        if execution.statement_type in DDL_STATEMENT_LABELS:
            action = DDL_STATEMENT_LABELS[execution.statement_type]
            return f"已成功执行数据库结构{action}操作。"

        if execution.row_count == 0:
            return "没有查到符合条件的数据。"

        if execution.row_count == 1 and len(execution.columns) == 1:
            return f"查询结果是 {execution.rows[0][0]}。"

        first_row = execution.rows[0] if execution.rows else ()
        if execution.row_count == 1 and len(execution.columns) >= 2:
            leading_pairs = [f"{column}: {value}" for column, value in zip(execution.columns, first_row)]
            return f"关于“{question}”，查询结果为：" + "，".join(leading_pairs) + "。"

        preview_values = []
        for row in execution.rows[:3]:
            preview_values.append(" / ".join(str(value) for value in row[:2]))
        preview_text = "；".join(preview_values)
        return f"已查询到 {execution.row_count} 条结果，前几项包括：{preview_text}。"