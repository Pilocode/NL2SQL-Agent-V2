from __future__ import annotations

import unittest
from pathlib import Path

from core.models import ColumnProfile, TableProfile
from core.query_analyzer import QueryAnalyzer
from core.schema_loader import load_schema_catalog
from core.schema_retriever import SchemaRetriever


ROOT_DIR = Path(__file__).resolve().parents[1]


class SchemaRetrieverTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_catalog = load_schema_catalog(
            ROOT_DIR / "data" / "processed" / "schema_metadata.json",
            ROOT_DIR / "data" / "processed" / "semantic_layer.json",
        )
        cls.analyzer = QueryAnalyzer()
        cls.retriever = SchemaRetriever(schema_catalog)

    def test_customer_question_hits_customer_and_invoice(self) -> None:
        question = "消费最高的客户有哪些"
        analysis = self.analyzer.analyze(question)
        hits = self.retriever.retrieve(question, analysis.tokens)
        table_names = [item.table_name for item in hits[:2]]
        self.assertIn("Customer", table_names)
        self.assertIn("Invoice", table_names)

    def test_track_question_hits_track(self) -> None:
        question = "每种媒体类型有多少首歌曲"
        analysis = self.analyzer.analyze(question)
        hits = self.retriever.retrieve(question, analysis.tokens)
        table_names = [item.table_name for item in hits[:3]]
        self.assertIn("Track", table_names)
        self.assertIn("MediaType", table_names)

    def test_summary_descriptions_improve_table_retrieval(self) -> None:
        schema_catalog = (
            TableProfile(
                name="orders",
                row_count=10,
                description="记录销售流水与订单结算信息。",
                columns=(
                    ColumnProfile(name="id", data_type="INTEGER", nullable=False, is_primary_key=True, description="订单唯一标识。"),
                    ColumnProfile(name="amount", data_type="REAL", nullable=False, description="销售流水金额。"),
                ),
            ),
            TableProfile(
                name="employees",
                row_count=3,
                description="记录员工档案信息。",
                columns=(
                    ColumnProfile(name="name", data_type="TEXT", nullable=False, description="员工姓名。"),
                ),
            ),
        )
        retriever = SchemaRetriever(schema_catalog)
        analyzer = QueryAnalyzer()

        question = "请看一下销售流水情况"
        analysis = analyzer.analyze(question)
        hits = retriever.retrieve(question, analysis.tokens)

        self.assertTrue(hits)
        self.assertEqual(hits[0].table_name, "orders")


if __name__ == "__main__":
    unittest.main()
