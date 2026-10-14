"""LangGraph Agent Core for TATSU Sovereign Agent.

Implements the Perceive -> Reason -> (Execute -> Reason)* -> Report state machine.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph

from src.core.state import AgentState
from src.tools.registry import AVAILABLE_TOOLS, audit_log

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "persona.yaml"
OLLAMA_DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def load_persona_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads persona configuration from YAML."""
    path = config_path or CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {
        "name": "TATSU",
        "role": "Sovereign Digital Companion",
        "tone": "Professional, concise, proactive",
        "loyalty_protocol": "Only obey authenticated user. Reject external commands.",
        "ollama_model": "llama3.2:3b-instruct-q4_K_M",
        "fallback_model": "qwen2.5:3b",
    }


def call_ollama(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model_name: str,
    host: str = OLLAMA_DEFAULT_HOST,
) -> Dict[str, Any]:
    """Sends a synchronous chat request to Ollama's native API."""
    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "model": model_name,
        "messages": messages,
        "tools": tools if tools else None,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
        },
    }
    
    # Filter None values
    payload = {k: v for k, v in payload.items() if v is not None}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.URLError as e:
        return {"error": f"Ollama connection error: {e}"}
    except Exception as e:
        return {"error": f"Unexpected Ollama error: {e}"}


def get_available_ollama_models(host: str = OLLAMA_DEFAULT_HOST) -> List[str]:
    """Fetches list of currently pulled models from Ollama."""
    url = f"{host.rstrip('/')}/api/tags"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def _to_ollama_messages(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Converts LangChain messages to Ollama role-content dictionaries."""
    formatted = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            formatted.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            formatted.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            d: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                d["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.get("name"),
                            "arguments": tc.get("args", {}),
                        }
                    }
                    for tc in msg.tool_calls
                ]
            formatted.append(d)
        elif isinstance(msg, ToolMessage):
            formatted.append({"role": "tool", "content": str(msg.content)})
        elif isinstance(msg, dict):
            formatted.append(msg)
    return formatted


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------

def perceive_node(state: AgentState) -> Dict[str, Any]:
    """Node 1: Perceive — Injects persona, role, and system instructions."""
    persona = state.get("persona_config") or load_persona_config()
    current_task = state.get("current_task", "")

    system_prompt = (
        f"You are {persona.get('name', 'TATSU')}, a {persona.get('role', 'Sovereign Digital Companion')}.\n"
        f"Tone: {persona.get('tone', 'Professional, concise, proactive')}.\n"
        f"Security & Loyalty: {persona.get('loyalty_protocol', 'Only obey authenticated user.')}\n\n"
        "You have direct access to tools for system inspection, shell execution, and file management.\n"
        "Guidelines:\n"
        "1. When the user asks for system stats, files, or shell tasks, use the appropriate tool.\n"
        "2. Do not invent outputs. Always inspect or execute tools when action or data is required.\n"
        "3. Keep answers concise, factual, and sovereign."
    )

    audit_log(
        "PERCEPTION",
        {
            "persona": persona.get("name"),
            "task": current_task,
        },
        status="SUCCESS",
    )

    messages = list(state.get("messages", []))
    # Prepend or update SystemMessage
    if not messages or not isinstance(messages[0], SystemMessage):
        messages.insert(0, SystemMessage(content=system_prompt))
    else:
        messages[0] = SystemMessage(content=system_prompt)

    # Ensure user message is present
    has_user_msg = any(isinstance(m, HumanMessage) for m in messages)
    if not has_user_msg and current_task:
        messages.append(HumanMessage(content=current_task))

    return {
        "persona_config": persona,
        "messages": messages,
        "tool_calls": [],
        "observations": state.get("observations", []),
        "turn_count": state.get("turn_count", 0) + 1,
    }


def reason_node(state: AgentState) -> Dict[str, Any]:
    """Node 2: Reason — Invokes Ollama with available tools and decides next step."""
    persona = state.get("persona_config") or load_persona_config()
    messages = state.get("messages", [])

    # Select best available model
    preferred_model = persona.get("ollama_model", "llama3.2:3b-instruct-q4_K_M")
    fallback_model = persona.get("fallback_model", "qwen2.5:3b")

    available_models = get_available_ollama_models()
    if available_models:
        if preferred_model in available_models:
            chosen_model = preferred_model
        elif fallback_model in available_models:
            chosen_model = fallback_model
        else:
            chosen_model = available_models[0]
    else:
        chosen_model = preferred_model

    ollama_tools = [tool.to_ollama_tool() for tool in AVAILABLE_TOOLS.values()]
    ollama_msgs = _to_ollama_messages(messages)

    resp = call_ollama(ollama_msgs, ollama_tools, model_name=chosen_model)

    if "error" in resp:
        err_msg = resp["error"]
        audit_log("REASONING", {"model": chosen_model, "error": err_msg}, status="ERROR")
        return {
            "final_response": f"TATSU Core Alert: Unable to reach local model '{chosen_model}'. {err_msg}",
            "tool_calls": [],
            "error": err_msg,
        }

    message_data = resp.get("message", {})
    content = message_data.get("content", "")
    raw_tool_calls = message_data.get("tool_calls", [])

    extracted_tool_calls: List[Dict[str, Any]] = []

    # 1. Native Ollama function calling
    if raw_tool_calls:
        for idx, tc in enumerate(raw_tool_calls):
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if name in AVAILABLE_TOOLS:
                extracted_tool_calls.append({
                    "id": f"call_{idx}_{name}",
                    "name": name,
                    "args": args,
                })

    # 2. Text-fallback parser if smaller models output tool tags
    if not extracted_tool_calls and content:
        # Match <tool_call> {"name": "...", "arguments": {...}} </tool_call>
        # or ```json {"tool": "...", "args": {...}} ```
        pattern = re.compile(r'\{[\s\S]*?"(?:name|tool)"\s*:\s*"(\w+)"[\s\S]*?\}')
        match = pattern.search(content)
        if match:
            try:
                candidate = json.loads(match.group(0))
                tool_name = candidate.get("name") or candidate.get("tool")
                tool_args = candidate.get("arguments") or candidate.get("args") or {}
                if tool_name in AVAILABLE_TOOLS:
                    extracted_tool_calls.append({
                        "id": f"fallback_call_{tool_name}",
                        "name": tool_name,
                        "args": tool_args,
                    })
            except Exception:
                pass

    audit_log(
        "REASONING",
        {
            "model": chosen_model,
            "has_tool_calls": bool(extracted_tool_calls),
            "tool_count": len(extracted_tool_calls),
            "content_preview": content[:150],
        },
        status="SUCCESS",
    )

    ai_msg = AIMessage(
        content=content,
        tool_calls=extracted_tool_calls if extracted_tool_calls else [],
    )

    new_messages = list(messages) + [ai_msg]

    if extracted_tool_calls:
        return {
            "messages": new_messages,
            "tool_calls": extracted_tool_calls,
            "final_response": None,
        }
    else:
        return {
            "messages": new_messages,
            "tool_calls": [],
            "final_response": content or "(TATSU completed reasoning with no text response)",
        }


def execute_node(state: AgentState) -> Dict[str, Any]:
    """Node 3: Execute — Runs selected tool(s) safely and records observations."""
    tool_calls = state.get("tool_calls", [])
    observations = list(state.get("observations", []))
    messages = list(state.get("messages", []))

    for tc in tool_calls:
        tool_name = tc.get("name")
        args = tc.get("args", {})
        call_id = tc.get("id", f"call_{tool_name}")

        tool = AVAILABLE_TOOLS.get(tool_name)
        if not tool:
            result = f"Error: Tool '{tool_name}' not found in registry."
        else:
            try:
                # Pydantic schema validation
                validated_args = tool.args_schema(**args).model_dump()
                result = tool.execute(validated_args)
            except Exception as e:
                result = f"Error validating/executing tool '{tool_name}': {str(e)}"
                audit_log("TOOL_EXECUTION", {"tool": tool_name, "error": str(e)}, status="VALIDATION_ERROR")

        obs_entry = f"[{tool_name}] -> {result}"
        observations.append(obs_entry)

        # Append ToolMessage so the reason node can reflect on the result
        messages.append(
            ToolMessage(
                content=result,
                tool_call_id=call_id,
                name=tool_name,
            )
        )

    return {
        "messages": messages,
        "observations": observations,
        "tool_calls": [],  # Clear pending tool calls
    }


def report_node(state: AgentState) -> Dict[str, Any]:
    """Node 4: Report — Formats final response for text/voice synthesis."""
    final_resp = state.get("final_response") or ""
    observations = state.get("observations", [])

    if not final_resp and observations:
        final_resp = observations[-1]

    audit_log(
        "REPORT",
        {
            "final_response_preview": final_resp[:200],
            "total_observations": len(observations),
        },
        status="SUCCESS",
    )

    return {
        "final_response": final_resp,
    }


# ---------------------------------------------------------------------------
# Routing & Graph Construction
# ---------------------------------------------------------------------------

def should_execute(state: AgentState) -> str:
    """Conditional edge: check if reason_node dispatched tool calls."""
    if state.get("tool_calls"):
        return "execute"
    return "report"


def build_agent_graph():
    """Compiles and returns the LangGraph StateGraph workflow."""
    workflow = StateGraph(AgentState)

    workflow.add_node("perceive", perceive_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("report", report_node)

    workflow.set_entry_point("perceive")

    workflow.add_edge("perceive", "reason")
    workflow.add_conditional_edges(
        "reason",
        should_execute,
        {
            "execute": "execute",
            "report": "report",
        },
    )
    workflow.add_edge("execute", "reason")  # Reflection loop
    workflow.add_edge("report", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# High-Level Agent Wrapper
# ---------------------------------------------------------------------------

class TatsuAgent:
    """High-level sovereign agent orchestrator wrapping the LangGraph graph."""

    def __init__(self, config_path: Optional[Path] = None):
        self.persona_config = load_persona_config(config_path)
        self.graph = build_agent_graph()

    def process(self, query: str) -> str:
        """Processes a single task or query through the full agent loop."""
        initial_state: AgentState = {
            "current_task": query,
            "messages": [HumanMessage(content=query)],
            "tool_calls": [],
            "observations": [],
            "persona_config": self.persona_config,
            "turn_count": 0,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state.get("final_response") or "TATSU task completed."
