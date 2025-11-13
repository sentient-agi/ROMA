from enum import Enum
from typing import Any, Callable, Dict
import dspy


class PredictionStrategy(str, Enum):
    PREDICT = "Predict"
    CHAIN_OF_THOUGHT = "ChainOfThought"
    PROGRAM_OF_THOUGHT = "ProgramOfThought"
    REACT = "ReAct"
    CODE_ACT = "CodeAct"
    BEST_OF_N = "BestOfN"
    MULTI_CHAIN_COMPARISON = "MultiChainComparison"
    REFINE = "Refine"
    KNN = "KNN"
    PARALLEL = "Parallel"
    MAJORITY = "majority"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "PredictionStrategy":
        norm = value.strip()
        # Exact value match (case-insensitive)
        for member in cls:
            if member.value.lower() == norm.lower():
                return member

        aliases: Dict[str, "PredictionStrategy"] = {
            "cot": cls.CHAIN_OF_THOUGHT,
            "chain_of_thought": cls.CHAIN_OF_THOUGHT,
            "react": cls.REACT,
            "code_act": cls.CODE_ACT,
            "best_of_n": cls.BEST_OF_N,
            "mcc": cls.MULTI_CHAIN_COMPARISON,
            "multi_chain_comparison": cls.MULTI_CHAIN_COMPARISON,
            "pot": cls.PROGRAM_OF_THOUGHT,
            "program_of_thought": cls.PROGRAM_OF_THOUGHT,
            "predict": cls.PREDICT,
            "refine": cls.REFINE,
            "knn": cls.KNN,
            "parallel": cls.PARALLEL,
            "majority": cls.MAJORITY,
        }
        key = norm.lower().replace("-", "_").replace(" ", "_")
        if key in aliases:
            return aliases[key]
        raise ValueError(f"Invalid prediction strategy '{value}'")

    def get_callable(self) -> Callable[..., Any]:
        mapping: Dict["PredictionStrategy", Callable[..., Any]] = {
            PredictionStrategy.PREDICT: dspy.Predict,
            PredictionStrategy.CHAIN_OF_THOUGHT: dspy.ChainOfThought,
            PredictionStrategy.PROGRAM_OF_THOUGHT: dspy.ProgramOfThought,
            PredictionStrategy.REACT: dspy.ReAct,
            PredictionStrategy.CODE_ACT: dspy.CodeAct,
            PredictionStrategy.BEST_OF_N: dspy.BestOfN,
            PredictionStrategy.MULTI_CHAIN_COMPARISON: dspy.MultiChainComparison,
            PredictionStrategy.REFINE: dspy.Refine,
            PredictionStrategy.KNN: dspy.KNN,
            PredictionStrategy.PARALLEL: dspy.Parallel,
            PredictionStrategy.MAJORITY: dspy.majority,
        }
        return mapping[self]

    def build(self, signature: Any, **kwargs: Any) -> Any:
        fn = self.get_callable()
        if self is PredictionStrategy.MAJORITY:
            return fn  # majority is a function (aggregator)
        return fn(signature, **kwargs)
