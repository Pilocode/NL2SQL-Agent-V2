from __future__ import annotations

import re

from core.database_registry import DatabaseContext
from core.models import ExampleCandidate, QueryAnalysis


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")


class ExampleRetriever:
    def __init__(self, registry: dict[str, DatabaseContext]):
        self.registry = registry

    def retrieve(self, question: str, analysis: QueryAnalysis, database_id: str, limit: int = 8) -> tuple[ExampleCandidate, ...]:
        context = self.registry.get(database_id)
        if context is None or not context.examples:
            return ()

        search_terms = self._build_search_terms(question, analysis)
        scored_examples: list[tuple[int, ExampleCandidate]] = []
        for example in context.examples:
            score = self._score_example(example, search_terms, analysis)
            if score > 0:
                scored_examples.append((score, example))

        if not scored_examples:
            return context.examples[:limit]

        scored_examples.sort(key=lambda item: (-item[0], item[1].question))
        return tuple(example for _, example in scored_examples[:limit])

    def _build_search_terms(self, question: str, analysis: QueryAnalysis) -> set[str]:
        terms = set(token.lower() for token in TOKEN_PATTERN.findall(question.strip().lower()))
        terms.update(item.lower() for item in analysis.tokens)
        terms.update(item.lower() for item in analysis.metric_hints)
        terms.update(item.lower() for item in analysis.entity_hints)
        terms.update(item.lower() for item in analysis.intent_tags)
        return {term for term in terms if term}

    def _score_example(self, example: ExampleCandidate, search_terms: set[str], analysis: QueryAnalysis) -> int:
        score = 0
        normalized_question = example.question.strip().lower()

        for term in search_terms:
            if term in normalized_question:
                score += 3

        for tag in example.tags:
            if tag.lower() in search_terms:
                score += 6

        for metric in analysis.metric_hints:
            if metric.lower() in example.tags:
                score += 4

        for entity in analysis.entity_hints:
            if entity.lower() in example.tags:
                score += 4

        for intent in analysis.intent_tags:
            if intent.lower() in example.tags:
                score += 2

        return score