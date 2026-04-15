from __future__ import annotations

import unittest

from core.database_registry import DatabaseContext
from core.example_retriever import ExampleRetriever
from core.models import DatabaseProfile, ExampleCandidate, QueryAnalysis, TableProfile


class ExampleRetrieverTestCase(unittest.TestCase):
    def test_retrieves_examples_within_routed_database(self) -> None:
        registry = {
            "chinook": DatabaseContext(
                profile=DatabaseProfile(
                    database_id="chinook",
                    display_name="Chinook",
                    description="数字音乐商店数据库",
                    dialect="sqlite",
                ),
                schema_catalog=(TableProfile(name="Customer", row_count=59),),
                semantic_layer={},
                examples=(
                    ExampleCandidate(
                        question="消费最高的客户是谁",
                        sql="SELECT 1;",
                        explanation="",
                        tags=("客户", "消费", "ranking"),
                        database_id="chinook",
                    ),
                ),
            ),
            "concert_singer": DatabaseContext(
                profile=DatabaseProfile(
                    database_id="concert_singer",
                    display_name="concert_singer",
                    description="Spider 演唱会数据库",
                    dialect="sqlite",
                ),
                schema_catalog=(TableProfile(name="singer", row_count=0),),
                semantic_layer={},
                examples=(
                    ExampleCandidate(
                        question="which singer performed in the stadium",
                        sql="SELECT singer.name FROM singer;",
                        explanation="",
                        tags=("singer", "stadium", "concert"),
                        database_id="concert_singer",
                        source="spider_train",
                    ),
                ),
            ),
        }
        retriever = ExampleRetriever(registry)
        analysis = QueryAnalysis(
            original_question="which singer performed in the stadium",
            normalized_question="which singer performed in the stadium",
            tokens=("singer", "stadium"),
            entity_hints=("singer",),
        )

        examples = retriever.retrieve("which singer performed in the stadium", analysis, "concert_singer")

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0].database_id, "concert_singer")
        self.assertEqual(examples[0].source, "spider_train")


if __name__ == "__main__":
    unittest.main()