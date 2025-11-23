"""Metrics and cost tracking endpoints."""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from roma_dspy.api.schemas import MetricsResponse
from roma_dspy.api.dependencies import get_storage, verify_execution_exists
from roma_dspy.core.storage.postgres_storage import PostgresStorage

router = APIRouter()


@router.get("/executions/{execution_id}/metrics", response_model=MetricsResponse)
async def get_execution_metrics(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> MetricsResponse:
    """
    Get comprehensive metrics for an execution.

    Includes:
    - Total LM calls and token usage
    - Total cost in USD
    - Average latency
    - Breakdown by task and module

    Args:
        execution_id: Execution ID

    Returns:
        Detailed metrics and cost information
    """
    try:
        # Get LM traces
        lm_traces = await storage.get_lm_traces(execution_id, limit=10000)

        if not lm_traces:
            return MetricsResponse(
                execution_id=execution_id,
                total_lm_calls=0,
                total_tokens=0,
                total_cost_usd=0.0,
                average_latency_ms=0.0,
                task_breakdown={},
            )

        # Calculate totals
        total_lm_calls = len(lm_traces)
        total_tokens = sum(trace.total_tokens for trace in lm_traces)
        total_cost_usd = sum(
            float(trace.cost_usd) if trace.cost_usd else 0.0 for trace in lm_traces
        )

        # Calculate average latency
        latencies = [trace.latency_ms for trace in lm_traces if trace.latency_ms]
        average_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

        # Build task breakdown
        task_breakdown: Dict[str, Dict[str, Any]] = {}

        for trace in lm_traces:
            task_id = trace.task_id or "unknown"

            if task_id not in task_breakdown:
                task_breakdown[task_id] = {
                    "calls": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                    "module": trace.module_name,
                    "model": trace.model,
                }

            task_breakdown[task_id]["calls"] += 1
            task_breakdown[task_id]["tokens"] += trace.total_tokens
            if trace.cost_usd:
                task_breakdown[task_id]["cost_usd"] += float(trace.cost_usd)

        return MetricsResponse(
            execution_id=execution_id,
            total_lm_calls=total_lm_calls,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            average_latency_ms=average_latency_ms,
            task_breakdown=task_breakdown,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics for {execution_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/executions/{execution_id}/costs", response_model=dict)
async def get_execution_costs(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> dict:
    """
    Get cost breakdown for an execution.

    Args:
        execution_id: Execution ID

    Returns:
        Cost information including total cost, token usage, and trace count
    """
    try:
        costs = await storage.get_execution_costs(execution_id)
        return costs

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get costs for {execution_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get costs: {str(e)}")


@router.get("/executions/{execution_id}/toolkit-metrics", response_model=dict)
async def get_toolkit_metrics(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> dict:
    """
    Get comprehensive toolkit metrics for an execution.

    Includes:
    - Toolkit lifecycle metrics (creation, caching, cleanup)
    - Tool invocation metrics (calls, duration, success rates)
    - Breakdown by toolkit and individual tools
    - Cache hit rates and performance statistics

    Args:
        execution_id: Execution ID

    Returns:
        Detailed toolkit and tool usage metrics
    """
    try:
        summary = await storage.get_toolkit_metrics_summary(execution_id)
        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get toolkit metrics for {execution_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get toolkit metrics: {str(e)}"
        )


@router.get("/executions/{execution_id}/toolkit-traces", response_model=dict)
async def get_toolkit_traces(
    execution_id: str = Depends(verify_execution_exists),
    operation: str | None = None,
    toolkit_class: str | None = None,
    limit: int = 1000,
    storage: PostgresStorage = Depends(get_storage),
) -> dict:
    """
    Get raw toolkit lifecycle traces for an execution.

    Args:
        execution_id: Execution ID
        operation: Optional filter by operation (create, cache_hit, cache_miss, cleanup)
        toolkit_class: Optional filter by toolkit class name
        limit: Maximum number of traces to return (default 1000)

    Returns:
        List of toolkit lifecycle traces
    """
    try:
        traces = await storage.get_toolkit_traces(
            execution_id=execution_id,
            operation=operation,
            toolkit_class=toolkit_class,
            limit=limit,
        )

        return {
            "execution_id": execution_id,
            "count": len(traces),
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "timestamp": trace.timestamp.isoformat(),
                    "operation": trace.operation,
                    "toolkit_class": trace.toolkit_class,
                    "duration_ms": trace.duration_ms,
                    "success": trace.success,
                    "error": trace.error,
                    "metadata": trace.metadata,
                }
                for trace in traces
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get toolkit traces for {execution_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get toolkit traces: {str(e)}"
        )


@router.get("/executions/{execution_id}/tool-invocations", response_model=dict)
async def get_tool_invocations(
    execution_id: str = Depends(verify_execution_exists),
    toolkit_class: str | None = None,
    tool_name: str | None = None,
    limit: int = 1000,
    storage: PostgresStorage = Depends(get_storage),
) -> dict:
    """
    Get raw tool invocation traces for an execution.

    Args:
        execution_id: Execution ID
        toolkit_class: Optional filter by toolkit class name
        tool_name: Optional filter by tool name
        limit: Maximum number of traces to return (default 1000)

    Returns:
        List of tool invocation traces
    """
    try:
        traces = await storage.get_tool_invocation_traces(
            execution_id=execution_id,
            toolkit_class=toolkit_class,
            tool_name=tool_name,
            limit=limit,
        )

        return {
            "execution_id": execution_id,
            "count": len(traces),
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "invoked_at": trace.invoked_at.isoformat(),
                    "toolkit_class": trace.toolkit_class,
                    "tool_name": trace.tool_name,
                    "duration_ms": trace.duration_ms,
                    "input_size_bytes": trace.input_size_bytes,
                    "output_size_bytes": trace.output_size_bytes,
                    "success": trace.success,
                    "error": trace.error,
                    "metadata": trace.metadata,
                }
                for trace in traces
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tool invocations for {execution_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get tool invocations: {str(e)}"
        )
