"""LM and Task trace endpoints."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from roma_dspy.api.schemas import LMTraceResponse
from roma_dspy.api.helpers import lm_trace_to_response
from roma_dspy.api.dependencies import get_storage, verify_execution_exists
from roma_dspy.core.storage.postgres_storage import PostgresStorage

router = APIRouter()


@router.get(
    "/executions/{execution_id}/lm-traces", response_model=List[LMTraceResponse]
)
async def get_lm_traces(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
    module_name: Optional[str] = Query(None, description="Filter by module name"),
    model: Optional[str] = Query(None, description="Filter by model"),
    limit: int = Query(100, ge=1, le=1000),
) -> List[LMTraceResponse]:
    """
    Get LM traces for an execution.

    Shows all LLM calls made during execution with:
    - Prompts and responses
    - Token usage and costs
    - Latency information
    - Module and task context

    Args:
        execution_id: Execution ID
        module_name: Optional module filter (atomizer, planner, executor, etc.)
        model: Optional model filter (gpt-4o-mini, etc.)
        limit: Maximum number of records to return

    Returns:
        List of LM traces with full details
    """
    try:
        # Get LM traces from storage
        traces = await storage.get_lm_traces(
            execution_id=execution_id, module_name=module_name, model=model, limit=limit
        )

        # Convert to response schemas
        return [lm_trace_to_response(trace) for trace in traces]

    except Exception as e:
        logger.error(f"Failed to get LM traces for {execution_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get LM traces: {str(e)}"
        )


@router.get("/executions/{execution_id}/lm-traces/cost-summary")
async def get_cost_summary(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> dict:
    """
    Get cost and token usage summary for an execution.

    Returns:
        Aggregated cost/token data by module and overall
    """
    try:
        # Get all LM traces
        traces = await storage.get_lm_traces(execution_id=execution_id)

        # Aggregate by module
        by_module = {}
        total_cost = 0.0
        total_tokens = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_calls = 0
        total_latency_ms = 0

        for trace in traces:
            module = trace.module_name
            if module not in by_module:
                by_module[module] = {
                    "calls": 0,
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_usd": 0.0,
                    "avg_latency_ms": 0,
                    "total_latency_ms": 0,
                }

            by_module[module]["calls"] += 1
            by_module[module]["total_tokens"] += trace.total_tokens or 0
            by_module[module]["prompt_tokens"] += trace.prompt_tokens or 0
            by_module[module]["completion_tokens"] += trace.completion_tokens or 0
            by_module[module]["cost_usd"] += (
                float(trace.cost_usd) if trace.cost_usd else 0.0
            )
            by_module[module]["total_latency_ms"] += trace.latency_ms or 0

            total_calls += 1
            total_tokens += trace.total_tokens or 0
            total_prompt_tokens += trace.prompt_tokens or 0
            total_completion_tokens += trace.completion_tokens or 0
            total_cost += float(trace.cost_usd) if trace.cost_usd else 0.0
            total_latency_ms += trace.latency_ms or 0

        # Calculate averages
        for module_data in by_module.values():
            if module_data["calls"] > 0:
                module_data["avg_latency_ms"] = (
                    module_data["total_latency_ms"] // module_data["calls"]
                )
                module_data["avg_cost_per_call"] = (
                    module_data["cost_usd"] / module_data["calls"]
                )

        return {
            "execution_id": execution_id,
            "summary": {
                "total_calls": total_calls,
                "total_tokens": total_tokens,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_cost_usd": round(total_cost, 6),
                "avg_latency_ms": total_latency_ms // total_calls
                if total_calls > 0
                else 0,
                "avg_cost_per_call": round(total_cost / total_calls, 6)
                if total_calls > 0
                else 0,
            },
            "by_module": by_module,
        }

    except Exception as e:
        logger.error(f"Failed to get cost summary for {execution_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get cost summary: {str(e)}"
        )


@router.get("/executions/{execution_id}/lm-traces/{trace_id}/prompt")
async def get_trace_prompt(
    trace_id: int,
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> dict:
    """
    Get full prompt for a specific LM trace.

    Useful for prompt optimization and debugging.

    Returns:
        Full prompt text and metadata
    """
    try:
        trace = await storage.get_lm_trace(trace_id)

        if not trace or trace.execution_id != execution_id:
            raise HTTPException(
                status_code=404,
                detail=f"LM trace {trace_id} not found for execution {execution_id}",
            )

        return {
            "trace_id": trace_id,
            "execution_id": execution_id,
            "module_name": trace.module_name,
            "task_id": trace.task_id,
            "model": trace.model,
            "temperature": trace.temperature,
            "prompt": trace.prompt,
            "response": trace.response,
            "prompt_length": len(trace.prompt) if trace.prompt else 0,
            "response_length": len(trace.response) if trace.response else 0,
            "tokens": {
                "prompt": trace.prompt_tokens,
                "completion": trace.completion_tokens,
                "total": trace.total_tokens,
            },
            "cost_usd": float(trace.cost_usd) if trace.cost_usd else 0.0,
            "latency_ms": trace.latency_ms,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trace prompt {trace_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get trace prompt: {str(e)}"
        )
