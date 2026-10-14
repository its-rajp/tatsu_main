"""Agent State Schema for TATSU Sovereign Agent."""

from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Core state object maintained across LangGraph execution cycles."""

    messages: Annotated[List[BaseMessage], add_messages]
    current_task: str
    tool_calls: List[Dict[str, Any]]
    observations: List[str]
    persona_config: Dict[str, Any]
    screen_context: Optional[Dict[str, Any]]
    system_health: Optional[Dict[str, Any]]
    memory_context: Optional[Dict[str, Any]]
    current_plan_steps: Optional[List[Dict[str, Any]]]
    final_response: Optional[str]
    error: Optional[str]
    turn_count: int
