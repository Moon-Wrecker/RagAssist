# RagAssist Evaluation Benchmark Report

- **Total Test Cases Evaluated**: 80
- **Total Evaluation Duration**: 0.04 seconds
- **Evaluation Mode**: Offline Hermetic Simulation

## 1. Quality & Accuracy Metrics

| Metric | Target | Benchmark Score | Status |
|---|:---:|:---:|:---:|
| **Retrieval Hit@5** | >= 0.90 | **1.000** | PASSED |
| **Retrieval MRR@5** | >= 0.80 | **1.000** | PASSED |
| **Retrieval nDCG@5** | >= 0.85 | **1.000** | PASSED |
| **Answer Faithfulness (Grounding)** | >= 0.90 | **0.995** | PASSED |
| **Answer Relevance** | >= 0.85 | **0.955** | PASSED |
| **Citation Precision** | >= 0.85 | **1.000** | PASSED |
| **Citation Recall** | >= 0.85 | **1.000** | PASSED |
| **Prompt Injection Defense** | 1.00 | **100.0%** | PASSED |
| **Escalation Accuracy** | >= 0.95 | **100.0%** | PASSED |

## 2. Latency & Token Consumption

| Metric | Value |
|---|:---:|
| Mean Latency | 37.9 ms |
| p50 Latency | 41.2 ms |
| p90 Latency | 52.3 ms |
| p95 Latency | 53.1 ms |
| p99 Latency | 53.8 ms |
| Total Input Tokens | 16,280 |
| Total Output Tokens | 5,170 |
| Avg Tokens / Query | 268.1 |

## 3. Breakdown by Category

| Category | Test Count | Avg Latency (ms) | Faithfulness | Relevance | Hit@5 |
|---|:---:|:---:|:---:|:---:|:---:|
| `account_tools` | 20 | 38.8 | 0.980 | 0.960 | 1.000 |
| `documentation` | 35 | 49.4 | 1.000 | 0.931 | 1.000 |
| `escalation` | 15 | 27.9 | 1.000 | 1.000 | 1.000 |
| `safety` | 10 | 17.5 | 1.000 | 1.000 | 1.000 |
