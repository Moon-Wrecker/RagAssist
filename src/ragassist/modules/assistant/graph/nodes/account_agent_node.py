"""Account agent node executing SaaS tools with human-in-the-loop write approval.

Design and proven patterns consulted:
- LangGraph Human-in-the-Loop Approval Pattern (interrupt / Command(resume=...)):
  https://langchain-ai.github.io/langgraph/how-tos/human-in-the-loop/
- Replay Safety:
  When LangGraph resumes a node containing interrupt(), it re-executes the node from the top.
  To prevent re-invoking the model and desynchronizing scripted/mock chat models or LLM cursors,
  we preserve the pending model message across the interrupt boundary.
"""

from __future__ import annotations

from typing import Any
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from ragassist.modules.assistant.graph.state import AssistantState

_PENDING_TOOL_CALLS: dict[str, Any] = {}


def make_account_agent_node(generator_tiers: dict[str, Any], tools: Any):  # type: ignore[no-untyped-def]
    async def account_agent(state: AssistantState) -> dict[str, Any]:
        complexity = float(state.get("complexity", 2.0))
        tier = "cheap" if complexity < 2.0 else "strong"
        model_entry = generator_tiers.get(tier) or generator_tiers.get("strong") or generator_tiers.get("cheap")
        model = model_entry[0] if isinstance(model_entry, list) else model_entry

        principal = state["principal"]
        question = state.get("question", "")
        tool_records: list[dict[str, Any]] = list(state.get("tool_calls", []))
        messages = [HumanMessage(content=question)]

        thread_key = f"{principal.tenant_id}:{state.get('conversation_id', '')}"
        if thread_key in _PENDING_TOOL_CALLS:
            ai_msg = _PENDING_TOOL_CALLS.pop(thread_key)
        else:
            ai_msg = await model.ainvoke(messages)
            if getattr(ai_msg, "tool_calls", None):
                _PENDING_TOOL_CALLS[thread_key] = ai_msg

        tool_calls_req = getattr(ai_msg, "tool_calls", [])

        if tool_calls_req:
            req = tool_calls_req[0]
            tool_name = req["name"]
            tool_args = req["args"]
            call_id = req.get("id", "call_1")

            # Check if tool is recognized by the registry
            known_tools = getattr(tools, "_tools", None)
            if known_tools is not None and tool_name not in known_tools:
                _PENDING_TOOL_CALLS.pop(thread_key, None)
                tool_msg = ToolMessage(
                    tool_call_id=call_id,
                    content=f"Error: Unknown tool '{tool_name}'.",
                )
                ai_final = await model.ainvoke([*messages, ai_msg, tool_msg])
                ans_text = str(ai_final.content)
                return {
                    "answer": ans_text,
                    "tool_calls": tool_records,
                }

            try:
                is_write = tools.is_write(tool_name)
            except Exception:
                is_write = False

            if is_write:
                # Pause and interrupt for human approval
                resume_payload = interrupt({
                    "action": "approval_required",
                    "tool": tool_name,
                    "arguments": tool_args,
                })

                # Clear pending cache since interrupt resumed
                _PENDING_TOOL_CALLS.pop(thread_key, None)

                decision = (
                    resume_payload.get("decision")
                    if isinstance(resume_payload, dict)
                    else resume_payload
                )

                if decision == "approve":
                    res = await tools.invoke(tool_name, tool_args, principal)
                    tool_records.append({
                        "name": tool_name,
                        "arguments": tool_args,
                        "result": res,
                        "approved": True,
                    })
                    tool_msg = ToolMessage(tool_call_id=call_id, content=str(res))
                    ai_final = await model.ainvoke([*messages, ai_msg, tool_msg])
                    ans_text = str(ai_final.content)
                else:
                    tool_records.append({
                        "name": tool_name,
                        "arguments": tool_args,
                        "approved": False,
                    })
                    tool_msg = ToolMessage(
                        tool_call_id=call_id,
                        content="User denied permission to execute this write action.",
                    )
                    ai_final = await model.ainvoke([*messages, ai_msg, tool_msg])
                    ans_text = str(ai_final.content)
            else:
                _PENDING_TOOL_CALLS.pop(thread_key, None)
                # Read tool executes immediately
                res = await tools.invoke(tool_name, tool_args, principal)
                tool_records.append({
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": res,
                })
                tool_msg = ToolMessage(tool_call_id=call_id, content=str(res))
                ai_final = await model.ainvoke([*messages, ai_msg, tool_msg])
                ans_text = str(ai_final.content)
        else:
            _PENDING_TOOL_CALLS.pop(thread_key, None)
            ans_text = str(ai_msg.content)

        used_name = getattr(
            model, "label", getattr(model, "model_name", getattr(model, "_llm_type", "model"))
        )

        return {
            "answer": ans_text,
            "tool_calls": tool_records,
            "model_used": used_name,
        }

    return account_agent
