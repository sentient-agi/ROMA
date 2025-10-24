"""Dataset loaders for prompt optimization."""

import dspy
from datasets import load_dataset
import random
from typing import Optional, Tuple, List
import pandas as pd

def load_aimo_datasets(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0
) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    """
    Load AIMO math datasets with configurable sizes.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility

    Returns:
        Tuple of (train_set, val_set, test_set)
    """

    # Load training/validation split from AIMO
    train_split = load_dataset("AI-MO/aimo-validation-aime")['train']
    train_split = [
        dspy.Example({
            "goal": x['problem'],
            'solution': x['solution'],
            'answer': x['answer'],
        }).with_inputs("goal")
        for x in train_split
    ]

    # Shuffle with fixed seed
    random.Random(seed).shuffle(train_split)
    tot_num = len(train_split)

    # Load test split from AIME 2025
    test_split = load_dataset("MathArena/aime_2025")['train']
    test_split = [
        dspy.Example({
            "goal": x['problem'],
            'answer': x['answer'],
        }).with_inputs("goal")
        for x in test_split
    ]

    # Split datasets
    train_set = train_split[:train_size]
    val_set = train_split[tot_num // 2:tot_num // 2 + val_size]

    # Repeat test set if needed to reach desired size
    test_set = (test_split * ((test_size // len(test_split)) + 1))[:test_size]

    return train_set, val_set, test_set

def load_frames_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    tsv_path: str = "hf://datasets/google/frames-benchmark/test.tsv",
    sep: str = "\t",
    text_column: Optional[str] = None,
    answer_column: Optional[str] = None,
) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    """
    Load the Google FRAMES benchmark TSV, then deterministically split into train/val/test.

    If column names are unknown, tries to infer text/answer columns; override via
    `text_column` and `answer_column` when you know them.

    Returns:
        Tuple of (train_set, val_set, test_set)
    """
    # Read TSV
    df = pd.read_csv(tsv_path, sep=sep)

    if df.empty:
        return [], [], []

    # Case-insensitive column resolver
    lower_to_orig = {c.lower(): c for c in df.columns}

    def pick(col_candidates, explicit_lower: Optional[str]):
        if explicit_lower:
            # Use explicit if present
            return lower_to_orig.get(explicit_lower, explicit_lower)
        for c in col_candidates:
            if c in lower_to_orig:
                return lower_to_orig[c]
        return None

    text_col = pick(
        ["prompt", "question", "input", "instruction", "goal", "query", "text"],
        text_column.lower() if text_column else None,
    )
    ans_col = pick(
        ["answer", "target", "label", "output", "response", "gold"],
        answer_column.lower() if answer_column else None,
    )

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[text_col]) if text_col and text_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if ans_col and ans_col in row and not pd.isna(row[ans_col]):
            payload["answer"] = str(row[ans_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    # If not enough left, fill from start to keep sizes
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set

def load_simpleqa_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    csv_path: str = "hf://datasets/basicv8vc/SimpleQA/simple_qa_test_set.csv",
) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    """
    Load the SimpleQA CSV (columns: problem, answer), then deterministically split into train/val/test.

    Returns:
        Tuple of (train_set, val_set, test_set)
    """
    df = pd.read_csv(csv_path)

    if df.empty:
        return [], [], []

    # Resolve columns case-insensitively
    lower_to_orig = {c.lower(): c for c in df.columns}
    problem_col = lower_to_orig.get("problem", "problem")
    answer_col = lower_to_orig.get("answer", "answer")

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[problem_col]) if problem_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if answer_col in row and not pd.isna(row[answer_col]):
            payload["answer"] = str(row[answer_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set

def load_simpleqa_verified_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    csv_path: str = "hf://datasets/google/simpleqa-verified/simpleqa_verified.csv",
) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    """
    Load the SimpleQA-Verified CSV (columns: problem, answer), then deterministically split into train/val/test.

    Note: Requires Hugging Face auth (e.g., `huggingface-cli login`) to access the dataset.

    Returns:
        Tuple of (train_set, val_set, test_set)
    """
    df = pd.read_csv(csv_path)

    if df.empty:
        return [], [], []

    # Resolve columns case-insensitively
    lower_to_orig = {c.lower(): c for c in df.columns}
    problem_col = lower_to_orig.get("problem", "problem")
    answer_col = lower_to_orig.get("answer", "answer")

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[problem_col]) if problem_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if answer_col in row and not pd.isna(row[answer_col]):
            payload["answer"] = str(row[answer_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set

def load_seal0_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    parquet_path: str = "hf://datasets/vtllms/sealqa/seal-0.parquet",
) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    """
    Load the SEAL-0 Parquet (columns: question, answer), then deterministically split into train/val/test.

    Note: Requires Hugging Face auth (e.g., `huggingface-cli login`) to access the dataset.

    Returns:
        Tuple of (train_set, val_set, test_set)
    """
    df = pd.read_parquet(parquet_path)

    if df.empty:
        return [], [], []

    # Resolve columns case-insensitively
    lower_to_orig = {c.lower(): c for c in df.columns}
    question_col = lower_to_orig.get("question", "question")
    answer_col = lower_to_orig.get("answer", "answer")

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[question_col]) if question_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if answer_col in row and not pd.isna(row[answer_col]):
            payload["answer"] = str(row[answer_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set