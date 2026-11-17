"""
Multi-Step Agent Orchestrator for EdgeMind.

Implements the iterative reasoning & tool execution loop:
1. Maintains full conversational context (system instructions, user prompt, assistant thoughts, tool outputs).
2. Enforces iteration and tool invocation limits (max_iterations, max_tool_calls).
3. Safely executes registered tools with per-tool timeouts and strict argument validation.
4. Handles error recovery: model receives informative error messages and can self-correct.
5. Guarantees zero code execution (only static AST analysis and candidate synthesis).
6. Persists final analysis reports into PostgreSQL JSONB store when session & user are present.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.provider import BaseAgentProvider, LiveAgentProvider
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentMessage,
    AgentState,
    AgentStatus,
    ToolCall,
    ToolExecutionRecord,
    ToolExecutionStatus,
)
from core.agents.tools import ToolRegistry, default_tool_registry
from core.config import get_settings
from core.database.models import User
from core.reports.builder import build_analysis_report_doc
from core.service import analyze_code

logger = logging.getLogger("edgemind.agents.orchestrator")


class AgentOrchestrator:
    """
    Coordinates multi-step agent execution, tool dispatching, and state management.
    """

    def __init__(
        self,
        provider: Optional[BaseAgentProvider] = None,
        registry: Optional[ToolRegistry] = None,
        max_iterations: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        session_timeout: Optional[float] = None,
    ):
        settings = get_settings()
        self.provider = provider or LiveAgentProvider()
        self.registry = registry or default_tool_registry
        self.max_iterations = max_iterations or settings.agent_max_iterations
        self.max_tool_calls = max_tool_calls or settings.agent_max_tool_calls
        self.session_timeout = session_timeout or settings.agent_session_timeout

    def _build_system_prompt(self) -> str:
        return (
            "You are the EdgeMind Autonomous Test Intelligence Agent. "
            "Your objective is to inspect Python code, detect missing edge-case test coverage, "
            "and synthesize ranked candidate test inputs using specialized static analysis tools.\n\n"
            "You have access to 7 specialized tools:\n"
            "1. parse_problem_constraints: Parse mathematical & natural language constraints into bounds.\n"
            "2. analyze_problem_structure: AST inspection of code signatures, types, and static metrics.\n"
            "3. detect_coverage_gaps: Find boundary and partition gaps in baseline test cases.\n"
            "4. retrieve_existing_analysis: Fetch historical analysis reports from persistent storage.\n"
            "5. generate_candidate_inputs: Synthesize targeted edge-case inputs addressing gaps.\n"
            "6. validate_candidate_inputs: Classify candidates against constraints (VALID/PROBE/UNKNOWN).\n"
            "7. rank_candidate_inputs: Score, deduplicate, and select highest-value candidates.\n\n"
            "OPERATING GUIDELINES:\n"
            "- Plan step-by-step. Call tools when you need to inspect or compute domain facts.\n"
            "- Zero runtime execution: all analysis is strictly static.\n"
            "- If a tool returns an error, adjust your parameters and retry.\n"
            "- When you have gathered sufficient evidence, synthesize a clear final answer with a summary."
        )

    def _build_user_prompt(self, request: AgentAnalyzeRequest) -> str:
        prompt_parts = [
            f"Please analyze the following Python code for file '{request.filename}':\n",
            "```python",
            request.code,
            "```\n",
        ]

        if request.problem_context:
            prompt_parts.append(f"Problem Context: {json.dumps(request.problem_context, indent=2)}\n")

        if request.test_cases:
            prompt_parts.append(f"Baseline Test Cases: {json.dumps(request.test_cases, indent=2)}\n")

        prompt_parts.append(
            f"Goal: Identify potential coverage gaps, validate domain constraints, and generate up to "
            f"{request.max_candidates or 10} ranked candidate edge-case inputs."
        )

        return "\n".join(prompt_parts)

    async def run(
        self,
        request: AgentAnalyzeRequest,
        db: Optional[AsyncSession] = None,
        current_user: Optional[User] = None,
        cancellation_token: Optional[asyncio.Event] = None,
    ) -> AgentAnalyzeResponse:
        """
        Execute the iterative reasoning and tool execution loop.
        """
        start_time = time.perf_counter()
        session_id = uuid.uuid4()
        effective_max_iterations = min(request.max_iterations or self.max_iterations, 10)

        # Context accessible to tool handlers (e.g. database session)
        tool_context = {
            "db": db,
            "current_user": current_user,
            "session_id": session_id,
            "project_id": str(request.project_id) if request.project_id else None,
            "problem_id": str(request.problem_id) if request.problem_id else None,
        }

        # Initialize conversation state
        state = AgentState(
            session_id=session_id,
            max_iterations=effective_max_iterations,
            max_tool_calls=self.max_tool_calls,
            messages=[
                AgentMessage(role="system", content=self._build_system_prompt()),
                AgentMessage(role="user", content=self._build_user_prompt(request)),
            ],
            status=AgentStatus.SUCCESS,
        )

        # Multi-Step Reasoning Loop
        while state.iteration < state.max_iterations:
            # Check cancellation token
            if cancellation_token and cancellation_token.is_set():
                state.status = AgentStatus.CANCELLED
                state.final_summary = "Agent execution cancelled by user request."
                break

            # Check wall-clock timeout
            elapsed = time.perf_counter() - start_time
            if elapsed > self.session_timeout:
                state.status = AgentStatus.PARTIAL
                state.final_summary = (
                    f"Agent session timeout reached ({self.session_timeout}s). Partial results returned."
                )
                break

            # Convert messages for provider
            raw_messages = [
                m.model_dump(exclude_none=True) for m in state.messages
            ]

            # Request step from LLM provider
            try:
                step_result = await self.provider.chat_completion(
                    messages=raw_messages,
                    tools=self.registry.get_schemas(),
                )
            except Exception as exc:
                logger.error(f"Provider chat_completion failed: {exc}")
                state.status = AgentStatus.FAILED
                state.final_summary = f"Reasoning provider failed: {exc}"
                break

            state.iteration += 1

            # Case A: Provider requests one or more tool calls
            if step_result.tool_calls:
                # Append assistant message with requested tool calls
                asst_msg = AgentMessage(
                    role="assistant",
                    content=step_result.content or step_result.thought or "",
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.get_arguments_dict())
                                if isinstance(tc.arguments, dict)
                                else str(tc.arguments),
                            },
                        }
                        for tc in step_result.tool_calls
                    ],
                )
                state.messages.append(asst_msg)

                for tc in step_result.tool_calls:
                    # Enforce max tool calls bound
                    if state.tool_call_count >= state.max_tool_calls:
                        err_msg = f"Maximum allowed tool executions ({state.max_tool_calls}) exceeded."
                        state.tool_executions.append(
                            ToolExecutionRecord(
                                tool_call_id=tc.id,
                                tool_name=tc.name,
                                arguments=tc.get_arguments_dict(),
                                status=ToolExecutionStatus.ERROR,
                                error=err_msg,
                            )
                        )
                        state.messages.append(
                            AgentMessage(
                                role="tool",
                                tool_call_id=tc.id,
                                name=tc.name,
                                content=json.dumps({"error": err_msg}),
                            )
                        )
                        continue

                    state.tool_call_count += 1
                    t0 = time.perf_counter()
                    record_status = ToolExecutionStatus.SUCCESS
                    tool_output: Optional[Dict[str, Any]] = None
                    tool_error: Optional[str] = None

                    try:
                        tool_output = await self.registry.execute_tool(
                            name=tc.name,
                            arguments=tc.get_arguments_dict(),
                            context=tool_context,
                        )
                    except KeyError as exc:
                        record_status = ToolExecutionStatus.ERROR
                        tool_error = str(exc)
                        tool_output = {"error": tool_error}
                    except ValueError as exc:
                        record_status = ToolExecutionStatus.ERROR
                        tool_error = str(exc)
                        tool_output = {"error": tool_error}
                    except TimeoutError as exc:
                        record_status = ToolExecutionStatus.TIMEOUT
                        tool_error = str(exc)
                        tool_output = {"error": tool_error}
                    except Exception as exc:
                        record_status = ToolExecutionStatus.ERROR
                        tool_error = f"Unexpected tool execution failure: {exc}"
                        tool_output = {"error": tool_error}

                    duration_ms = (time.perf_counter() - t0) * 1000.0

                    # Save tool execution record in audit history
                    state.tool_executions.append(
                        ToolExecutionRecord(
                            tool_call_id=tc.id,
                            tool_name=tc.name,
                            arguments=tc.get_arguments_dict(),
                            status=record_status,
                            duration_ms=round(duration_ms, 2),
                            result=tool_output if record_status == ToolExecutionStatus.SUCCESS else None,
                            error=tool_error,
                        )
                    )

                    # Append tool response message into conversation context
                    state.messages.append(
                        AgentMessage(
                            role="tool",
                            tool_call_id=tc.id,
                            name=tc.name,
                            content=json.dumps(tool_output),
                        )
                    )

                    # Accumulate tool results in context for response synthesis
                    if record_status == ToolExecutionStatus.SUCCESS and tool_output:
                        if tc.name == "analyze_problem_structure":
                            state.accumulated_context["structure"] = tool_output
                        elif tc.name == "parse_problem_constraints":
                            state.accumulated_context["constraints"] = tool_output
                        elif tc.name == "detect_coverage_gaps":
                            state.accumulated_context["gaps"] = tool_output.get("gaps", [])
                        elif tc.name == "generate_candidate_inputs":
                            state.accumulated_context["candidates"] = tool_output.get("candidates", [])
                        elif tc.name == "rank_candidate_inputs":
                            state.accumulated_context["selected_candidates"] = tool_output.get("selected_candidates", [])
                            state.accumulated_context["ranked_candidates"] = tool_output.get("ranked_candidates", [])
                            state.accumulated_context["ranking_summary"] = tool_output.get("ranking_summary", {})
                        elif tc.name == "validate_candidate_inputs":
                            state.accumulated_context["validations"] = tool_output.get("classifications", [])

            # Case B: Provider returns final text (no tool calls)
            else:
                state.final_summary = step_result.content or "Agent completed reasoning without additional notes."
                state.status = AgentStatus.SUCCESS
                break

        # Check if iteration limit was reached without final answer
        if state.final_summary is None:
            state.status = AgentStatus.MAX_ITERATIONS_REACHED
            state.final_summary = (
                f"Agent reached maximum reasoning cycles ({state.max_iterations}). "
                "Synthesized partial recommendations from executed tool outputs."
            )

        # Baseline static analysis fallback if not already executed
        static_analysis = state.accumulated_context.get("structure")
        if not static_analysis:
            code_report = analyze_code(
                request.code,
                filename=request.filename or "solution.py",
                static_only=True,
            )
            static_analysis = {
                "static_metrics": code_report.get("metrics", {}),
                "findings_count": len(code_report.get("results", [])),
                "code_report": code_report,
            }

        # Assemble test intelligence section
        candidates = (
            state.accumulated_context.get("selected_candidates")
            or state.accumulated_context.get("candidates")
            or []
        )
        ranked = state.accumulated_context.get("ranked_candidates") or []
        gaps = state.accumulated_context.get("gaps") or []
        ranking_summary = state.accumulated_context.get("ranking_summary") or {
            "total_evaluated": len(candidates),
            "selection_limit": request.max_candidates or 10,
        }

        test_intelligence = {
            "existing_tests_analyzed": len(request.test_cases) if request.test_cases else 0,
            "coverage_gaps": gaps,
            "total_gaps": len(gaps),
            "generated_candidates": candidates[: request.max_candidates or 10],
            "ranked_candidates": ranked,
            "ranking_summary": ranking_summary,
        }

        total_duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Persist report to PostgreSQL JSONB if authenticated user & active db
        persisted_report_id: Optional[str] = None
        if db is not None and current_user is not None:
            try:
                from core.database.models import AnalysisSession
                from core.database.repositories.report_repository import ReportRepository

                # Create parent AnalysisSession row to satisfy foreign key constraint
                analysis_session = AnalysisSession(
                    id=session_id,
                    user_id=current_user.id,
                    project_id=request.project_id,
                    analysis_mode="AGENTIC",
                    language="python",
                    analysis_status=state.status.value,
                    gaps_detected=len(gaps),
                    candidates_generated=len(candidates),
                    duration_ms=total_duration_ms,
                )
                db.add(analysis_session)
                await db.flush()

                report_repo = ReportRepository(db)
                full_report_payload = {
                    "product": "EdgeMind",
                    "version": "1.0.0",
                    "status": state.status.value,
                    "code_analysis": static_analysis.get("code_report")
                    or analyze_code(request.code, static_only=True),
                    "test_intelligence": test_intelligence,
                    "agent_audit": {
                        "iterations": state.iteration,
                        "tool_executions": [t.model_dump() for t in state.tool_executions],
                        "summary": state.final_summary,
                    },
                }

                doc = build_analysis_report_doc(
                    report=full_report_payload,
                    session_id=str(session_id),
                    user_id=str(current_user.id),
                    project_id=str(request.project_id) if request.project_id else None,
                    problem_id=str(request.problem_id) if request.problem_id else None,
                    problem_context=request.problem_context,
                    duration_ms=total_duration_ms,
                )

                created_report = await report_repo.create_report(
                    doc=doc,
                    session_id=session_id,
                    user_id=current_user.id,
                    project_id=request.project_id,
                    problem_id=request.problem_id,
                )
                await db.commit()
                persisted_report_id = str(
                    created_report.get("analysis_report_id") or created_report.get("id") or session_id
                )
            except Exception as exc:
                logger.warning(f"Could not persist agent report to database: {exc}")

        return AgentAnalyzeResponse(
            status=state.status.value,
            product="EdgeMind",
            version="1.0.0",
            session_id=str(session_id),
            iterations=state.iteration,
            tool_executions=state.tool_executions,
            final_summary=state.final_summary,
            test_intelligence=test_intelligence,
            code_analysis=static_analysis,
            total_duration_ms=round(total_duration_ms, 2),
            persisted_report_id=persisted_report_id,
            warnings=[
                "Zero user code was executed at runtime.",
                "Generated candidates are labeled GENERATED_TEST with expected_output=None.",
            ],
            limitations=[
                "Synthesized edge cases target domain boundaries, not confirmed runtime bugs.",
            ],
        )
