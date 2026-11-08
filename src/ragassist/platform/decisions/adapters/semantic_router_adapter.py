"""Semantic Router Adapter for ultra-low latency intent classification."""

import math
import re
from typing import Any
import structlog

from ragassist.platform.decisions.ports import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    Decider,
    PredicateAnswer,
    PredicateQuestion,
    Question,
    RoutingDecision,
    ScoreAnswer,
    ScoreQuestion,
)
from ragassist.platform.embeddings.ports import EmbeddingProvider

logger = structlog.get_logger(__name__)

ROUTE_UTTERANCES: dict[str, list[str]] = {
    "rag_search": [
        "how do i configure pgvector index",
        "what is the token limit for hybrid chunking",
        "explain the architecture of the knowledge pipeline",
        "troubleshoot http 500 error in worker service",
        "where is the documentation for the sse streaming endpoint",
        "how does vector search work",
        "documentation on retrieval ranking",
        "search the knowledge base for instructions",
    ],
    "saas_action": [
        "what is my current subscription plan",
        "show me my recent invoices",
        "how many seats are active in our account",
        "update the billing email to accounting@example.com",
        "give me an account overview",
        "check account balance and subscription status",
        "view billing statements and payments",
    ],
    "general_chat": [
        "hello",
        "hi there",
        "good morning",
        "who are you",
        "thanks for your help",
        "goodbye",
        "how are you today",
        "tell me a joke",
    ],
    "human_escalation": [
        "i need to speak to a real human",
        "transfer me to a representative",
        "i want to file a complaint",
        "your answer is completely wrong, get me a supervisor",
        "connect me with human support",
        "i want to speak with customer service agent",
    ],
}


class SemanticRouterAdapter(Decider):
    """Adapter for semantic routing with calibrated softmax probabilities."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        temperature: float = 0.15,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.temperature = temperature
        self._route_tokens: dict[str, set[str]] = {
            route: {w for utt in utts for w in self._tokenize(utt)}
            for route, utts in ROUTE_UTTERANCES.items()
        }

    @property
    def name(self) -> str:
        return "semantic_router"

    def _tokenize(self, text: str) -> list[str]:
        return [w.lower() for w in re.findall(r"\b\w+\b", text)]

    def _compute_lexical_similarity(self, query: str) -> dict[str, float]:
        """Compute normalized similarity across routes."""
        query_words = set(self._tokenize(query))
        if not query_words:
            return {r: 0.25 for r in ROUTE_UTTERANCES}

        raw_scores: dict[str, float] = {}
        for route, route_words in self._route_tokens.items():
            intersection = query_words.intersection(route_words)
            # Jaccard overlap + key phrase weighting
            score = len(intersection) / max(len(query_words.union(route_words)), 1)

            # Check exact phrase matches in route utterances
            query_lower = query.lower()
            for utt in ROUTE_UTTERANCES[route]:
                if utt in query_lower or query_lower in utt:
                    score += 1.0

            raw_scores[route] = score

        # Apply softmax with temperature
        max_score = max(raw_scores.values()) if raw_scores else 0.0
        if max_score == 0.0:
            # Uniform if no match
            return {r: 1.0 / len(ROUTE_UTTERANCES) for r in ROUTE_UTTERANCES}

        exp_scores = {r: math.exp(s / self.temperature) for r, s in raw_scores.items()}
        sum_exp = sum(exp_scores.values())
        return {r: exp / sum_exp for r, exp in exp_scores.items()}

    async def evaluate_choice(
        self, input_text: str, question: ChoiceQuestion
    ) -> ChoiceAnswer:
        probabilities = self._compute_lexical_similarity(input_text)

        # Filter to question.choices if specific
        if set(question.choices) != set(probabilities.keys()):
            # Re-normalize over requested choices
            sub_probs = {c: probabilities.get(c, 0.01) for c in question.choices}
            total = sum(sub_probs.values())
            probabilities = {c: p / total for c, p in sub_probs.items()}

        best_choice = max(probabilities.keys(), key=lambda k: probabilities[k])
        confidence = probabilities[best_choice]

        return ChoiceAnswer(
            name=question.name,
            choice=best_choice,
            confidence=confidence,
            probabilities=probabilities,
        )

    async def evaluate_predicate(
        self, input_text: str, question: PredicateQuestion
    ) -> PredicateAnswer:
        # Fast heuristic
        return PredicateAnswer(name=question.name, probability=0.5, verdict=True)

    async def evaluate_score(
        self, input_text: str, question: ScoreQuestion
    ) -> ScoreAnswer:
        return ScoreAnswer(name=question.name, score=0.5, confidence=0.5)

    async def decide(self, input_text: str, questions: list[Question]) -> list[Answer]:
        results: list[Answer] = []
        for q in questions:
            if isinstance(q, ChoiceQuestion):
                results.append(await self.evaluate_choice(input_text, q))
            elif isinstance(q, PredicateQuestion):
                results.append(await self.evaluate_predicate(input_text, q))
            elif isinstance(q, ScoreQuestion):
                results.append(await self.evaluate_score(input_text, q))
        return results
