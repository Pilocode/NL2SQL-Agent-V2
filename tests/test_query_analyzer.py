from __future__ import annotations

import unittest
from pathlib import Path

from core.query_analyzer import QueryAnalyzer
from core.schema_loader import load_semantic_layer


ROOT_DIR = Path(__file__).resolve().parents[1]


class QueryAnalyzerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        semantic_layer = load_semantic_layer(ROOT_DIR / "data" / "processed" / "semantic_layer.json")
        cls.analyzer = QueryAnalyzer(semantic_layer)

    def test_extracts_metric_entity_and_top_k(self) -> None:
        analysis = self.analyzer.analyze("客户最多的 5 个国家有哪些")

        self.assertIn("count", analysis.intent_tags)
        self.assertIn("ranking", analysis.intent_tags)
        self.assertIn("客户", analysis.entity_hints)
        self.assertIn("国家", analysis.entity_hints)
        self.assertEqual(analysis.top_k, 5)

    def test_extracts_time_grain(self) -> None:
        analysis = self.analyzer.analyze("2009 年有多少笔订单")

        self.assertEqual(analysis.time_grain, "year")
        self.assertIn("count", analysis.intent_tags)
        self.assertIn("订单", analysis.entity_hints)

    def test_extracts_ambiguous_terms(self) -> None:
        analysis = self.analyzer.analyze("帮我查一下最火的5个专辑")

        self.assertIn("最火", analysis.ambiguous_terms)
        self.assertIn("专辑", analysis.entity_hints)
        self.assertEqual(analysis.top_k, 5)


if __name__ == "__main__":
    unittest.main()