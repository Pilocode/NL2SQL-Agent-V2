from __future__ import annotations

from dataclasses import replace
import unittest

from app.config import get_settings
from app.orchestrator import NL2SQLOrchestrator
from core.sql_validator import SQLValidator


class SQLPipelineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        settings = replace(
            get_settings(),
            llm_api_key="",
            llm_model="",
            llm_analysis_model="",
            llm_thinking_model="",
            llm_generation_model="",
            llm_repair_model="",
            llm_answer_model="",
        )
        cls.orchestrator = NL2SQLOrchestrator(settings)
        cls.validator = SQLValidator()

    def test_customer_spend_pipeline_executes(self) -> None:
        response = self.orchestrator.answer_question("消费最高的 5 位客户是谁")

        self.assertIsNotNone(response.draft)
        self.assertTrue(response.validation.is_valid)
        self.assertIsNotNone(response.final_sql)
        self.assertIsNotNone(response.execution)
        assert response.execution is not None
        self.assertTrue(response.execution.succeeded)
        self.assertEqual(response.execution.row_count, 5)
        self.assertIn("Invoice", [hit.table_name for hit in response.pipeline.retrievals])
        self.assertTrue(response.answer_text)
        self.assertTrue(response.agent_traces)
        self.assertTrue(response.stage_updates)
        self.assertEqual(response.stage_updates[0].stage, "analysis")
        self.assertEqual(response.agent_traces[0].agent_name, "analysis_agent")
        self.assertIn(response.agent_traces[0].strategy, {"fallback_rule", "rule_only"})
        self.assertIsNotNone(response.pipeline.routed_database)
        assert response.pipeline.routed_database is not None
        self.assertEqual(response.pipeline.routed_database.database_id, "chinook")

    def test_ambiguous_album_popularity_question_executes(self) -> None:
        response = self.orchestrator.answer_question("帮我查一下最火的5个专辑")

        self.assertIsNotNone(response.semantic_interpretation)
        assert response.semantic_interpretation is not None
        self.assertIn("销量", response.semantic_interpretation.rewritten_question)
        self.assertTrue(response.validation.is_valid)
        self.assertIsNotNone(response.final_sql)
        assert response.final_sql is not None
        self.assertIn("FROM Album", response.final_sql)
        self.assertIn("InvoiceLine", response.final_sql)
        self.assertTrue(any(update.stage == "generation" for update in response.stage_updates))
        self.assertIsNotNone(response.execution)
        assert response.execution is not None
        self.assertTrue(response.execution.succeeded)

    def test_validator_blocks_write_statement(self) -> None:
        result = self.validator.validate("DELETE FROM Customer;")

        self.assertFalse(result.is_valid)
        self.assertIn("只读 SELECT", result.message)

    def test_validator_adds_limit_for_order_by_query(self) -> None:
        result = self.validator.validate("SELECT Name FROM Track ORDER BY UnitPrice DESC")

        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.normalized_sql)
        assert result.normalized_sql is not None
        self.assertIn("LIMIT 100", result.normalized_sql.upper())


if __name__ == "__main__":
    unittest.main()