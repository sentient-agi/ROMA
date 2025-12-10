"""Enhanced Executor with PTC service integration for code generation tasks."""

from __future__ import annotations

import dspy
from typing import Union, Any, Optional, Dict, Mapping, Sequence, List
from loguru import logger

from roma_dspy.core.modules.executor import Executor
from roma_dspy.types import PredictionStrategy, TaskType
from roma_dspy.integrations.ptc_client import get_ptc_client


class PTCExecutor(Executor):
    """
    Executor that routes CODE tasks to PTC service.

    Falls back to standard LLM execution if:
    - PTC service is unavailable
    - Task is not a code generation task
    - PTC integration is disabled
    """

    def __init__(
        self,
        prediction_strategy: Union[
            PredictionStrategy, str
        ] = PredictionStrategy.CHAIN_OF_THOUGHT,
        *,
        signature: Any = None,
        config: Optional[Any] = None,
        lm: Optional[dspy.LM] = None,
        model: Optional[str] = None,
        model_config: Optional[Mapping[str, Any]] = None,
        tools: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None,
        ptc_enabled: bool = True,
        ptc_base_url: str = "http://localhost:8002",
        ptc_timeout: float = 300.0,
        **strategy_kwargs: Any,
    ) -> None:
        """
        Initialize PTC-enabled executor.

        Args:
            ptc_enabled: Whether to use PTC service for code tasks
            ptc_base_url: URL of PTC service
            ptc_timeout: Timeout for PTC requests
            **kwargs: Passed to parent Executor
        """
        super().__init__(
            signature=signature,
            config=config,
            prediction_strategy=prediction_strategy,
            lm=lm,
            model=model,
            model_config=model_config,
            tools=tools,
            **strategy_kwargs,
        )

        self.ptc_enabled = ptc_enabled
        self.ptc_base_url = ptc_base_url
        self.ptc_timeout = ptc_timeout
        self._ptc_client = None

        if ptc_enabled:
            self._ptc_client = get_ptc_client(
                base_url=ptc_base_url,
                timeout=ptc_timeout,
            )
            logger.info(f"PTC integration enabled at {ptc_base_url}")

    def _is_code_task(self, goal: str) -> bool:
        """
        Determine if a task is code-related.

        Simple heuristic: check for code-related keywords.
        In production, this could use the task_type from planner.
        """
        code_keywords = [
            "code", "function", "class", "script", "program",
            "implement", "write code", "create a", "build a",
            "python", "javascript", "java", "c++", "rust",
            "api", "endpoint", "module", "library"
        ]
        goal_lower = goal.lower()
        return any(keyword in goal_lower for keyword in code_keywords)

    async def aforward(
        self,
        goal: str,
        task_type: Optional[TaskType] = None,
        **kwargs: Any
    ) -> Any:
        """
        Execute task, routing to PTC if it's a code generation task.

        Args:
            goal: Task description
            task_type: Optional task type from planner
            **kwargs: Additional parameters

        Returns:
            Execution result
        """
        # Check if this should go to PTC
        use_ptc = (
            self.ptc_enabled
            and self._ptc_client is not None
            and (
                task_type == TaskType.CODE_INTERPRET
                or self._is_code_task(goal)
            )
        )

        if use_ptc:
            try:
                logger.info(f"Routing code task to PTC: {goal[:100]}...")

                # Extract requirements if provided
                requirements = kwargs.get("requirements", [])
                language = kwargs.get("language", "python")

                # Call PTC service
                result = await self._ptc_client.generate_code(
                    task_description=goal,
                    requirements=requirements,
                    language=language,
                )

                # Format result for ROMA
                output = f"""Generated code using {result['provider']}:

```{result['language']}
{result['code']}
```

Cost: ${result['cost_usd']:.6f} USD ({result['tokens_used']} tokens)
"""

                logger.info(f"PTC successfully generated code (cost: ${result['cost_usd']:.6f})")

                # Return in ROMA executor format
                return dspy.Prediction(
                    output=output,
                    sources=[f"PTC/{result['provider']}"],
                    _metadata={
                        "ptc_result": result,
                        "cost_usd": result["cost_usd"],
                        "tokens_used": result["tokens_used"],
                        "provider": result["provider"],
                    }
                )

            except Exception as e:
                logger.warning(f"PTC execution failed, falling back to LLM: {e}")
                # Fall through to standard execution

        # Fall back to standard executor (LLM-based)
        logger.info(f"Using standard LLM execution for: {goal[:100]}...")
        return await super().aforward(goal=goal, **kwargs)

    def forward(self, goal: str, task_type: Optional[TaskType] = None, **kwargs: Any) -> Any:
        """
        Synchronous forward (converts to async).

        For compatibility with DSPy's sync interface.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.aforward(goal=goal, task_type=task_type, **kwargs))
