from __future__ import annotations

import unittest

from core.database_registry import DatabaseContext
from core.database_router import DatabaseRouter
from core.models import DatabaseProfile, ExampleCandidate, QueryAnalysis, TableProfile


class DatabaseRouterTestCase(unittest.TestCase):
    def test_routes_to_chinook_for_music_store_question(self) -> None:
        registry = {
            "chinook": DatabaseContext(
                profile=DatabaseProfile(
                    database_id="chinook",
                    display_name="Chinook",
                    description="数字音乐商店数据库",
                    dialect="sqlite",
                    route_hints=("客户", "订单", "歌曲", "专辑", "艺人"),
                ),
                schema_catalog=(TableProfile(name="Customer", row_count=59), TableProfile(name="Invoice", row_count=412)),
                semantic_layer={},
                examples=(
                    ExampleCandidate(
                        question="消费最高的客户是谁",
                        sql="SELECT 1;",
                        explanation="",
                        tags=("客户", "消费"),
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
                    route_hints=("singer", "stadium", "concert"),
                ),
                schema_catalog=(TableProfile(name="singer", row_count=0), TableProfile(name="stadium", row_count=0)),
                semantic_layer={},
                examples=(
                    ExampleCandidate(
                        question="which singer performed in the stadium",
                        sql="SELECT 1;",
                        explanation="",
                        tags=("singer", "stadium"),
                        database_id="concert_singer",
                    ),
                ),
            ),
        }
        router = DatabaseRouter(registry)
        analysis = QueryAnalysis(
            original_question="消费最高的客户是谁",
            normalized_question="消费最高的客户是谁",
            tokens=("客户", "消费"),
            metric_hints=("消费",),
            entity_hints=("客户",),
        )

        routed = router.route("消费最高的客户是谁", analysis)

        self.assertEqual(routed.database_id, "chinook")

    def test_routes_to_spider_database_when_domain_hints_match(self) -> None:
        registry = {
            "chinook": DatabaseContext(
                profile=DatabaseProfile(
                    database_id="chinook",
                    display_name="Chinook",
                    description="数字音乐商店数据库",
                    dialect="sqlite",
                    route_hints=("客户", "订单", "歌曲", "专辑", "艺人"),
                ),
                schema_catalog=(TableProfile(name="Customer", row_count=59),),
                semantic_layer={},
                examples=(),
            ),
            "concert_singer": DatabaseContext(
                profile=DatabaseProfile(
                    database_id="concert_singer",
                    display_name="concert_singer",
                    description="Spider 演唱会数据库",
                    dialect="sqlite",
                    route_hints=("singer", "stadium", "concert"),
                ),
                schema_catalog=(TableProfile(name="singer", row_count=0), TableProfile(name="stadium", row_count=0)),
                semantic_layer={},
                examples=(),
            ),
        }
        router = DatabaseRouter(registry)
        analysis = QueryAnalysis(
            original_question="which singer performed in the stadium",
            normalized_question="which singer performed in the stadium",
            tokens=("singer", "stadium"),
            entity_hints=("singer", "stadium"),
        )

        routed = router.route("which singer performed in the stadium", analysis)

        self.assertEqual(routed.database_id, "concert_singer")


if __name__ == "__main__":
    unittest.main()