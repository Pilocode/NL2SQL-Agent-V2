from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from core.models import QueryExecution


class SQLiteExecutor:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def query(self, sql: str) -> pd.DataFrame:
        connection = sqlite3.connect(self.database_path)
        try:
            return pd.read_sql_query(sql, connection)
        finally:
            connection.close()

    def execute(self, sql: str) -> QueryExecution:
        statement_type = self._detect_statement_type(sql)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            if statement_type == "select":
                frame = pd.read_sql_query(sql, connection)
                rows = tuple(tuple(row) for row in frame.itertuples(index=False, name=None))
                return QueryExecution(
                    succeeded=True,
                    sql=sql,
                    columns=tuple(str(column) for column in frame.columns),
                    rows=rows,
                    row_count=len(frame),
                    affected_rows=len(frame),
                    statement_type=statement_type,
                )

            cursor = connection.cursor()
            cursor.execute(sql)
            connection.commit()
            affected_rows = max(cursor.rowcount, 0)
            return QueryExecution(
                succeeded=True,
                sql=sql,
                row_count=affected_rows,
                affected_rows=affected_rows,
                statement_type=statement_type,
            )
        finally:
            connection.close()

    def _detect_statement_type(self, sql: str) -> str | None:
        normalized = sql.lstrip().lower()
        for statement_type in ("select", "insert", "update", "delete", "create", "alter", "drop"):
            if normalized.startswith(statement_type):
                return statement_type
        return None
