"""Metric that augments scalar scores with LLM-generated feedback."""

from __future__ import annotations

import inspect
from typing import Any, Optional, Union

import dspy

from prompt_optimization.judge import ComponentJudge

class MetricWithFeedback(dspy.Module):
    """Metric that combines scalar scoring with optional component feedback."""

    def __init__(
        self,
        judge: ComponentJudge,
        scoring_metric: Optional[Any] = None,
    ) -> None:
        super().__init__()
        self.judge = judge
        self.scoring_metric = scoring_metric

    def forward(
        self,
        example: Any,
        prediction: Any,
        trace: Any = None,
        pred_name: Optional[str] = None,
        pred_trace: Optional[dict] = None,
    ) -> Union[int, dspy.Prediction]:
        if self.scoring_metric:
            score = self.scoring_metric(example=example, prediction=prediction)
        else:
            score = "No scoring metric provided"


        feedback = "None"
        if pred_trace is not None:
            try:
                prediction_trace = getattr(prediction, "output_trace", "")
                feedback = self.judge(
                    component_name=pred_name,
                    component_trace=pred_trace,
                    prediction_trace=prediction_trace or "",
                )
            except Exception as exc:  # noqa: BLE001
                feedback = f"Judge error: {exc}"

        print(f"Feedback: {feedback}")
        print(f"Score: {score}")
        return dspy.Prediction(score=score, feedback=feedback)

    async def aforward(
        self,
        example: Any,
        prediction: Any,
        trace: Any = None,
        pred_name: Optional[str] = None,
        pred_trace: Optional[dict] = None,
    ) -> Union[int, dspy.Prediction]:
        if self.scoring_metric:
            score = await self.scoring_metric(example=example, prediction=prediction)
        else:
            score = "No scoring metric provided"

        feedback = "None"
        if pred_trace is not None:
            try:
                prediction_trace = getattr(prediction, "output_trace", "")
                feedback = await self.judge(
                    component_name=pred_name,
                    component_trace=pred_trace,
                    prediction_trace=prediction_trace or "",
                )
            except Exception as exc:  # noqa: BLE001
                feedback = f"Judge error: {exc}"

        print(f"Feedback: {feedback}")
        print(f"Score: {score}")
        return dspy.Prediction(score=score, feedback=feedback)
