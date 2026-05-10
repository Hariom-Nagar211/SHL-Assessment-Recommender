# Conversational SHL Assessment Recommender - Approach

## Overview

The service is a stateless FastAPI application that recommends SHL assessments from a local copy of the SHL Individual Test Solutions catalog. It exposes the required endpoints:

- `GET /health` returns `{"status": "ok"}`.
- `POST /chat` accepts the full conversation history and returns `reply`, `recommendations`, and `end_of_conversation` using the exact required schema.

I chose a deterministic retrieval-first design rather than a fully LLM-driven agent. The evaluator checks schema compliance, catalog grounding, turn limits, refusal behavior, and recall. A rule-based orchestration layer is easier to test, faster under a 30 second timeout, and safer because every recommendation is selected directly from the scraped catalog.

## Catalog Processing

The catalog is stored in `shl_product_catalog.json` and loaded at application startup. Each valid item is normalized into a `CatalogItem` containing:

- name
- catalog URL
- description
- assessment categories from `keys`
- job levels
- duration
- remote/adaptive flags
- combined searchable text

The loader uses Python's JSON parser with `strict=False` because the scraped catalog contains at least one raw newline inside a product name. This keeps the service robust without modifying the source catalog.

Recommendations only return URLs present in the loaded catalog. The service does not generate or accept external assessment URLs.

## Conversation Strategy

The API is stateless. Every call reconstructs intent from the supplied message history. Only user messages are used as recommendation context so that earlier assistant replies do not accidentally become search requirements.

The agent handles four major paths:

1. Clarification: if the user request is too vague, such as "I need an assessment", the service asks for the role and the skills or traits to measure. It returns no recommendations.
2. Recommendation: once the user provides enough role or skill context, the service ranks catalog items and returns 1 to 10 recommendations.
3. Refinement: because the full user history is reprocessed on every call, changes like "Actually add personality tests" update the shortlist while preserving previous constraints such as Java or seniority.
4. Comparison: comparison requests such as "OPQ vs GSA" are detected separately. Common abbreviations are mapped to catalog items, and the response is grounded in catalog names, categories, and descriptions.

The service also refuses out-of-scope requests, including general legal/hiring advice and prompt-injection attempts. Refusals return an empty recommendation list.

## Retrieval and Ranking

Ranking is lexical and category-aware:

- exact token matches in assessment names receive the highest weight;
- matches in descriptions, job levels, and metadata receive lower weight;
- category hints map user language to SHL catalog categories, for example:
  - Java, SQL, coding, developer -> `Knowledge & Skills`
  - personality, behavior, OPQ -> `Personality & Behavior`
  - reasoning, aptitude, numerical -> `Ability & Aptitude`
  - leadership, stakeholder, communication -> `Competencies`
- seniority hints such as entry-level, mid-level, graduate, and manager are matched against catalog job levels;
- known aliases such as `OPQ`, `OPQ32r`, `GSA`, and `MQ` map to canonical catalog product names.

The ranker also applies light product-quality adjustments. For example, it slightly favors assessment-like products over reports, guides, profiler cards, or pre-packaged solutions unless the user explicitly names them. This helps keep shortlists closer to usable assessments while still allowing named comparisons.

## Testing and Evaluation

I added evaluator-style tests in `test_app.py` using FastAPI's `TestClient`. The tests cover:

- health endpoint readiness;
- strict response schema;
- no recommendations for vague queries;
- Java role recommendation;
- refinement with personality tests;
- OPQ/GSA comparison;
- refusal of prompt injection;
- all recommendation URLs coming from the local catalog.

Current local result:

```text
6 passed
```

## What Did Not Work Initially

The first JSON load failed because the scraped catalog contains a raw newline inside a string. I fixed this by using tolerant JSON parsing.

The first ranker used substring matching, which caused accidental matches such as "here" matching inside "Anywhere". I replaced it with token-boundary matching.

The first refinement pass used all messages, including assistant replies, as search context. That made assistant text pollute later recommendations. The current version uses only user messages for retrieval context.

## Interview Design Notes

If asked why I did not start with an LLM-heavy agent:

The assignment rewards grounded catalog recommendations and strict schema reliability. A deterministic retrieval layer gives predictable behavior, is easier to test, and avoids hallucinated assessments or URLs. An LLM could be added later for natural-language rewriting, but I would keep final recommendation selection constrained to catalog IDs.

If asked how I would improve recall:

I would add embeddings over product name, description, keys, and job levels, then combine vector similarity with the current lexical/category score. I would also tune against the provided public traces by measuring Recall@10 after each ranking change.

If asked how I prevent hallucinations:

The service never asks the model to invent products. It loads catalog items into memory and recommendations are serialized only from `CatalogItem` objects. The tests assert every returned URL exists in the catalog.

If asked how stateless refinement works:

The service re-reads the complete user message history on every request. Earlier user constraints remain active, and newer user constraints add or override intent. No server-side session memory is required.

If asked about trade-offs:

The current approach is robust, fast, and explainable, but it may miss semantic matches that do not share words with the query. Embedding retrieval and trace-driven tuning would be my next upgrades.
