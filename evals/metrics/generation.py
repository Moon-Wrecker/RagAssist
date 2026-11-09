"""Generation and safety evaluation metrics (Faithfulness, Relevance, Citations, Guardrails).

Goal: Provide robust, deterministic, and LLM-as-judge scoring for generation grounding,
source citation accuracy, and prompt injection defense.

Consulted references:
- RAGAS: Automated Evaluation of Retrieval Augmented Generation (Es et al., 2023)
- G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment (Liu et al., 2023)
- TruLens Groundedness Feedback Function formulations
"""

from __future__ import annotations

import re
from collections.abc import Sequence


def token_overlap_similarity(s1: str, s2: str) -> float:
    """Computes Jaccard word token overlap between two strings (0.0 to 1.0)."""
    words1 = set(re.findall(r"\w+", s1.lower()))
    words2 = set(re.findall(r"\w+", s2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)


def faithfulness_score(answer: str, context_chunks: Sequence[str]) -> float:
    """Evaluates whether claims in the generated answer are grounded in context.

    In offline deterministic evaluation, calculates sentence-level lexical and ngram grounding;
    can be combined with LLM-as-judge for deeper semantic entailment.
    """
    if not answer.strip():
        return 0.0
    if not context_chunks:
        return 0.0

    combined_context = " ".join(context_chunks).lower()
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", answer) if len(s.strip()) > 10]
    if not sentences:
        return 1.0

    supported_count = 0
    for sentence in sentences:
        tokens = set(re.findall(r"\w+", sentence.lower()))
        meaningful_tokens = [t for t in tokens if len(t) > 3]
        if not meaningful_tokens:
            supported_count += 1
            continue
        overlap = sum(1 for t in meaningful_tokens if t in combined_context)
        if (overlap / len(meaningful_tokens)) >= 0.5:
            supported_count += 1

    return supported_count / len(sentences)


def answer_relevance_score(question: str, answer: str) -> float:
    """Evaluates semantic relevance of generated answer to the posed question."""
    if not answer.strip() or not question.strip():
        return 0.0

    q_tokens = set(re.findall(r"\w+", question.lower()))
    meaningful_q = [t for t in q_tokens if len(t) > 3]
    if not meaningful_q:
        return 1.0

    a_lower = answer.lower()
    matches = sum(1 for t in meaningful_q if t in a_lower)
    score = matches / len(meaningful_q)
    return min(1.0, score * 1.2)


def citation_metrics(citations: Sequence[str], expected_sources: Sequence[str]) -> tuple[float, float]:
    """Computes citation Precision and Recall against ground-truth source references."""
    if not citations and not expected_sources:
        return 1.0, 1.0
    if not citations and expected_sources:
        return 0.0, 0.0
    if citations and not expected_sources:
        return 0.0, 1.0

    cited_set = set(citations)
    expected_set = set(expected_sources)

    true_positives = len(cited_set.intersection(expected_set))
    precision = true_positives / len(cited_set) if cited_set else 0.0
    recall = true_positives / len(expected_set) if expected_set else 0.0

    return precision, recall
