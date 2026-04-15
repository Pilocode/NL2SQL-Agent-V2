from __future__ import annotations

import re

from core.database_registry import DatabaseContext
from core.models import QueryAnalysis, RoutedDatabase


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")


class DatabaseRouter:
    def __init__(self, registry: dict[str, DatabaseContext], default_database_id: str = "chinook"):
        self.registry = registry
        self.default_database_id = default_database_id

    def route(self, question: str, analysis: QueryAnalysis) -> RoutedDatabase:
        if len(self.registry) == 1:
            only_context = next(iter(self.registry.values()))
            return RoutedDatabase(
                database_id=only_context.profile.database_id,
                display_name=only_context.profile.display_name,
                reason="当前仅加载了一个数据库，直接使用默认库。",
                score=100,
            )

        normalized = question.strip().lower()
        question_terms = set(token.lower() for token in TOKEN_PATTERN.findall(normalized))
        question_terms.update(item.lower() for item in analysis.tokens)
        question_terms.update(item.lower() for item in analysis.entity_hints)
        question_terms.update(item.lower() for item in analysis.metric_hints)

        best_context = self.registry.get(self.default_database_id) or next(iter(self.registry.values()))
        best_score = -1
        best_reason = "未命中更强的库特征，回退到默认数据库。"

        for context in self.registry.values():
            score = 0
            matched_terms: list[str] = []

            for hint in context.profile.route_hints:
                if hint and hint in question_terms:
                    score += 6
                    matched_terms.append(hint)
                elif hint and hint in normalized:
                    score += 3
                    matched_terms.append(hint)

            for example in context.examples[:12]:
                for tag in example.tags:
                    lowered_tag = tag.lower()
                    if lowered_tag in question_terms:
                        score += 2
                        matched_terms.append(lowered_tag)

            profile_description = context.profile.description.lower()
            description_hits = [term for term in question_terms if len(term) >= 2 and term in profile_description]
            if description_hits:
                score += min(4, len(description_hits) * 2)
                matched_terms.extend(description_hits[:2])

            if score > best_score:
                best_context = context
                best_score = score
                best_reason = (
                    f"命中库级路由线索: {', '.join(dict.fromkeys(matched_terms))}"
                    if matched_terms
                    else "该数据库与当前问题词汇最接近。"
                )

        return RoutedDatabase(
            database_id=best_context.profile.database_id,
            display_name=best_context.profile.display_name,
            reason=best_reason,
            score=max(best_score, 0),
        )