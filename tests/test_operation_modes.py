from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.config import get_settings
from app.orchestrator import NL2SQLOrchestrator
from core.local_db_assets import build_local_database_assets, delete_local_database_assets
from core.models import AgentTrace, OPERATION_MODE_DDL, OPERATION_MODE_DML, SQLDraft
from core.sql_validator import SQLValidator


class _StubGenerationAgent:
    def __init__(self, sql: str) -> None:
        self.sql = sql

    def generate(self, *args, **kwargs):
        draft = SQLDraft(
            sql=self.sql,
            source="stub",
            rationale="测试中直接注入预期 SQL。",
            prompt="stub prompt",
        )
        return draft, AgentTrace("generation_agent", "stub", self.sql), "stub prompt"


class OperationModePipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "school.sqlite"
        self._create_test_database(self.database_path)
        asset_paths = build_local_database_assets(self.database_path)
        settings = replace(
            get_settings(),
            database_path=self.database_path,
            schema_metadata_path=asset_paths["metadata"],
            semantic_layer_path=asset_paths["semantic"],
            demo_questions_path=asset_paths["examples"],
            enable_spider_rag=False,
            llm_api_key="",
            llm_model="",
            llm_analysis_model="",
            llm_thinking_model="",
            llm_generation_model="",
            llm_repair_model="",
            llm_answer_model="",
        )
        self.orchestrator = NL2SQLOrchestrator(settings)
        self.validator = SQLValidator()

    def tearDown(self) -> None:
        delete_local_database_assets(self.database_path)
        self.temp_dir.cleanup()

    def test_dml_insert_executes_successfully(self) -> None:
        self.orchestrator.generation_agents[self.orchestrator.default_database_id] = _StubGenerationAgent(
            "INSERT INTO Student(student_id, name, class_name) VALUES ('S1002', '李青', '软工2302');"
        )

        response = self.orchestrator.answer_question(
            "向 Student 表新增一条学生记录，学号 S1002，姓名 李青，班级 软工2302",
            operation_mode=OPERATION_MODE_DML,
        )

        self.assertTrue(response.validation.is_valid)
        self.assertEqual(response.validation.statement_type, "insert")
        self.assertEqual(response.operation_mode, OPERATION_MODE_DML)
        self.assertIsNotNone(response.execution)
        assert response.execution is not None
        self.assertTrue(response.execution.succeeded)
        self.assertEqual(response.execution.statement_type, "insert")
        self.assertEqual(response.execution.affected_rows, 1)
        self.assertIn("影响 1 行数据", response.answer_text)

        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT student_id, name, class_name FROM Student WHERE student_id = 'S1002'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row, ("S1002", "李青", "软工2302"))

    def test_ddl_create_table_executes_successfully(self) -> None:
        self.orchestrator.generation_agents[self.orchestrator.default_database_id] = _StubGenerationAgent(
            "CREATE TABLE Course (course_id TEXT PRIMARY KEY, course_name TEXT NOT NULL, credit INTEGER NOT NULL);"
        )

        response = self.orchestrator.answer_question(
            "创建一张课程表，包含课程编号、课程名、学分",
            operation_mode=OPERATION_MODE_DDL,
        )

        self.assertTrue(response.validation.is_valid)
        self.assertEqual(response.validation.statement_type, "create")
        self.assertEqual(response.operation_mode, OPERATION_MODE_DDL)
        self.assertIsNotNone(response.execution)
        assert response.execution is not None
        self.assertTrue(response.execution.succeeded)
        self.assertEqual(response.execution.statement_type, "create")
        self.assertIn("数据库结构", response.answer_text)

        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='Course'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row, ("Course",))

    def test_validator_enforces_operation_mode_boundaries(self) -> None:
        dml_result = self.validator.validate(
            "INSERT INTO Student(student_id, name, class_name) VALUES ('S1003', '王晨', '软工2301');",
            operation_mode=OPERATION_MODE_DML,
        )
        ddl_result = self.validator.validate(
            "CREATE TABLE Demo (id INTEGER PRIMARY KEY);",
            operation_mode=OPERATION_MODE_DDL,
        )
        invalid_result = self.validator.validate(
            "CREATE TABLE Demo (id INTEGER PRIMARY KEY);",
            operation_mode=OPERATION_MODE_DML,
        )

        self.assertTrue(dml_result.is_valid)
        self.assertEqual(dml_result.statement_type, "insert")
        self.assertTrue(ddl_result.is_valid)
        self.assertEqual(ddl_result.statement_type, "create")
        self.assertFalse(invalid_result.is_valid)
        self.assertIn("DML 模式", invalid_result.message)

    @staticmethod
    def _create_test_database(database_path: Path) -> None:
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE Student (
                    student_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    class_name TEXT NOT NULL
                );

                INSERT INTO Student(student_id, name, class_name)
                VALUES ('S1001', '张敏', '软工2301');
                """
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
