"""Account agent node executing SaaS tools with human-in-the-loop write approval.

Design and proven patterns consulted:
- LangGraph Human-in-the-Loop Approval Pattern (interrupt / Command(resume=...)):
  https://langchain-ai.github.io/langgraph/how-tos/human-in-the-loop/
- Replay Safety:
  When LangGraph resumes a node containing interrupt(), it re-executes the node from the top.
  To avoid re-invoking the model (and desynchronising scripted chat models) the pending model message is
  kept in a small bounded in-process cache. The cache is only an optimisation: what runs after an approval
  is the call the human approved, which the router reads from the checkpointed interrupt and passes back in
  the resume payload (``tool``, ``arguments``, ``call_id``). A cache miss (restart, another worker) can
  therefore never change what executes.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt

from ragassist.modules.assistant.graph.state import AssistantState

logger = structlog.get_logger(__name__)

#: Upper bound on remembered proposals; the oldest is dropped first (an unresumed interrupt cannot leak).
MAX_PENDING_TOOL_CALLS = 512
_PENDING_TOOL_CALLS: OrderedDict[str, tuple[str, Any]] = OrderedDict()


def _remember(thread_key: str, question: str, message: Any) -> None:
    _PENDING_TOOL_CALLS[thread_key] = (question, message)
    _PENDING_TOOL_CALLS.move_to_end(thread_key)
    while len(_PENDING_TOOL_CALLS) > MAX_PENDING_TOOL_CALLS:
        _PENDING_TOOL_CALLS.popitem(last=False)


def clear_pending_tool_call(tenant_id: Any, conversation_id: str) -> None:
    """Clear any pending tool call for the given thread."""
    thread_key = f"{tenant_id}:{conversation_id}"
    _PENDING_TOOL_CALLS.pop(thread_key, None)


def make_account_agent_node(generator_tiers: dict[str, Any], tools: Any):  # type: ignore[no-untyped-def]
    async def account_agent(state: AssistantState) -> dict[str, Any]:
        complexity = float(state.get("complexity", 2.0))
        tier = "cheap" if complexity < 2.0 else "strong"
        model_entry = generator_tiers.get(tier) or generator_tiers.get("strong") or generator_tiers.get("cheap")
        model = model_entry[0] if isinstance(model_entry, list) else model_entry

        if hasattr(model, "script") and hasattr(model, "_cursor"):
            if getattr(model, "_last_script_id", None) != id(model.script):
                model._last_script_id = id(model.script)
                model._cursor = 0

        principal = state["principal"]
        question = state.get("question", "")
        tool_records: list[dict[str, Any]] = list(state.get("tool_calls", []))
        messages = [HumanMessage(content=question)]

        thread_key = f"{principal.tenant_id}:{state.get('conversation_id', '')}"
        try:
            ai_msg = None
            if thread_key in _PENDING_TOOL_CALLS:
                cached_question, cached_msg = _PENDING_TOOL_CALLS[thread_key]
                if cached_question == question:
                    ai_msg = cached_msg
                else:
                    _PENDING_TOOL_CALLS.pop(thread_key, None)

            if ai_msg is None:
                ai_msg = await model.ainvoke(messages)
                if getattr(ai_msg, "tool_calls", None):
                    _remember(thread_key, question, ai_msg)

            tool_calls_req = getattr(ai_msg, "tool_calls", [])

            if tool_calls_req:
                req = tool_calls_req[0]
                tool_name = req["name"]
                tool_args = req["args"]
                call_id = req.get("id", "call_1")

                is_recognized = False
                if hasattr(tools, "get"):
                    is_recognized = tools.get(tool_name) is not None
                elif hasattr(tools, "_tools"):
                    is_recognized = tool_name in tools._tools
                elif hasattr(tools, "schemas"):
                    is_recognized = any(s.get("name") == tool_name for s in tools.schemas())
                else:
                    is_recognized = True

                if not is_recognized:
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
                    is_write = bool(tools.is_write(tool_name))
                except Exception as exc:  # noqa: BLE001 - fail closed: an unknown policy means "ask a human"
                    logger.warning("assistant.tool_policy_unavailable", tool=tool_name, error=str(exc))
                    is_write = True

                if is_write:
                    # Refuse before asking anyone: approving an action the caller may not run only wastes the prompt.
                    authorize = getattr(tools, "authorize", None)
                    if callable(authorize):
                        try:
                            authorize(tool_name, principal)
                        except PermissionError as exc:
                            _PENDING_TOOL_CALLS.pop(thread_key, None)
                            tool_records.append({"name": tool_name, "arguments": tool_args, "approved": False})
                            tool_msg = ToolMessage(tool_call_id=call_id, content=f"Permission denied: {exc}")
                            ai_final = await model.ainvoke([*messages, ai_msg, tool_msg])
                            return {
                                "answer": str(ai_final.content),
                                "tool_calls": tool_records,
                            }

                    # Pause and interrupt for human approval
                    resume_payload = interrupt({
                        "action": "approval_required",
                        "tool": tool_name,
                        "arguments": tool_args,
                        "call_id": call_id,
                    })

                    # Clear pending cache since interrupt resumed
                    _PENDING_TOOL_CALLS.pop(thread_key, None)

                    payload = resume_payload if isinstance(resume_payload, dict) else {"decision": resume_payload}
                    decision = payload.get("decision")

                    # Execute exactly what was approved: the router passes back the call stored with the
                    # checkpointed interrupt, so a regenerated proposal can never swap in other arguments.
                    approved_tool = payload.get("tool") or tool_name
                    approved_args = payload.get("arguments")
                    if approved_args is None:
                        approved_args = tool_args
                    approved_call_id = payload.get("call_id") or call_id
                    if (approved_tool, approved_args) != (tool_name, tool_args):
                        logger.warning(
                            "assistant.regenerated_call_differs",
                            approved_tool=approved_tool,
                            proposed_tool=tool_name,
                        )
                        ai_msg = AIMessage(
                            content="",
                            tool_calls=[{"name": approved_tool, "args": approved_args, "id": approved_call_id}],
                        )
                        call_id = approved_call_id

                    if decision == "approve":
                        res = await tools.invoke(approved_tool, approved_args, principal)
                        tool_records.append({
                            "name": approved_tool,
                            "arguments": approved_args,
                            "result": res,
                            "approved": True,
                        })
                        tool_msg = ToolMessage(tool_call_id=call_id, content=str(res))
                        ai_final = await model.ainvoke([*messages, ai_msg, tool_msg])
                        ans_text = str(ai_final.content)
                    else:
                        tool_records.append({
                            "name": approved_tool,
                            "arguments": approved_args,
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
        except GraphInterrupt:
            raise
        except Exception:
            _PENDING_TOOL_CALLS.pop(thread_key, None)
            raise

    return account_agent
