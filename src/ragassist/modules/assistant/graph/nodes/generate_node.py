"""Generation node producing grounded answers with citations."""

from __future__ import annotations

import re
from typing import Any
from langchain_core.messages import HumanMessage

from ragassist.modules.assistant.graph.state import AssistantState


def make_generate_node(generator_tiers: dict[str, Any]):  # type: ignore[no-untyped-def]
    async def generate(state: AssistantState) -> dict[str, Any]:
        count = state.get("generate_count", 0) + 1
        complexity = float(state.get("complexity", 2.0))
        tier = "cheap" if complexity < 2.0 else "strong"

        model_entry = generator_tiers.get(tier)
        if not model_entry:
            model_entry = generator_tiers.get("strong") or generator_tiers.get("cheap")

        models = model_entry if isinstance(model_entry, list) else [model_entry]

        # Format context passages
        chunks = state.get("graded_chunks", [])
        if chunks:
            parts: list[str] = []
            for idx, c in enumerate(chunks, start=1):
                title = getattr(c, "title", "")
                parts.append(f"[{idx}] {title}\n{c.text}")
            formatted_context = "\n\n".join(parts)
            prompt_content = (
                f"You are RagAssist, a helpful customer assistant.\n"
                f"Answer the question using strictly the provided facts.\n"
                f"Cite sources using bracketed numbers like [1].\n\n"
                f"<untrusted_document_context>\n{formatted_context}\n</untrusted_document_context>\n\n"
                f"Question: {state['question']}"
            )
        else:
            prompt_content = (
                f"You are RagAssist, a helpful customer assistant.\n"
                f"Question: {state['question']}"
            )

        messages = [HumanMessage(content=prompt_content)]

        ans_text = ""
        used_model_name = ""
        last_error: Exception | None = None

        for model in models:
            try:
                tokens: list[str] = []
                async for chunk in model.astream(messages):
                    content = getattr(chunk, "content", "")
                    tokens.append(str(content))
                ans_text = "".join(tokens)
                used_model_name = getattr(
                    model, "label", getattr(model, "model_name", getattr(model, "_llm_type", "model"))
                )
                break
            except Exception as exc:
                last_error = exc
                continue

        if not ans_text and last_error is not None:
            raise last_error

        # Parse citations
        citations: list[dict[str, Any]] = []
        if chunks and ans_text:
            cited_indices = set(re.findall(r"\[(\d+)\]", ans_text))
            for idx_str in sorted(cited_indices, key=int):
                i = int(idx_str) - 1
                if 0 <= i < len(chunks):
                    c = chunks[i]
                    citations.append({
                        "chunk_id": str(c.chunk_id),
                        "document_id": getattr(c, "document_id", ""),
                        "title": getattr(c, "title", ""),
                        "page": getattr(c, "page", None),
                        "heading_path": list(getattr(c, "heading_path", ())),
                    })

        return {
            "generate_count": count,
            "answer": ans_text,
            "citations": citations,
            "model_used": used_model_name,
        }

    return generate
