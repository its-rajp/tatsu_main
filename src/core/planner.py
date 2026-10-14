"""Agentic Multi-Step Planner for TATSU Sovereign Agent — Phase 3.

Breaks down high-level user commands into sequential execution plans,
coordinates tool invocations step-by-step, verifies intermediate outcomes,
and handles dynamic self-correction.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from src.tools.registry import AVAILABLE_TOOLS, audit_log

logger = logging.getLogger("TATSU.Planner")


class PlanStep(BaseModel):
    """Represents a single atomic action within an execution plan."""
    step_id: int
    description: str
    tool: str
    args: Dict[str, Any]
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    result: Optional[str] = None


class ExecutionPlan(BaseModel):
    """Structured sequence of steps formulating an agentic workflow."""
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    current_index: int = 0
    is_complete: bool = False
    error: Optional[str] = None


class AgenticPlanner:
    """Deconstructs high-level goals into step sequences and drives their execution."""

    def __init__(self, tools_dict: Optional[Dict[str, Any]] = None):
        self.tools = tools_dict or AVAILABLE_TOOLS

    def decompose_goal(self, goal: str) -> ExecutionPlan:
        """Heuristically or structurally creates an execution plan for a compound goal.
        
        Handles compound operations like:
        - "organize files and archive them"
        - "search for PDFs, move them, and zip them"
        - "check system stats and run python test"
        """
        plan = ExecutionPlan(goal=goal)
        goal_lower = goal.lower()

        # Pattern 1: Search and Archive
        if ("search" in goal_lower or "find" in goal_lower) and ("archive" in goal_lower or "zip" in goal_lower):
            ext_match = re.search(r"\b(\.[a-zA-Z0-9]+|\*\.[a-zA-Z0-9]+|pdf|py|txt|png|jpg)\b", goal_lower)
            ext = ext_match.group(1) if ext_match else "*.pdf"
            if not ext.startswith("*"):
                ext = f"*{ext}" if ext.startswith(".") else f"*.{ext}"

            plan.steps = [
                PlanStep(
                    step_id=1,
                    description=f"Search for files matching '{ext}' in workspace",
                    tool="file_search",
                    args={"pattern": ext, "directory": "."},
                ),
                PlanStep(
                    step_id=2,
                    description="Archive discovered files into a zip container",
                    tool="file_archive",
                    args={"file_list": [], "destination_zip": "logs/archived_results.zip", "confirm": True},
                ),
            ]

        # Pattern 2: Organize directory
        elif "organize" in goal_lower or "clean up" in goal_lower or "cleanup" in goal_lower:
            plan.steps = [
                PlanStep(
                    step_id=1,
                    description="Organize loose directory files into categories",
                    tool="file_organize",
                    args={"directory": ".", "confirm": True},
                ),
                PlanStep(
                    step_id=2,
                    description="Verify organized structure",
                    tool="file_search",
                    args={"pattern": "*", "directory": "."},
                ),
            ]

        # Pattern 3: Python execution & verify
        elif "run python" in goal_lower or "execute script" in goal_lower:
            code_match = re.search(r"```python\n(.*?)\n```", goal, re.DOTALL)
            code = code_match.group(1) if code_match else "print('TATSU plan execution verified.')"
            plan.steps = [
                PlanStep(
                    step_id=1,
                    description="Execute Python code in isolated sandbox",
                    tool="run_python_script",
                    args={"code": code},
                ),
            ]

        # Default single-step fallback
        else:
            plan.steps = [
                PlanStep(
                    step_id=1,
                    description=f"Execute task: {goal}",
                    tool="system_info" if "system" in goal_lower else "shell_exec",
                    args={"detailed": True} if "system" in goal_lower else {"command": f"echo '{goal}'"},
                ),
            ]

        return plan

    def execute_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """Executes plan steps sequentially, passing intermediate context if applicable."""
        intermediate_results = []
        last_discovered_files = []

        audit_log("PLAN_START", {"goal": plan.goal, "total_steps": len(plan.steps)})

        for i, step in enumerate(plan.steps):
            plan.current_index = i
            step.status = "RUNNING"

            # Dynamic parameter chaining: if step requires file_list and previous search found files
            if step.tool == "file_archive" and not step.args.get("file_list") and last_discovered_files:
                step.args["file_list"] = last_discovered_files

            tool = self.tools.get(step.tool)
            if not tool:
                step.status = "FAILED"
                step.result = f"Error: Tool '{step.tool}' not found in registry."
                plan.error = step.result
                audit_log("PLAN_STEP_FAILED", {"step": step.step_id, "error": step.result})
                break

            try:
                output = tool.execute(step.args)
                step.status = "COMPLETED"
                step.result = output
                intermediate_results.append(f"Step {step.step_id} ({step.tool}): {output}")

                # If output was a file_search result, parse out file paths
                if step.tool == "file_search":
                    # Extract paths from JSON or string output
                    try:
                        import json
                        parsed = json.loads(output)
                        if isinstance(parsed, list):
                            last_discovered_files = [f.get("path") for f in parsed if f.get("path")]
                    except Exception:
                        pass

                audit_log("PLAN_STEP_COMPLETE", {"step": step.step_id, "tool": step.tool})

            except Exception as e:
                step.status = "FAILED"
                step.result = f"Exception: {str(e)}"
                plan.error = step.result
                audit_log("PLAN_STEP_ERROR", {"step": step.step_id, "error": str(e)})
                break

        plan.is_complete = all(s.status == "COMPLETED" for s in plan.steps)
        summary = "\n".join(intermediate_results)
        if plan.is_complete:
            final_report = f"Plan completed successfully ({len(plan.steps)} steps executed):\n{summary}"
        else:
            final_report = f"Plan stopped at step {plan.current_index + 1}: {plan.error}\nProgress so far:\n{summary}"

        audit_log("PLAN_FINISH", {"goal": plan.goal, "completed": plan.is_complete})
        return {
            "is_complete": plan.is_complete,
            "final_report": final_report,
            "steps": [s.model_dump() for s in plan.steps],
        }
