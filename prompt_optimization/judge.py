"""LLM judge for evaluating component performance."""

import dspy
from prompt_optimization.config import LMConfig
from prompt_optimization.prompts import GRADER_PROMPT


judge_config = LMConfig("openrouter/anthropic/claude-sonnet-4.5", temperature=0.75, max_tokens=128000, cache=True)

class JudgeSignature(dspy.Signature):
    """Signature for component evaluation judge."""
    component_name: str = dspy.InputField(description="Name of the component being evaluated (e.g., planner._predictor.predict)")
    component_trace: str = dspy.InputField(description="Structured trace of component execution (dict/JSON)")
    prediction_trace: str = dspy.InputField(description="Full execution tree trace covering entire prediction")
    component_feedback: str = dspy.OutputField(description="Actionable feedback for improving the component")


class ComponentJudge:
    """
    LLM-based judge for evaluating individual components.

    Uses Claude Sonnet 4.5 by default to provide detailed feedback on
    component performance within the recursive solver system.
    """

    def __init__(self, *, prompt: str = GRADER_PROMPT, lm_config: LMConfig = judge_config):
        """
        Initialize component judge.

        Args:
            prompt: Prompt for the judge
            lm_config: Language model configuration for the judge
        """
        self.lm = dspy.LM(
            model=lm_config.model,
            temperature=lm_config.temperature,
            max_tokens=lm_config.max_tokens,
            cache=lm_config.cache
        )
        self.prompt = prompt
        with dspy.context(lm=self.lm):
            self.predictor = dspy.ChainOfThought(
                JudgeSignature,
                instructions=self.prompt
            )

    def __call__(
        self,
        component_name: str,
        component_trace: dict,
        prediction_trace: str = ""
    ) -> str:
        """
        Evaluate a component and return feedback.

        Args:
            component_name: Name of the component (e.g., "planner")
            component_trace: Structured execution trace for the component
            prediction_trace: Full prediction trace (optional)

        Returns:
            Detailed feedback string
        """
        with dspy.context(lm=self.lm):
            result = self.predictor(
                component_name=component_name,
                component_trace=str(component_trace),
                prediction_trace=prediction_trace
            )
        return result.component_feedback

    async def __acall__(
        self,
        component_name: str,
        component_trace: dict,
        prediction_trace: str = ""
    ) -> str:
        """
        Async evaluate a component and return feedback.

        Args:
            component_name: Name of the component (e.g., "planner")
            component_trace: Structured execution trace for the component
            prediction_trace: Full prediction trace (optional)

        Returns:
            Detailed feedback string
        """
        with dspy.context(lm=self.lm):
            result = await self.predictor(
                component_name=component_name,
                component_trace=str(component_trace),
                prediction_trace=prediction_trace
            )
        return result.component_feedback
