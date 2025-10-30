import dspy

from prompt_optimization.config import LMConfig
from prompt_optimization.prompts.grader_prompts import SEARCH_GRADER_PROMPT



# A simple LLM grader signature: classify into one of the 3 labels
class SearchJudgeSignature(dspy.Signature):
    question: str = dspy.InputField(description="Original question/prompt")
    gold_answer: str = dspy.InputField(description="Reference/gold target answer")
    predicted_answer: str = dspy.InputField(description="Model's predicted answer")
    grade: str = dspy.OutputField(description='One of: CORRECT | INCORRECT | NOT_ATTEMPTED')

class SearchMetric(dspy.Module):
    """
    LLM-based search/QA metric that returns a binary score:
      - 0 if CORRECT
      - 1 if INCORRECT or NOT_ATTEMPTED

    Uses a classification prompt to judge semantic correctness rather than exact match.
    """

    def __init__(self, lm_config: LMConfig, prompt: str = SEARCH_GRADER_PROMPT):
        super().__init__()
        self.prompt = prompt
        self.lm = dspy.LM(
            model=lm_config.model,
            temperature=lm_config.temperature,
            max_tokens=lm_config.max_tokens,
            cache=lm_config.cache,
        )
        self.predictor = dspy.ChainOfThought(SearchJudgeSignature, instructions=self.prompt)

    def _label_to_score(self, label: str) -> int:
        lab = (label or "").strip().upper()
        # Normalize common variants
        if lab.startswith("CORRECT"):
            return 1
        if lab.startswith("INCORRECT") or lab.startswith("NOT_ATTEMPTED"):
            return 0
        # Fallback: treat unknown as incorrect
        return 0

    def forward(self, example, prediction, trace=None, pred_name=None, pred_trace=None) -> int:
        question = example.get("goal") or example.get("question") or ""
        gold = example.get("answer") or example.get("target") or example.get("gold") or ""
        pred_text = getattr(prediction, "result_text", None) or getattr(prediction, "text", None) or str(prediction)

        with dspy.context(lm=self.lm):
            res = self.predictor(
                question=str(question),
                gold_answer=str(gold),
                predicted_answer=str(pred_text),
            )
        return self._label_to_score(res.grade)

    async def aforward(self, example, prediction, trace=None, pred_name=None, pred_trace=None) -> int:
        question = example.get("goal") or example.get("question") or ""
        gold = example.get("answer") or example.get("target") or example.get("gold") or ""
        pred_text = getattr(prediction, "result_text", None) or getattr(prediction, "text", None) or str(prediction)

        with dspy.context(lm=self.lm):
            res = await self.predictor(
                question=str(question),
                gold_answer=str(gold),
                predicted_answer=str(pred_text),
            )
        return self._label_to_score(res.grade)
