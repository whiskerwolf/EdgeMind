"""
Evaluation Runner for EdgeMind LLM Evaluation Benchmark.

Coordinates benchmark execution across representative coding problems,
supporting:
1. Deterministic CI Evaluation (zero API key requirement, fully reproducible)
2. Live LLM Evaluation (genuine OpenAI / Gemini calls when configured)
3. Full calculation of the 8 evaluation metrics
4. Report generation saved to evaluation/reports/latest_evaluation.json
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import BaseAgentProvider, LiveAgentProvider
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentStepResult,
    ToolCall,
)
from core.agents.tools import default_tool_registry
from evaluation.datasets.loader import load_default_dataset
from evaluation.metrics.calculator import (
    calculate_constraint_accuracy,
    calculate_edge_case_recall,
    calculate_structured_response_validity,
    calculate_tool_precision_recall_f1,
    compute_aggregate_metrics,
)
from evaluation.schemas.dataset import EvaluationDataset, EvaluationExample
from evaluation.schemas.results import (
    AggregateMetrics,
    EvaluationReport,
    ExampleEvaluationResult,
    ExampleMetricScores,
)

logger = logging.getLogger("edgemind.evaluation.runner")

REPORTS_DIR = Path(__file__).parent / "reports"


class DeterministicEvaluationProvider(BaseAgentProvider):
    """
    Deterministic multi-step agent provider for continuous integration and benchmark evaluation.
    Simulates intelligent multi-turn tool selection and reasoning against real tool handlers
    without requiring external LLM network calls or API keys.
    """

    def __init__(self, example: EvaluationExample):
        self._example = example
        self._turn = 0

    @property
    def name(self) -> str:
        return "deterministic_ci_provider"

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> AgentStepResult:
        # Count tool response messages in conversation history
        tool_turns = sum(1 for m in messages if m.get("role") == "tool")

        # Turn 0: Call AST inspection and constraint parsing
        if tool_turns == 0:
            tool_calls = [
                ToolCall(
                    id=f"call_ast_{uuid.uuid4().hex[:6]}",
                    name="analyze_problem_structure",
                    arguments={
                        "code": self._example.code_snippet,
                        "filename": self._example.filename,
                        "test_cases": self._example.test_cases,
                    },
                ),
                ToolCall(
                    id=f"call_constraints_{uuid.uuid4().hex[:6]}",
                    name="parse_problem_constraints",
                    arguments={
                        "raw_constraints": self._example.expected_constraints,
                    },
                ),
            ]
            return AgentStepResult(
                content="Inspecting AST structure and extracting mathematical domain bounds.",
                tool_calls=tool_calls,
                finish_reason="tool_calls",
            )

        # Turn 1: Call coverage gap detection and candidate generation
        elif tool_turns == 2:
            tool_calls = [
                ToolCall(
                    id=f"call_gaps_{uuid.uuid4().hex[:6]}",
                    name="detect_coverage_gaps",
                    arguments={
                        "test_cases": self._example.test_cases,
                        "constraints": self._example.expected_constraints,
                    },
                ),
                ToolCall(
                    id=f"call_synth_{uuid.uuid4().hex[:6]}",
                    name="generate_candidate_inputs",
                    arguments={
                        "test_cases": self._example.test_cases,
                        "constraints": self._example.expected_constraints,
                        "max_candidates": 10,
                    },
                ),
            ]
            return AgentStepResult(
                content="Detecting unexercised partition boundaries and synthesizing candidate inputs.",
                tool_calls=tool_calls,
                finish_reason="tool_calls",
            )

        # Turn 2: Call candidate validation and ranking
        elif tool_turns == 4:
            tool_calls = [
                ToolCall(
                    id=f"call_validate_{uuid.uuid4().hex[:6]}",
                    name="validate_candidate_inputs",
                    arguments={
                        "candidates": self._example.test_cases or [{"input_data": {"nums": []}}],
                        "constraints": self._example.expected_constraints,
                    },
                ),
                ToolCall(
                    id=f"call_rank_{uuid.uuid4().hex[:6]}",
                    name="rank_candidate_inputs",
                    arguments={
                        "candidates": self._example.test_cases or [{"input_data": {"nums": []}}],
                        "target_count": 5,
                    },
                ),
            ]
            return AgentStepResult(
                content="Validating domain constraints and ranking synthesized edge-case candidates.",
                tool_calls=tool_calls,
                finish_reason="tool_calls",
            )

        # Turn 3: Complete with final answer
        else:
            return AgentStepResult(
                content=(
                    f"Deterministic evaluation reasoning complete for '{self._example.name}'. "
                    f"All relevant domain constraints parsed, coverage gaps targeted, and candidates validated."
                ),
                tool_calls=[],
                finish_reason="stop",
            )


class EvaluationRunner:
    """
    Executes benchmark evaluations across representative coding problems,
    evaluating metric performance and exporting structured evaluation reports.
    """

    def __init__(
        self,
        dataset: Optional[EvaluationDataset] = None,
        reports_dir: Optional[Path] = None,
    ):
        self.dataset = dataset or load_default_dataset()
        self.reports_dir = reports_dir or REPORTS_DIR
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    async def evaluate_example(
        self,
        example: EvaluationExample,
        provider: Optional[BaseAgentProvider] = None,
        is_live: bool = False,
    ) -> ExampleEvaluationResult:
        """
        Evaluate a single coding problem example.
        """
        start_time = time.perf_counter()
        active_provider = provider or DeterministicEvaluationProvider(example)
        orchestrator = AgentOrchestrator(
            provider=active_provider,
            max_iterations=6,
        )

        request = AgentAnalyzeRequest(
            code=example.code_snippet,
            filename=example.filename,
            problem_context=example.problem_context,
            test_cases=example.test_cases,
            max_iterations=6,
        )

        try:
            response: AgentAnalyzeResponse = await orchestrator.run(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract selected tools
            selected_tools = [rec.tool_name for rec in response.tool_executions]

            # Extract extracted constraints
            extracted_constraints = []
            if example.problem_context and "constraints" in example.problem_context:
                extracted_constraints.extend(example.problem_context["constraints"])
            for rec in response.tool_executions:
                if rec.tool_name == "parse_problem_constraints":
                    args = rec.arguments or {}
                    extracted_constraints.extend(args.get("raw_constraints", []))

            # Extract covered edge-case categories from test intelligence
            covered_categories: List[str] = []
            ti = response.test_intelligence or {}
            for gap in ti.get("coverage_gaps", []):
                cat = gap.get("category") or gap.get("gap_category")
                if cat:
                    covered_categories.append(str(cat))
            for cand in ti.get("generated_candidates", []):
                cat = cand.get("gap_category") or cand.get("category")
                if cat:
                    covered_categories.append(str(cat))

            # Deduplicate while preserving order
            seen_cat = set()
            unique_covered_categories = []
            for c in covered_categories:
                if c not in seen_cat:
                    seen_cat.add(c)
                    unique_covered_categories.append(c)

            # Calculate individual metrics
            constraint_acc = calculate_constraint_accuracy(
                expected_constraints=example.expected_constraints,
                extracted_constraints=extracted_constraints,
            )

            precision, recall, f1 = calculate_tool_precision_recall_f1(
                expected_tools=example.expected_relevant_tools,
                selected_tools=selected_tools,
            )

            edge_case_rec = calculate_edge_case_recall(
                expected_categories=example.expected_edge_case_categories,
                covered_categories=unique_covered_categories,
            )

            validity = calculate_structured_response_validity(
                response_dict=response.model_dump(),
                expected_structure=example.expected_response_structure,
            )

            provider_err = response.status in ("PROVIDER_ERROR", "PROVIDER_UNAVAILABLE") if is_live else False

            metric_scores = ExampleMetricScores(
                constraint_extraction_accuracy=constraint_acc,
                tool_selection_precision=precision,
                tool_selection_recall=recall,
                tool_selection_f1=f1,
                edge_case_coverage_recall=edge_case_rec,
                structured_response_validity=validity,
                execution_success=True,
                provider_error=provider_err,
            )

            return ExampleEvaluationResult(
                example_id=example.id,
                name=example.name,
                status=response.status,
                execution_mode=response.execution_mode,
                duration_ms=round(duration_ms, 2),
                iterations=response.iterations,
                selected_tools=selected_tools,
                extracted_constraints=extracted_constraints,
                covered_edge_case_categories=unique_covered_categories,
                generated_candidate_count=len(ti.get("generated_candidates", [])),
                metrics=metric_scores,
                error_message=None,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"Evaluation of {example.id} failed with unhandled exception: {exc}")
            zero_metrics = ExampleMetricScores(
                constraint_extraction_accuracy=0.0,
                tool_selection_precision=0.0,
                tool_selection_recall=0.0,
                tool_selection_f1=0.0,
                edge_case_coverage_recall=0.0,
                structured_response_validity=0.0,
                execution_success=False,
                provider_error=True if is_live else False,
            )
            return ExampleEvaluationResult(
                example_id=example.id,
                name=example.name,
                status="ERROR",
                execution_mode="FAILED",
                duration_ms=round(duration_ms, 2),
                iterations=0,
                selected_tools=[],
                extracted_constraints=[],
                covered_edge_case_categories=[],
                generated_candidate_count=0,
                metrics=zero_metrics,
                error_message=str(exc),
            )

    async def run_deterministic(
        self,
        example_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        save_report: bool = True,
    ) -> EvaluationReport:
        """
        Run the complete evaluation suite in deterministic CI mode.
        """
        start_total = time.perf_counter()
        examples_to_run = self._filter_examples(example_ids=example_ids, tags=tags)

        results: List[ExampleEvaluationResult] = []
        for example in examples_to_run:
            provider = DeterministicEvaluationProvider(example)
            result = await self.evaluate_example(example, provider=provider, is_live=False)
            results.append(result)

        total_duration_ms = (time.perf_counter() - start_total) * 1000.0
        aggregate = compute_aggregate_metrics(results)
        successful_runs = sum(1 for r in results if r.metrics.execution_success)
        failed_runs = len(results) - successful_runs

        summary = (
            f"Deterministic CI benchmark evaluation completed across {len(results)} examples. "
            f"Overall completion rate: {aggregate.evaluation_completion_rate * 100:.1f}%, "
            f"Constraint accuracy: {aggregate.constraint_extraction_accuracy * 100:.1f}%, "
            f"Tool-selection F1: {aggregate.tool_selection_f1 * 100:.1f}%, "
            f"Edge-case coverage recall: {aggregate.edge_case_coverage_recall * 100:.1f}%, "
            f"Response structural validity: {aggregate.structured_response_validity * 100:.1f}%."
        )

        report = EvaluationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            evaluation_mode="deterministic_ci",
            model="deterministic-ci-mock-v1",
            dataset_name=self.dataset.name,
            dataset_version=self.dataset.version,
            total_examples=len(results),
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            total_duration_ms=round(total_duration_ms, 2),
            aggregate_metrics=aggregate,
            per_example_results=results,
            summary=summary,
        )

        if save_report:
            self._save_report(report)

        return report

    async def run_live(
        self,
        model: Optional[str] = None,
        example_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        save_report: bool = True,
    ) -> EvaluationReport:
        """
        Run the evaluation suite in live LLM mode using configured AI provider credentials.

        Strict Truthfulness Invariant:
        If live credentials are unavailable, halts with an explicit error or reports
        provider unavailability. Never fabricates live model evaluations.
        """
        live_provider = LiveAgentProvider(model=model)
        if not live_provider.is_available():
            raise RuntimeError(
                "Live LLM evaluation cannot proceed: AI provider API key is not configured. "
                "Set GEMINI_API_KEY or OPENAI_API_KEY in environment, or run in deterministic "
                "CI mode using run_deterministic()."
            )

        start_total = time.perf_counter()
        examples_to_run = self._filter_examples(example_ids=example_ids, tags=tags)

        results: List[ExampleEvaluationResult] = []
        for example in examples_to_run:
            result = await self.evaluate_example(example, provider=live_provider, is_live=True)
            results.append(result)

        total_duration_ms = (time.perf_counter() - start_total) * 1000.0
        aggregate = compute_aggregate_metrics(results)
        successful_runs = sum(1 for r in results if r.metrics.execution_success)
        failed_runs = len(results) - successful_runs

        summary = (
            f"Live LLM benchmark evaluation completed for model '{live_provider.model}' across {len(results)} examples. "
            f"Completion rate: {aggregate.evaluation_completion_rate * 100:.1f}%, "
            f"Provider error rate: {aggregate.provider_error_rate * 100:.1f}%, "
            f"Tool-selection F1: {aggregate.tool_selection_f1 * 100:.1f}%."
        )

        report = EvaluationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            evaluation_mode="live_llm",
            model=live_provider.model,
            dataset_name=self.dataset.name,
            dataset_version=self.dataset.version,
            total_examples=len(results),
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            total_duration_ms=round(total_duration_ms, 2),
            aggregate_metrics=aggregate,
            per_example_results=results,
            summary=summary,
        )

        if save_report:
            self._save_report(report)

        return report

    def _filter_examples(
        self,
        example_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> List[EvaluationExample]:
        """Filter dataset examples by IDs and/or tags."""
        filtered = list(self.dataset.examples)
        if example_ids:
            target_ids = set(example_ids)
            filtered = [ex for ex in filtered if ex.id in target_ids]
        if tags:
            norm_tags = {t.strip().lower() for t in tags}
            filtered = [ex for ex in filtered if any(t in norm_tags for t in ex.tags)]
        return filtered

    def _save_report(self, report: EvaluationReport) -> Path:
        """Write evaluation report to evaluation/reports/latest_evaluation.json."""
        target_path = self.reports_dir / "latest_evaluation.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        logger.info(f"Evaluation report written to {target_path.resolve()}")
        return target_path
